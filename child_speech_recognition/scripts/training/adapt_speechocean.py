"""Bounded mixed-domain adaptation; select on Validation, then evaluate fixed Tests."""

import hashlib
import json
import os
import random
import traceback
from pathlib import Path

from ..evaluation import evaluate_speechocean as ocean
from ..common import runtime as e

OUT = Path(
    os.environ.get(
        "SPEECHOCEAN_ADAPT_DIR", e.REPO / ".local-data/asr-speechocean-adaptation"
    )
)
if (
    ocean.DATA.resolve() != (e.REPO / ".local-data/speechocean762").resolve()
    and OUT.resolve() == (e.REPO / ".local-data/asr-speechocean-adaptation").resolve()
):
    raise ValueError(
        "Set SPEECHOCEAN_ADAPT_DIR to a new directory when changing labels"
    )
T = e.torch


def korean_eval(model, audio, split, label):
    model.eval()
    rows = sorted(e.rows(split), key=lambda r: (r["duration"], r["audio_filename"]))
    results = []
    with T.inference_mode():
        for offset in range(0, len(rows), 4):
            batch = rows[offset : offset + 4]
            wavs = [T.from_numpy(audio.read(r)) for r in batch]
            lengths = T.tensor([w.numel() for w in wavs], device="cuda")
            signal = T.nn.utils.rnn.pad_sequence(wavs, batch_first=True).cuda()
            enc, lens = model(input_signal=signal, input_signal_length=lengths)
            hyps = model.decoding.rnnt_decoder_predictions_tensor(
                encoder_output=enc, encoded_lengths=lens, return_hypotheses=True
            )
            assert len(hyps) == len(batch)
            results.extend({**r, "hypothesis": h.text} for r, h in zip(batch, hyps))
    refs = [e.norm(r["text"]) for r in results]
    hyps = [e.norm(r["hypothesis"]) for r in results]
    metric = {
        "count": len(rows),
        "wer": e.jiwer.wer(refs, hyps),
        "cer": e.jiwer.cer(refs, hyps),
    }
    e.dump(OUT / f"{label}-predictions.json", results)
    return metric


