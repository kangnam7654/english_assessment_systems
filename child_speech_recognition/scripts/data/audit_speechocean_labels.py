"""Read-only label audit and fixed review sample; never rewrite source labels."""

import collections
import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / ".local-data/speechocean-audit"


def main():
    scores = json.loads((ROOT / "scores.json").read_text())
    detail = json.loads((ROOT / "scores-detail.json").read_text())
    rows = [
        dict(r, split=s)
        for s in ["train", "validation", "test"]
        for r in json.loads((ROOT / f"{s}.json").read_text())
    ]
    issues = []
    for r in rows:
        u, t = r["id"], r["text"]
        flags = []
        if not t.strip():
            flags.append("empty")
        if re.search(r"'{2,}|\bN{3,}\b|\ufffd", t):
            flags.append("placeholder_or_broken_text")
        if re.search(r"[^A-Z0-9\s'.,?!:-]", t):
            flags.append("unexpected_characters")
        if t != scores[u]["text"] or t != detail[u]["text"]:
            flags.append("source_text_mismatch")
        if t != " ".join(w["text"] for w in scores[u]["words"]):
            flags.append("word_annotation_mismatch")
        if re.search(r"\b(\w+)\s+\1\b", t):
            flags.append("repeated_word_review_only")
        weak = [w["text"] for w in scores[u]["words"] if w["accuracy"] <= 3]
        if weak:
            flags.append("source_low_word_accuracy_review_only")
        if flags:
            issues.append(
                {
                    "id": u,
                    "split": r["split"],
                    "text": t,
                    "flags": flags,
                    "low_accuracy_words": weak,
                }
            )
    # Stratified deterministic sample: one shuffled record per split and age,
    # cycling strata to reach 100. Include the five existing public demos separately.
    rng = random.Random(20260916)
    buckets = collections.defaultdict(list)
    for r in rows:
        if r["split"] in ["train", "validation"]:
            buckets[(r["split"], r["age"])].append(r)
    for key in sorted(buckets):
        rng.shuffle(buckets[key])
    selected = []
    while len(selected) < 100 and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(selected) < 100:
                selected.append(buckets[key].pop())
    demo = {"000030012", "000490017", "010500012", "020140004", "030070015"}
    selected.extend(r for r in rows if r["id"] in demo)
    for r in selected:
        r["source_accuracy"] = scores[r["id"]]["accuracy"]
        r["word_annotations"] = scores[r["id"]]["words"]
    summary = {
        "count": len(rows),
        "split_counts": dict(collections.Counter(r["split"] for r in rows)),
        "flag_counts": dict(collections.Counter(f for r in issues for f in r["flags"])),
        "review_sample_count": len(selected),
        "review_selection": "100 Train/Validation records, round-robin age and split strata after seeded shuffle (20260916), plus 5 existing Test demos; not proportional random sampling.",
        "corrected_labels": 0,
        "human_audio_adjudication": False,
        "source_hashes": {
            n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
            for n in ["scores.json", "scores-detail.json"]
        },
    }
    for name, data in [
        ("structural-summary.json", summary),
        ("flags.json", issues),
        ("review-sample.json", selected),
    ]:
        (ROOT / name).write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
