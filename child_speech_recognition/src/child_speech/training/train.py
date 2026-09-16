"""Train with native NeMo modules and CUDA TDT loss, under an explicit PyTorch loop."""

import json
import os
import time
import traceback
from pathlib import Path

from omegaconf import OmegaConf

from ..common import runtime as e

T = e.torch
ROOT = e.ROOT
N = 41183
PER = (N + 3) // 4
TOTAL = 3 * PER


def evaluate(model, audio, step):
    """Decode the fixed Validation split and persist WER/CER for checkpoint selection.

    Args:
        model: Model used for the forward pass or parameter update.
        audio: Reader for the experiment's 16 kHz mono audio archive.
        step: Optimizer step recorded alongside the evaluation or checkpoint.

    Returns:
        Validation WER, CER, optimizer step, epoch fraction, and sample count.

    Raises:
        AssertionError: Decoder output count differs from the batch size or Validation
            does not contain 5,178 unique recordings.
    """
    model.eval()
    rs = sorted(
        e.rows("validation"), key=lambda r: (r["duration"], r["audio_filename"])
    )
    results = []
    with T.inference_mode():
        for offset in range(0, len(rs), 4):
            batch = rs[offset : offset + 4]
            wavs = [T.from_numpy(audio.read(r)) for r in batch]
            lens = T.tensor([x.numel() for x in wavs], device="cuda")
            signal = T.nn.utils.rnn.pad_sequence(wavs, batch_first=True).cuda()
            encoded, elens = model(input_signal=signal, input_signal_length=lens)
            hypotheses = model.decoding.rnnt_decoder_predictions_tensor(
                encoder_output=encoded, encoded_lengths=elens, return_hypotheses=True
            )
            assert len(hypotheses) == len(batch)
            results.extend(
                {**r, "hypothesis": h.text} for r, h in zip(batch, hypotheses)
            )
            if offset % 1000 == 0:
                print("validation", step, offset + len(batch), flush=True)
    assert len(results) == 5178 and len({r["audio_filename"] for r in results}) == 5178
    refs = [e.norm(r["text"]) for r in results]
    hyps = [e.norm(r["hypothesis"]) for r in results]
    metric = {
        "step": step,
        "epoch": step / PER,
        "wer": e.jiwer.wer(refs, hyps),
        "cer": e.jiwer.cer(refs, hyps),
        "count": len(rs),
    }
    (ROOT / f"validation-{step}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results)
    )
    e.dump(ROOT / f"validation-{step}-metrics.json", metric)
    return metric


