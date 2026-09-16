"""Create a versioned Whisper-label dataset without rewriting source manifests.

All records are transcribed without reference prompts. This is machine labeling,
not human adjudication. Existing Test metrics retain their original references.
"""

import hashlib
import json
import re
import traceback
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / ".local-data/speechocean762"
OUT = REPO / ".local-data/speechocean-whisper-v1"
REV = "41f01f3fe87f28c78e2fbf8b568835947dd65ed9"


def dump(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def norm(text):
    return " ".join(
        re.sub(r"[^a-z0-9'\s]", " ", text.lower().replace("’", "'")).split()
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    splits = {
        s: json.loads((SOURCE / f"{s}.json").read_text())
        for s in ["train", "validation", "test"]
    }
    source_hashes = {
        s: hashlib.sha256((SOURCE / f"{s}.json").read_bytes()).hexdigest()
        for s in splits
    }
    rows = [r for rs in splits.values() for r in rs]
    assert len(rows) == 2440 and len({r["id"] for r in rows}) == 2440
    protocol = {
        "label_version": "whisper-v1",
        "model": "openai/whisper-large-v3-turbo",
        "revision": REV,
        "source_manifest_hashes": source_hashes,
        "language": "en",
        "task": "transcribe",
        "do_sample": False,
        "max_new_tokens": 128,
        "batch_size": 8,
        "precision": "FP32",
        "reference_prompt": False,
        "human_adjudicated": False,
        "scope": "All 2440 children; same split membership and audio.",
        "evaluation_note": "Whisper-derived Test references measure agreement with machine labels, not independently verified ASR accuracy.",
    }
    if (OUT / "label-protocol.json").exists():
        assert json.loads((OUT / "label-protocol.json").read_text()) == protocol
    dump(OUT / "label-protocol.json", protocol)
    pred_path = OUT / "predictions.jsonl"
    predictions = {}
    if pred_path.exists():
        for line in pred_path.read_text().splitlines():
            p = json.loads(line)
            assert p["id"] not in predictions
            predictions[p["id"]] = p
    expected = {r["id"]: r for r in rows}
    for uid, p in predictions.items():
        assert (
            uid in expected
            and p["audio_sha256"] == expected[uid]["audio_sha256"]
            and p["revision"] == REV
        )
    remaining = [r for r in rows if r["id"] not in predictions]
    if remaining:
        cached = (
            Path.home()
            / ".cache/huggingface/hub/models--openai--whisper-large-v3-turbo/snapshots"
            / REV
        )
        processor = AutoProcessor.from_pretrained(cached, local_files_only=True)
        model = (
            AutoModelForSpeechSeq2Seq.from_pretrained(
                cached, local_files_only=True, dtype=torch.float32
            )
            .cuda()
            .eval()
        )
        with pred_path.open("a") as log, torch.inference_mode():
            for offset in range(0, len(remaining), 8):
                batch = remaining[offset : offset + 8]
                audios = []
                for r in batch:
                    p = SOURCE / r["source_path"]
                    assert (
                        hashlib.sha256(p.read_bytes()).hexdigest() == r["audio_sha256"]
                    )
                    audio, sr = sf.read(p, dtype="float32")
                    assert sr == 16000 and audio.ndim == 1 and len(audio) > 0
                    assert len(audio) <= 30 * 16000, (
                        "Do not silently truncate long audio"
                    )
                    audios.append(audio)
                inputs = processor(
                    audios,
                    sampling_rate=16000,
                    return_tensors="pt",
                    return_attention_mask=True,
                ).to("cuda")
                tokens = model.generate(
                    **inputs,
                    language="en",
                    task="transcribe",
                    do_sample=False,
                    max_new_tokens=128,
                )
                texts = processor.batch_decode(tokens, skip_special_tokens=True)
                assert len(texts) == len(batch)
                for r, t, ids in zip(batch, texts, tokens):
                    # A capped or empty output must be investigated rather than silently replacing a label.
                    # Whisper removes EOS from individual returned sequences during postprocessing.
                    # Check the output length instead; do not mistake a short sequence for truncation.
                    assert len(ids) < 128, (
                        f"Review potentially capped output: {r['id']}"
                    )
                    text = t.strip()
                    assert norm(text), f"Empty transcript: {r['id']}"
                    p = {
                        "id": r["id"],
                        "text": text,
                        "audio_sha256": r["audio_sha256"],
                        "revision": REV,
                    }
                    log.write(json.dumps(p, ensure_ascii=False) + "\n")
                    log.flush()
                    predictions[r["id"]] = p
                if offset % 80 == 0:
                    status = {
                        "status": "transcribing",
                        "completed": len(predictions),
                        "total": len(rows),
                    }
                    dump(OUT / "status.json", status)
                    print(json.dumps(status), flush=True)
    assert set(predictions) == set(expected)
    summary = {
        "label_version": "whisper-v1",
        "total": len(rows),
        "human_adjudicated": False,
        "splits": {},
    }
    for split, rs in splits.items():
        output = [
            {
                **r,
                "original_text": r["text"],
                "text": predictions[r["id"]]["text"],
                "label_source": "openai/whisper-large-v3-turbo",
                "label_revision": REV,
            }
            for r in rs
        ]
        dump(OUT / f"{split}.json", output)
        summary["splits"][split] = {
            "count": len(rs),
            "changed_text": sum(r["text"] != p["text"] for r, p in zip(rs, output)),
            "changed_after_normalization": sum(
                norm(r["text"]) != norm(p["text"]) for r, p in zip(rs, output)
            ),
            "sha256": hashlib.sha256((OUT / f"{split}.json").read_bytes()).hexdigest(),
        }
        assert (
            hashlib.sha256((SOURCE / f"{split}.json").read_bytes()).hexdigest()
            == source_hashes[split]
        )
    # Preserve metadata needed by existing loaders while recording new label hashes.
    source_protocol = json.loads((SOURCE / "protocol.json").read_text())
    updated = json.loads(json.dumps(source_protocol))
    for s in splits:
        updated["splits"][s]["sha256"] = summary["splits"][s]["sha256"]
    updated["label_protocol"] = protocol
    dump(OUT / "protocol.json", updated)
    wave_link = OUT / "WAVE"
    if not wave_link.exists():
        wave_link.symlink_to(SOURCE / "WAVE", target_is_directory=True)
    dump(OUT / "summary.json", summary)
    dump(
        OUT / "status.json",
        {"status": "complete", "completed": len(rows), "total": len(rows)},
    )
    print("COMPLETE", json.dumps(summary), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        dump(OUT / "status.json", {"status": "failed", "error": traceback.format_exc()})
        raise
