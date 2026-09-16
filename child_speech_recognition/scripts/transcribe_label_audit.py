"""Independent Whisper cross-check without reference prompts; not ground truth."""

import hashlib
import json
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / ".local-data/speechocean-audit"


def main():
    cache = (
        Path.home() / ".cache/huggingface/hub/models--openai--whisper-large-v3-turbo"
    )
    rev = (cache / "refs/main").read_text().strip()
    model_path = cache / "snapshots" / rev
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
    model = (
        AutoModelForSpeechSeq2Seq.from_pretrained(
            model_path, local_files_only=True, dtype=torch.float32
        )
        .cuda()
        .eval()
    )
    rows = json.loads((AUDIT / "review-sample.json").read_text())
    out = AUDIT / "whisper-predictions.jsonl"
    with out.open("w") as f, torch.inference_mode():
        for i, r in enumerate(rows):
            p = ROOT / ".local-data/speechocean762" / r["source_path"]
            assert hashlib.sha256(p.read_bytes()).hexdigest() == r["audio_sha256"]
            audio, sr = sf.read(p, dtype="float32")
            assert sr == 16000 and audio.ndim == 1
            inputs = processor(
                audio, sampling_rate=sr, return_tensors="pt", return_attention_mask=True
            ).to("cuda")
            ids = model.generate(
                **inputs,
                language="en",
                task="transcribe",
                do_sample=False,
                max_new_tokens=128,
            )
            text = processor.batch_decode(ids, skip_special_tokens=True)[0]
            f.write(
                json.dumps(
                    {
                        "id": r["id"],
                        "text": text,
                        "model": "openai/whisper-large-v3-turbo",
                        "revision": rev,
                        "audio_sha256": r["audio_sha256"],
                    }
                )
                + "\n"
            )
            f.flush()
            if i % 20 == 0:
                print(i + 1, len(rows), flush=True)
    print("COMPLETE", len(rows), flush=True)


if __name__ == "__main__":
    main()