class MixedAudio(e.Audio):
    def read(self, row):
        if "source_path" not in row:
            return super().read(row)
        a, sr = e.sf.read(ocean.DATA / row["source_path"], dtype="float32")
        assert sr == 16000 and a.ndim == 1
        return a


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "protocol.json").exists():
        raise RuntimeError(
            "Run directory already exists; preserve this experiment and choose a new output directory."
        )
    seed = 20260916
    random.seed(seed)
    e.np.random.seed(seed)
    T.manual_seed(seed)
    source = e.ROOT / "best.pt"
    saved = T.load(source, map_location="cpu", weights_only=False)
    assert saved["step"] == 28314
    protocol = json.loads((ocean.DATA / "protocol.json").read_text())
    splits = {
        s: json.loads((ocean.DATA / f"{s}.json").read_text())
        for s in ["train", "validation", "test"]
    }
    for s in splits:
        assert (
            hashlib.sha256((ocean.DATA / f"{s}.json").read_bytes()).hexdigest()
            == protocol["splits"][s]["sha256"]
        )
    korean_protocol = json.loads(
        (e.REPO / "child_speech_recognition/results/protocol.json").read_text()
    )
    for s in ["train", "validation", "test"]:
        assert (
            hashlib.sha256((e.DATA / f"splits/{s}.jsonl").read_bytes()).hexdigest()
            == korean_protocol["manifest_hashes"][s]
        )
    korean = e.rows("train")
    e.dump(
        OUT / "protocol.json",
        {
            "initial_checkpoint_sha256": hashlib.sha256(
                source.read_bytes()
            ).hexdigest(),
            "initial_step": 28314,
            "seed": seed,
            "epochs": 3,
            "ocean_per_epoch": len(splits["train"]),
            "korean_replay_per_epoch": len(splits["train"]),
            "mixing": "1:1 utterances; new seeded Korean sample without replacement within each epoch",
            "optimizer": "AdamW",
            "lr": 1e-5,
            "microbatch": 1,
            "accumulation": 4,
            "bn_stats": "frozen",
            "precision": "FP32",
            "selection": "Minimum mean of Korean and ocean Validation WER, including epoch 0; require Korean WER <= epoch0 + 0.005.",
            "test_usage": "Tests already observed; evaluate selected model once after Validation selection. No Test model selection.",
            "ocean_protocol": protocol,
            "korean_manifest_hashes": korean_protocol["manifest_hashes"],
        },
    )
    model = e.load()
    model.load_state_dict(saved["model"])
    del saved
    ocean.configure(model)
    audio = MixedAudio()
    opt = e.optimizer(model)
    bn = {
        k: v.detach().cpu().clone()
        for k, v in model.named_buffers()
        if k.endswith(("running_mean", "running_var", "num_batches_tracked"))
    }
    history = []
    best_score = float("inf")
    selected_epoch = 0
    baseline = None
    for epoch in range(4):
        if epoch:
            rng = random.Random(seed + epoch)
            replay = rng.sample(korean, len(splits["train"]))
            rows = splits["train"] + replay
            rng.shuffle(rows)
            e.dump(
                OUT / f"epoch-{epoch}-order.json",
                [r.get("id", r.get("audio_filename")) for r in rows],
            )
            e.trainmode(model)
            for offset in range(0, len(rows), 4):
                batch = rows[offset : offset + 4]
                opt.zero_grad(set_to_none=True)
                losses = []
                for row in batch:
                    value = e.loss(model, audio.batch(model, [row]))
                    if not T.isfinite(value) or value.item() < 0:
                        raise RuntimeError(
                            f"Invalid loss at epoch {epoch}, offset {offset}"
                        )
                    losses.append(value.item())
                    (value / len(batch)).backward()
                T.nn.utils.clip_grad_norm_(
                    model.parameters(), 1, error_if_nonfinite=True
                )
                opt.step()
                if offset % 200 == 0:
                    status = {
                        "status": "training",
                        "epoch": epoch,
                        "records": offset + len(batch),
                        "total": len(rows),
                        "loss": sum(losses) / len(losses),
                    }
                    e.dump(OUT / "status.json", status)
                    print(json.dumps(status), flush=True)
            assert all(
                T.equal(v.detach().cpu(), bn[k])
                for k, v in model.named_buffers()
                if k in bn
            )
        e.dump(OUT / "status.json", {"status": "validating", "epoch": epoch})
        ko = korean_eval(model, audio, "validation", f"epoch-{epoch}-korean-validation")
        zh = ocean.evaluate(
            model, splits["validation"], f"epoch-{epoch}-ocean-validation", out=OUT
        )
        if baseline is None:
            baseline = ko["wer"]
        score = (ko["wer"] + zh["wer"]) / 2
        eligible = ko["wer"] <= baseline + 0.005
        metric = {
            "epoch": epoch,
            "korean": ko,
            "ocean": zh,
            "mean_wer": score,
            "eligible": eligible,
        }
        history.append(metric)
        if eligible and score < best_score:
            best_score = score
            selected_epoch = epoch
            T.save(
                {"model": model.state_dict(), "epoch": epoch, "metric": metric},
                OUT / "best.tmp",
            )
            (OUT / "best.tmp").replace(OUT / "best.pt")
        e.dump(
            OUT / "validation.json",
            {"history": history, "selected_epoch": selected_epoch},
        )
        print("VALIDATION", json.dumps(metric), flush=True)
    saved = T.load(OUT / "best.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(saved["model"])
    del saved
    e.dump(
        OUT / "status.json",
        {"status": "evaluating_selected_test", "selected_epoch": selected_epoch},
    )
    zh = ocean.evaluate(model, splits["test"], "selected-ocean-test", out=OUT)
    ko = korean_eval(model, audio, "test", "selected-korean-test")
    report = {
        "selected_epoch": selected_epoch,
        "validation": history,
        "korean_test": ko,
        "ocean_test": zh,
        "checkpoint_sha256": hashlib.sha256((OUT / "best.pt").read_bytes()).hexdigest(),
        "initial_korean_test": json.loads(
            (e.ROOT / "test-28314-metrics.json").read_text()
        ),
        "initial_ocean_test": json.loads((ocean.OUT / "comparison.json").read_text())[
            "after"
        ],
    }
    e.dump(OUT / "results.json", report)
    e.dump(
        OUT / "status.json", {"status": "complete", "selected_epoch": selected_epoch}
    )
    print("COMPLETE", json.dumps(report), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        e.dump(
            OUT / "status.json", {"status": "failed", "error": traceback.format_exc()}
        )
        raise
