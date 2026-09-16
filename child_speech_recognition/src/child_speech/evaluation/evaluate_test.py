"""Provide evaluate test operations for evaluation."""

import hashlib
import json

from omegaconf import OmegaConf

from ..common import runtime as e

T = e.torch
ROOT = e.ROOT
PER = 10296


def evaluate(model, audio, step):
    """Decode the fixed Test split and write paired predictions and WER/CER.

    Args:
        model: Model used for the forward pass or parameter update.
        audio: Reader for the experiment's 16 kHz mono audio archive.
        step: Optimizer step recorded alongside the evaluation or checkpoint.

    Returns:
        Test metrics including WER, CER, step, epoch, and sample count.

    Raises:
        AssertionError: Decoder output count differs from the batch size or Test does not
            contain 4,567 unique recordings.
    """
    model.eval()
    rs = sorted(e.rows("test"), key=lambda r: (r["duration"], r["audio_filename"]))
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
                print("test", step, offset + len(batch), flush=True)
    assert len(results) == 4567 and len({r["audio_filename"] for r in results}) == 4567
    refs = [e.norm(r["text"]) for r in results]
    hyps = [e.norm(r["hypothesis"]) for r in results]
    metric = {
        "step": step,
        "epoch": step / PER,
        "wer": e.jiwer.wer(refs, hyps),
        "cer": e.jiwer.cer(refs, hyps),
        "count": len(rs),
    }
    (ROOT / f"test-{step}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results)
    )
    e.dump(ROOT / f"test-{step}-metrics.json", metric)
    return metric


def main():
    """Verify fixed Test provenance and compare the baseline with the selected checkpoint.

    Raises:
        AssertionError: The Test manifest, selected checkpoint step, or paired prediction
            identities do not match the recorded experiment.
    """
    manifest = e.DATA / "splits/test.jsonl"
    expected = json.loads(
        (e.REPO / "child_speech_recognition/results/protocol.json").read_text()
    )["manifest_hashes"]["test"]
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == expected
    selected = json.loads((ROOT / "results.json").read_text())["best"]
    saved = T.load(ROOT / "best.pt", map_location="cpu", weights_only=False)
    assert saved["step"] == selected["step"] and selected["step"] > 0
    step = selected["step"]
    checkpoint_hash = hashlib.file_digest(
        (ROOT / "best.pt").open("rb"), "sha256"
    ).hexdigest()
    e.dump(
        ROOT / "test-protocol.json",
        {
            "selected_on": "Validation",
            "checkpoint_step": saved["step"],
            "checkpoint_sha256": checkpoint_hash,
            "test_sha256": expected,
            "count": 4567,
            "no_test_selection": True,
        },
    )
    model = e.load()
    audio = e.Audio()
    cfg = OmegaConf.create(OmegaConf.to_container(model.cfg.decoding, resolve=True))
    cfg.greedy.allow_cuda_graphs = False
    model.change_decoding_strategy(cfg)
    before = evaluate(model, audio, 0)
    model.load_state_dict(saved["model"])
    del saved
    after = evaluate(model, audio, step)
    a = [json.loads(s) for s in (ROOT / "test-0.jsonl").read_text().splitlines()]
    b = [json.loads(s) for s in (ROOT / f"test-{step}.jsonl").read_text().splitlines()]
    key = lambda rs: {r["audio_filename"]: (r["audio_sha256"], r["text"]) for r in rs}
    assert key(a) == key(b) == key(e.rows("test"))
    report = {
        "before": before,
        "after": after,
        "wer_reduction_pp": 100 * (before["wer"] - after["wer"]),
        "relative_wer_reduction_percent": 100 * (1 - after["wer"] / before["wer"]),
        "paired_records_verified": 4567,
    }
    e.dump(ROOT / "test-comparison.json", report)
    md = f"# NeMo Parakeet Test 평가\n\n같은 Test 4,567개, 같은 NeMo FP32 환경. Validation으로 선택한 {step / PER:.2f} epoch 모델을 고정해 평가. 입력 ID·정답·오디오 SHA256 일치 확인.\n\n| 지표 | 사전학습 | 파인튜닝 |\n|---|---:|---:|\n| WER | {100 * before['wer']:.3f}% | {100 * after['wer']:.3f}% |\n| CER | {100 * before['cer']:.3f}% | {100 * after['cer']:.3f}% |\n\nWER {report['wer_reduction_pp']:.3f}%p 감소, 상대 오류 감소 {report['relative_wer_reduction_percent']:.2f}%.\n\nAI Hub 일부 데이터 자체 분할이며 공식 벤치마크가 아니다. 이전 실험에서도 관찰한 Test이므로 완전히 미관측한 검증으로 표현하지 않는다. 이번 Test 결과로 모델을 선택하거나 추가 학습하지 않았다.\n"
    (ROOT / "TEST-COMPARISON.ko.md").write_text(md)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
