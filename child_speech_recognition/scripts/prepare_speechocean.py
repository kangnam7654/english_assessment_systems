"""Download only children (<18) and split official Train by speaker and age."""

import concurrent.futures
import hashlib
import io
import json
import random
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / ".local-data/speechocean762"
REV = "613968e3b0b789fc33936fb5eba1973176ba7d11"
BASE = f"https://raw.githubusercontent.com/jimbozhang/speechocean762/{REV}/"


def fetch(path):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(BASE + path, timeout=60).read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    all_rows = {}
    for split in ["train", "test"]:
        meta = {}
        for name in ["spk2age", "utt2spk", "text", "wav.scp"]:
            data = fetch(f"{split}/{name}")
            (ROOT / f"{split}-{name}.txt").write_bytes(data)
            meta[name] = dict(
                s.split(maxsplit=1) for s in data.decode().splitlines() if s.strip()
            )
        all_rows[split] = [
            {
                "id": u,
                "speaker_id": spk,
                "age": int(meta["spk2age"][spk]),
                "text": meta["text"][u],
                "source_path": meta["wav.scp"][u],
            }
            for u, spk in sorted(meta["utt2spk"].items())
            if int(meta["spk2age"][spk]) < 18
        ]
    train_spk = {r["speaker_id"] for r in all_rows["train"]}
    test_spk = {r["speaker_id"] for r in all_rows["test"]}
    assert not train_spk & test_spk
    rng = random.Random(20260916)
    validation = set()
    for age in sorted({r["age"] for r in all_rows["train"]}):
        speakers = sorted(
            {r["speaker_id"] for r in all_rows["train"] if r["age"] == age}
        )
        rng.shuffle(speakers)
        if len(speakers) > 1:
            validation.update(speakers[: max(1, round(len(speakers) * 0.2))])
    splits = {
        "train": [r for r in all_rows["train"] if r["speaker_id"] not in validation],
        "validation": [r for r in all_rows["train"] if r["speaker_id"] in validation],
        "test": all_rows["test"],
    }

    def download(row):
        path = ROOT / row["source_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes() if path.exists() else fetch(row["source_path"])
        with wave.open(io.BytesIO(data)) as w:
            assert w.getframerate() == 16000 and w.getnchannels() == 1
            row["duration"] = w.getnframes() / 16000
        path.write_bytes(data)
        row["audio_sha256"] = hashlib.sha256(data).hexdigest()
        return row

    for split, rows in splits.items():
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(download, rows))
        (ROOT / f"{split}.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(
            split,
            len(rows),
            "speakers",
            len({r["speaker_id"] for r in rows}),
            "seconds",
            sum(r["duration"] for r in rows),
            flush=True,
        )
    hashes = {s: {r["audio_sha256"] for r in rs} for s, rs in splits.items()}
    assert (
        not hashes["train"] & hashes["test"]
        and not hashes["validation"] & hashes["test"]
        and not hashes["train"] & hashes["validation"]
    )
    protocol = {
        "revision": REV,
        "child_age": "<18",
        "seed": 20260916,
        "validation": "Official Train speakers: ~20% held out within each age, at least one where age has >1 speakers; singleton ages remain Train.",
        "test": "All official Test children, no selection using outcomes.",
        "splits": {
            s: {
                "count": len(rs),
                "speakers": len({r["speaker_id"] for r in rs}),
                "hours": sum(r["duration"] for r in rs) / 3600,
                "sha256": hashlib.sha256((ROOT / f"{s}.json").read_bytes()).hexdigest(),
            }
            for s, rs in splits.items()
        },
    }
    (ROOT / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    print(json.dumps(protocol), flush=True)


if __name__ == "__main__":
    main()
