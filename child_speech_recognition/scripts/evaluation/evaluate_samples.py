"""Compare the fixed public audio demos with the Validation-selected checkpoint."""

import hashlib
import json
from pathlib import Path

from ..common import runtime as e
from omegaconf import OmegaConf

SAMPLES = Path(__file__).resolve().parents[2] / "samples/speechocean762"


def evaluate(model, samples):
    """Use the Test decoder and normalization, with batches of at most four."""
    model.eval()
    predictions = []
    with e.torch.inference_mode():
        for offset in range(0, len(samples), 4):
            batch = samples[offset : offset + 4]
            wavs = []
            for row in batch:
                path = SAMPLES / row["audio"]
                assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
                audio, sr = e.sf.read(path, dtype="float32")
                assert sr == 16000 and audio.ndim == 1
                wavs.append(e.torch.from_numpy(audio))
            lengths = e.torch.tensor([w.numel() for w in wavs], device="cuda")
            signal = e.torch.nn.utils.rnn.pad_sequence(wavs, batch_first=True).cuda()
            encoded, lens = model(input_signal=signal, input_signal_length=lengths)
            hypotheses = model.decoding.rnnt_decoder_predictions_tensor(
                encoder_output=encoded, encoded_lengths=lens, return_hypotheses=True
            )
            assert len(hypotheses) == len(batch)
            predictions.extend(h.text for h in hypotheses)
    return predictions


def main():
    manifest_path = SAMPLES / "manifest.json"
    samples = json.loads(manifest_path.read_text())["samples"]
    selected = json.loads((e.ROOT / "results.json").read_text())["best"]
    checkpoint = e.ROOT / "best.pt"
    saved = e.torch.load(checkpoint, map_location="cpu", weights_only=False)
    assert saved["step"] == selected["step"] == 28314
    model = e.load()
    cfg = OmegaConf.create(OmegaConf.to_container(model.cfg.decoding, resolve=True))
    cfg.strategy = "greedy_batch"
    cfg.greedy.allow_cuda_graphs = False
    model.change_decoding_strategy(cfg)
    before = evaluate(model, samples)
    model.load_state_dict(saved["model"])
    del saved
    after = evaluate(model, samples)
    refs = [e.norm(r["reference"]) for r in samples]
    records = []
    for row, a, b in zip(samples, before, after):
        scores = {}
        for name, text in [("before", a), ("after", b)]:
            score = e.jiwer.process_words(e.norm(row["reference"]), e.norm(text))
            scores[name] = {
                "text": text,
                "word_errors": score.substitutions + score.deletions + score.insertions,
                "substitutions": score.substitutions,
                "deletions": score.deletions,
                "insertions": score.insertions,
            }
        records.append(
            dict(
                id=row["id"],
                reference=row["reference"],
                audio_sha256=row["sha256"],
                **scores,
            )
        )
    report = {
        "model": "nvidia/parakeet-tdt-0.6b-v2",
        "model_revision": e.REV,
        "checkpoint_step": selected["step"],
        "selected_on": "Validation",
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "decoding": "greedy_batch",
        "precision": "FP32",
        "tf32": False,
        "batch_size": 4,
        "normalization": "Lowercase, curly apostrophe to ASCII, non [a-z0-9' whitespace] to spaces, collapse whitespace (runtime.norm).",
        "caveat": "Five fixed Mandarin-L1 child demo recordings, not a representative benchmark. References are supplied reading text, not independently adjudicated verbatim transcripts.",
        "samples": records,
    }
    for name, predictions in [("before", before), ("after", after)]:
        hyps = [e.norm(x) for x in predictions]
        report[name] = {
            "wer": e.jiwer.wer(refs, hyps),
            "cer": e.jiwer.cer(refs, hyps),
            "word_errors": sum(r[name]["word_errors"] for r in records),
            "reference_words": sum(len(r.split()) for r in refs),
        }
    e.dump(SAMPLES / "predictions.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
