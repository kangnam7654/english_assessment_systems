"""Evaluate every official Test child using frozen original and Korean-adapted models."""

import hashlib
import json
import os
from pathlib import Path

import runtime as e
from omegaconf import OmegaConf

DATA = Path(
    os.environ.get("SPEECHOCEAN_DATA_DIR", e.REPO / ".local-data/speechocean762")
)
OUT = Path(
    os.environ.get("SPEECHOCEAN_EVAL_DIR", e.REPO / ".local-data/asr-speechocean")
)
if (
    DATA.resolve() != (e.REPO / ".local-data/speechocean762").resolve()
    and OUT.resolve() == (e.REPO / ".local-data/asr-speechocean").resolve()
):
    raise ValueError("Set SPEECHOCEAN_EVAL_DIR to a new directory when changing labels")


def evaluate(model, rows, label, out=OUT):
    model.eval()
    results = []
    with e.torch.inference_mode():
        for offset in range(0, len(rows), 4):
            batch = rows[offset : offset + 4]
            wavs = []
            for row in batch:
                p = DATA / row["source_path"]
                assert hashlib.sha256(p.read_bytes()).hexdigest() == row["audio_sha256"]
                a, sr = e.sf.read(p, dtype="float32")
                assert sr == 16000 and a.ndim == 1
                wavs.append(e.torch.from_numpy(a))
            lengths = e.torch.tensor([w.numel() for w in wavs], device="cuda")
            signal = e.torch.nn.utils.rnn.pad_sequence(wavs, batch_first=True).cuda()
            enc, lens = model(input_signal=signal, input_signal_length=lengths)
            hyps = model.decoding.rnnt_decoder_predictions_tensor(
                encoder_output=enc, encoded_lengths=lens, return_hypotheses=True
            )
            assert len(hyps) == len(batch)
            results.extend({**r, "hypothesis": h.text} for r, h in zip(batch, hyps))
            if offset % 200 == 0:
                print(label, offset + len(batch), len(rows), flush=True)
    refs = [e.norm(r["text"]) for r in results]
    hyps = [e.norm(r["hypothesis"]) for r in results]
    score = e.jiwer.process_words(refs, hyps)
    metric = {
        "count": len(rows),
        "wer": score.wer,
        "cer": e.jiwer.cer(refs, hyps),
        "word_errors": score.substitutions + score.deletions + score.insertions,
        "reference_words": sum(len(r.split()) for r in refs),
    }
    out.mkdir(parents=True, exist_ok=True)
    e.dump(out / f"{label}-predictions.json", results)
    e.dump(out / f"{label}-metrics.json", metric)
    return metric


def configure(model):
    cfg = OmegaConf.create(OmegaConf.to_container(model.cfg.decoding, resolve=True))
    cfg.strategy = "greedy_batch"
    cfg.greedy.allow_cuda_graphs = False
    model.change_decoding_strategy(cfg)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = json.loads((DATA / "test.json").read_text())
    checkpoint = e.ROOT / "best.pt"
    saved = e.torch.load(checkpoint, map_location="cpu", weights_only=False)
    assert saved["step"] == 28314
    model = e.load()
    configure(model)
    before = evaluate(model, rows, "pretrained")
    model.load_state_dict(saved["model"])
    del saved
    after = evaluate(model, rows, "korean-adapted")
    report = {
        "scope": "All official speechocean762 Test speakers aged <18; label provenance in dataset protocol, no human transcript adjudication.",
        "dataset": json.loads((DATA / "protocol.json").read_text()),
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "checkpoint_step": 28314,
        "before": before,
        "after": after,
        "wer_change_pp": 100 * (after["wer"] - before["wer"]),
    }
    e.dump(OUT / "comparison.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
