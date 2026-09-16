"""Create a private listening page and a small public model-output comparison.

Audio and dataset reference labels stay in the private output directory.
"""

import argparse
import base64
import hashlib
import html
import json
import re
import zipfile
from pathlib import Path


def normalize(text):
    """Normalize transcripts consistently without rewriting word spellings.

    Args:
        text: Text to process without changing the original input.

    Returns:
        Normalized transcript, preserving spelling differences.
    """
    return " ".join(
        re.sub(r"[^a-z0-9'\s]", " ", text.lower().replace("’", "'")).split()
    )


def errors(reference, prediction):
    """Count word insertions, deletions, and substitutions with edit distance.

    Args:
        reference: Reference words used to measure transcription errors.
        prediction: Predicted words aligned against the reference.

    Returns:
        Word-level Levenshtein edit count.
    """
    previous = list(range(len(prediction) + 1))
    for i, word in enumerate(reference, 1):
        current = [i]
        for j, other in enumerate(prediction, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != other))
            )
        previous = current
    return previous[-1]


def paired(before_path, after_path):
    """Join baseline and tuned predictions after verifying identical IDs, hashes, and labels.

    Args:
        before_path: JSONL predictions from the pretrained baseline.
        after_path: JSONL predictions from the fine-tuned model.

    Returns:
        Tuples of baseline row, tuned row, baseline word-error count, and tuned word-
        error count.

    Raises:
        ValueError: Prediction IDs differ or contain duplicates; Reference/audio
            identity mismatch.
    """
    before = [json.loads(s) for s in before_path.read_text().splitlines()]
    after = [json.loads(s) for s in after_path.read_text().splitlines()]
    left = {r["audio_filename"]: r for r in before}
    right = {r["audio_filename"]: r for r in after}
    if (
        len(left) != len(before)
        or len(right) != len(after)
        or left.keys() != right.keys()
    ):
        raise ValueError("Prediction IDs differ or contain duplicates")
    output = []
    for key in sorted(left):
        a, b = left[key], right[key]
        if any(a[k] != b[k] for k in ("text", "audio_sha256", "audio_member")):
            raise ValueError("Reference/audio identity mismatch")
        ref = normalize(a["text"]).split()
        output.append(
            (
                a,
                b,
                errors(ref, normalize(a["hypothesis"]).split()),
                errors(ref, normalize(b["hypothesis"]).split()),
            )
        )
    return output


def main():
    """Build private audio comparisons and a public report without reference transcripts.

    Raises:
        ValueError: Not enough examples matching the declared selection rule; Audio hash
            mismatch.
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--audio-zip", type=Path, required=True)
    p.add_argument("--private-output", type=Path, required=True)
    p.add_argument("--public-output", type=Path, required=True)
    args = p.parse_args()
    if ".local-data" not in args.private_output.resolve().parts:
        p.error("Private output must be inside a Git-ignored .local-data directory")
    pairs = paired(args.before, args.after)
    short = [
        r
        for r in pairs
        if 5 <= len(normalize(r[0]["text"]).split()) <= 12 and r[0]["duration"] <= 8
    ]
    improved = [r for r in short if 1 <= r[2] <= 2 and r[3] == 0]
    regressed = [r for r in short if r[2] == 0 and 1 <= r[3] <= 2]
    # Illustrative, filename-ordered examples, not a representative metric sample.
    selected = improved[:3] + regressed[:1]
    if len(selected) != 4:
        raise ValueError("Not enough examples matching the declared selection rule")
    public, cards = [], []
    with zipfile.ZipFile(args.audio_zip) as archive:
        for index, (a, b, old, new) in enumerate(selected, 1):
            wav = archive.read(a["audio_member"])
            if hashlib.sha256(wav).hexdigest() != a["audio_sha256"]:
                raise ValueError("Audio hash mismatch")
            item = {
                "example": index,
                "outcome": "improved" if new < old else "regressed",
                "before": a["hypothesis"],
                "after": b["hypothesis"],
                "before_word_errors": old,
                "after_word_errors": new,
            }
            public.append(item)
            cards.append(
                f"<article><h2>Example {index} — {item['outcome']}</h2>"
                f'<audio controls src="data:audio/wav;base64,{base64.b64encode(wav).decode()}"></audio>'
                f"<p>Reference: {html.escape(a['text'])}</p><p>Before: {html.escape(a['hypothesis'])}</p>"
                f"<p>After: {html.escape(b['hypothesis'])}</p><p>Word errors: {old} → {new}</p></article>"
            )
    args.private_output.mkdir(parents=True, exist_ok=True)
    page = (
        '<!doctype html><meta charset="utf-8"><title>ASR listening examples — private</title><style>body{font:18px system-ui;max-width:860px;margin:40px auto;padding:16px}article{border-top:1px solid #ccc;padding:20px 0}audio{width:100%}</style><h1>Parakeet: before / after</h1><p>Private AI Hub listening examples. Do not redistribute this page. Three improvements and one regression, selected for illustration. Corpus Test WER: 14.45% → 8.50%.</p>'
        + "".join(cards)
    )
    (args.private_output / "index.html").write_text(page)
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(
        json.dumps(
            {
                "selection": "First three improved and first regressed examples in filename order; 5–12 reference words, <=8 seconds; one or two errors versus zero. Illustrative selection, not random sampling.",
                "examples": public,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