def main():
    """Run resumable NeMo fine-tuning and select checkpoints using Validation WER.

    Raises:
        RuntimeError: A nonfinite or negative loss is observed during training.
        AssertionError: Training/Validation manifest integrity or checkpoint identity checks fail.
    """
    rs = e.ordered()
    audio = e.Audio()
    model = e.load()
    opt = e.optimizer(model)
    # Disable inference CUDA graphs for predictable memory and startup costs.
    cfg = OmegaConf.create(OmegaConf.to_container(model.cfg.decoding, resolve=True))
    cfg.greedy.allow_cuda_graphs = False
    model.change_decoding_strategy(cfg)
    protocol = {
        "model": "nvidia/parakeet-tdt-0.6b-v2",
        "revision": e.REV,
        "framework": "nemo_toolkit 3.0.0 native model and TDTLossNumba; custom PyTorch loop",
        "epochs": 3,
        "steps": TOTAL,
        "train_records": N,
        "microbatch": 1,
        "accumulation": 4,
        "lr": 1e-5,
        "optimizer": "AdamW",
        "betas": [0.9, 0.999],
        "eps": 1e-8,
        "weight_decay": 0,
        "clip": 1,
        "precision": "fp32",
        "bn_running_stats": "frozen",
        "specaugment": False,
        "dither": 0,
        "sigma": 0,
        "omega": 0,
        "loss_reduction": "mean",
        "dropout": "native NeMo configuration; differs from Transformers port",
        "selection": "minimum Validation WER, quarter epoch; includes pretrained",
        "test_used": False,
        "goal_wer": 0.1,
        "manifest_hashes": {
            s: e.hashlib.sha256((e.DATA / f"splits/{s}.jsonl").read_bytes()).hexdigest()
            for s in ["train", "validation"]
        },
    }
    e.dump(ROOT / "protocol.json", protocol)
    bn = {
        k: v.detach().cpu().clone()
        for k, v in model.named_buffers()
        if k.endswith(("running_mean", "running_var", "num_batches_tracked"))
    }
    assert len(bn) == 72
    first = 0
    history = []
    best = float("inf")
    if (ROOT / "resume.pt").exists():
        saved = T.load(ROOT / "resume.pt", map_location="cpu", weights_only=False)
        model.load_state_dict(saved["model"])
        opt.load_state_dict(saved["optimizer"])
        first = saved["step"]
        history = saved["history"]
        best = min(r["wer"] for r in history)
        T.set_rng_state(saved["cpu_rng"])
        T.cuda.set_rng_state(saved["cuda_rng"])
        del saved
    else:
        e.dump(ROOT / "status.json", {"status": "evaluating_pretrained_validation"})
        history = [evaluate(model, audio, 0)]
        best = history[0]["wer"]
        T.save(
            {"step": 0, "model": model.state_dict(), "metric": history[0]},
            ROOT / "best.pt",
        )
        T.manual_seed(e.SEED)
        e.np.random.seed(e.SEED)
        e.random.seed(e.SEED)

    def save(step):
        """Save model, optimizer, random state, and progress for resumable training.

        Args:
            step: Optimizer step recorded alongside the evaluation or checkpoint.
        """
        state = {
            "step": step,
            "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "optimizer": opt.state_dict(),
            "cpu_rng": T.get_rng_state(),
            "cuda_rng": T.cuda.get_rng_state(),
            "history": history,
        }
        T.save(state, ROOT / "resume.tmp")
        (ROOT / "resume.tmp").replace(ROOT / "resume.pt")

    log_path = ROOT / "training.jsonl"
    if log_path.exists():
        old = log_path.read_text().splitlines()
        retained = [line for line in old if json.loads(line)["step"] <= first]
        if len(retained) != len(old):
            (ROOT / "training.interrupted.jsonl").write_text("\n".join(old) + "\n")
            log_path.write_text("\n".join(retained) + ("\n" if retained else ""))
    e.trainmode(model)
    with (ROOT / "training.jsonl").open("a") as log:
        for step in range(first, TOTAL):
            start = time.monotonic()
            opt.zero_grad(set_to_none=True)
            offset = step % PER
            batch = rs[offset * 4 : (offset + 1) * 4]
            ls = 0
            for r in batch:
                value = e.loss(model, audio.batch(model, [r]))
                if not T.isfinite(value) or value.item() < 0:
                    raise RuntimeError(
                        f"loss={value.item()} step={step + 1} audio={r['audio_filename']}"
                    )
                ls += value.item()
                (value / len(batch)).backward()
            grad = T.nn.utils.clip_grad_norm_(
                model.parameters(), 1, error_if_nonfinite=True
            )
            opt.step()
            T.cuda.synchronize()
            item = {
                "step": step + 1,
                "epoch": (step + 1) / PER,
                "records": len(batch),
                "loss": ls / len(batch),
                "gradient_norm": grad.item(),
                "seconds": time.monotonic() - start,
            }
            log.write(json.dumps(item) + "\n")
            log.flush()
            if (step + 1) % 100 == 0 or step == first:
                print(item, flush=True)
                e.dump(
                    ROOT / "status.json",
                    {
                        "status": "training",
                        "step": step + 1,
                        "total_steps": TOTAL,
                        "epoch": (step + 1) / PER,
                        "best_validation_wer": best,
                    },
                )
            if (step + 1) % 2574 == 0:
                assert all(
                    T.equal(v.detach().cpu(), bn[k])
                    for k, v in model.named_buffers()
                    if k in bn
                )
                rng = T.get_rng_state()
                cuda_rng = T.cuda.get_rng_state()
                e.dump(
                    ROOT / "status.json",
                    {"status": "evaluating_validation", "step": step + 1},
                )
                metric = evaluate(model, audio, step + 1)
                history.append(metric)
                if metric["wer"] < best:
                    best = metric["wer"]
                    T.save(
                        {
                            "step": step + 1,
                            "model": model.state_dict(),
                            "metric": metric,
                        },
                        ROOT / "best.tmp",
                    )
                    (ROOT / "best.tmp").replace(ROOT / "best.pt")
                T.set_rng_state(rng)
                T.cuda.set_rng_state(cuda_rng)
                e.trainmode(model)
                e.dump(
                    ROOT / "results.json",
                    {
                        "checkpoints": history,
                        "best": min(history, key=lambda r: r["wer"]),
                        "goal_achieved": best < 0.1,
                        "test_used": False,
                    },
                )
                text = "# NeMo Parakeet 3 epoch\n\nNative NeMo model/TDT CUDA loss; AdamW FP32, batch 1 x accumulation 4, BN stats frozen. Test 미사용. Native dropout differs from Transformers.\n\n| Epoch | Validation WER | CER |\n|---|---:|---:|\n"
                for r in history:
                    text += f"| {r['epoch']:.2f} | {r['wer'] * 100:.3f}% | {r['cer'] * 100:.3f}% |\n"
                (ROOT / "RESULTS.ko.md").write_text(text)
                save(step + 1)
    logs = [json.loads(s) for s in (ROOT / "training.jsonl").read_text().splitlines()]
    assert [r["step"] for r in logs] == list(range(1, TOTAL + 1)) and sum(
        r["records"] for r in logs
    ) == 3 * N
    e.dump(
        ROOT / "status.json",
        {
            "status": "complete",
            "best": min(history, key=lambda r: r["wer"]),
            "goal_achieved": best < 0.1,
            "test_used": False,
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        e.dump(
            ROOT / "status.json", {"status": "failed", "error": traceback.format_exc()}
        )
        raise
