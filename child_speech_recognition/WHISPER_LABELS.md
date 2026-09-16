# Whisper-derived labels / Whisper 자동 전사 라벨

A separate experiment uses Whisper transcripts as labels for **all 2,440 child
recordings**. This version is `whisper-v1`; it is not a human-adjudicated correction
set and does not certify that every generated word is correct.

- Model: `openai/whisper-large-v3-turbo`, revision
  `41f01f3fe87f28c78e2fbf8b568835947dd65ed9`.
- Audio-only transcription, English, greedy generation, FP32, batch size 8,
  maximum 128 new tokens. No original text is passed to the model.
- Same audio, IDs, speakers and Train/Validation/Test membership as before.
- New manifests use Whisper output in `text`, source text in `original_text`,
  and explicit `label_source` / `label_revision` fields.
- Original manifests, public source transcripts and previously reported metrics
  remain unchanged. Digit formatting and names follow Whisper output.
- Empty or potentially capped outputs stop the run for investigation. Outputs
  are resumable and the final manifests are emitted after coverage checks pass.

## Generate

In the existing CUDA Transformers environment, with the original audio and cached
model available:

```sh
python -m child_speech_recognition.scripts.data.relabel_speechocean
```

Output: `.local-data/speechocean-whisper-v1/` on `ciot-workstation`.
It contains new split manifests, raw predictions, generation protocol, provenance,
a source-audio symlink and a completion summary. Original data remains in
`.local-data/speechocean762/`.

## Use the new labels explicitly

Evaluation with these labels is complete; training with them has not been run.
The commands below document reproduction and optional future training. Label
generation itself does not start either step.

```sh
export SPEECHOCEAN_DATA_DIR="$PWD/.local-data/speechocean-whisper-v1"
export SPEECHOCEAN_EVAL_DIR="$PWD/.local-data/asr-speechocean-whisper-v1"
export SPEECHOCEAN_ADAPT_DIR="$PWD/.local-data/asr-speechocean-whisper-v1-adaptation"
python -m child_speech_recognition.scripts.evaluation.evaluate_speechocean
python -m child_speech_recognition.scripts.training.adapt_speechocean
```

The new output directories prevent the old evaluation and adaptation records from
being replaced. Baseline evaluation precedes adaptation so the same new Test
references are used for both models.

**평가 해석:** 새 Test의 WER은 Whisper가 만든 문장과 모델 출력의 일치도입니다.
사람이 확정한 전사 기준 성능과 구분해야 하며, 기존 라벨의 WER과 직접 비교해
모델이 좋아졌다고 주장하지 않습니다. 같은 새 라벨로 기존 모델부터 다시 평가해야 합니다.

Source audio and original annotations: [speechocean762](https://www.openslr.org/101/),
Junbo Zhang et al. (2021), CC BY 4.0. The original source attribution is retained;
replacement text is explicitly marked as machine-generated.

## Completed replacement

| Split | Records | Changed after existing text normalization |
|---|---:|---:|
| Train | 900 | 444 |
| Validation | 260 | 120 |
| Test | 1,280 | 735 |
| Total | 2,440 | 1,299 |

All 2,440 `text` fields now use Whisper output in the new version. The remaining
1,141 differ only in formatting under existing normalization. Changed counts are
not a count of proven errors fixed; number/name conventions may also differ.
Split order, IDs, speaker metadata, audio hashes and original text were verified.
No empty outputs remain. No training was run. The subsequent evaluation is recorded below.
[Exact summary and manifest hashes](results/whisper-labels.json)

## Evaluation against Whisper labels (2026-09-16)

Same 1,280 Test recordings, greedy-batch NeMo FP32 decoding, and existing text
normalization. No new training: compare the original pretrained model with the
previously selected Korean-adapted step-28314 checkpoint.

| Metric | Pretrained Parakeet | Korean-adapted Parakeet |
|---|---:|---:|
| WER | 25.03% | 25.62% |
| CER | 16.67% | 16.83% |
| Word errors / 7,267 reference words | 1,819 | 1,862 |

The adapted model has 43 more word errors (+0.592 percentage points WER) against
these machine references. This is not evidence of a training change: the weights
are unchanged. Original-label WER remains 24.37% / 24.02%. Changing the references
changes the metric and can reverse the ranking. Neither label set is established
as fully correct by this comparison.

Re-scoring the previous saved hypotheses against the new labels reproduces both
new WER values exactly, isolating the reference change from repeat-inference
variation in the aggregate WER. Paired IDs, audio hashes, references and metric
arithmetic were verified for all 1,280 records.

[Exact metrics](results/speechocean-whisper-test.json) ·
[Pairing and fixed-hypothesis checks](results/speechocean-whisper-test-verification.json)
