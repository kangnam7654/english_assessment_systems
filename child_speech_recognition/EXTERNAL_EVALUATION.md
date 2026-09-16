# External child-speech evaluation

**Portfolio decision:** retain the Korean-adapted model and its original Korean Test
report. Keep these experiments as supplementary evidence; no additional adaptation
is planned. Public audio availability does not determine the training target.

We first evaluate the frozen pretrained and Korean-adapted Parakeet checkpoints
on **all official speechocean762 Test speakers under 18**, rather than interpreting
five demo recordings as a benchmark. This is Mandarin-L1 English, a different domain
from the Korean AI Hub experiment. Supplied reading prompts are retained; they are
not independently adjudicated verbatim transcripts.

## Data boundaries

- Source revision: `613968e3b0b789fc33936fb5eba1973176ba7d11`.
- Only child audio is downloaded to `.local-data/speechocean762`.
- Official Test remains fixed, including the five public demo files.
- Official Train is split by speaker within each age: approximately 20% of speakers
  are held out for Validation, with at least one when an age has multiple speakers.
  Singleton ages stay in Train. Seed: `20260916`.
- Speaker IDs and exact audio hashes must be disjoint across all three splits.
- Full evaluation does not alter the existing Korean checkpoint or Test results.

## Run

Use the existing CUDA/NeMo environment in [EXPERIMENTS.md](EXPERIMENTS.md).

```sh
python child_speech_recognition/scripts/prepare_speechocean.py
python child_speech_recognition/scripts/evaluate_speechocean.py
```

Manifests, protocol and audio remain in `.local-data/speechocean762`. Predictions
and aggregate comparison are written to `.local-data/asr-speechocean`.

## Initial full Test result

| Official Test children: 1,280 utterances / 64 speakers | Pretrained | Korean-adapted |
|---|---:|---:|
| WER | 24.37% | 24.02% |
| CER | 15.18% | 14.70% |
| Word errors / 7,266 reference words | 1,771 | 1,745 |

The full subset shows a small improvement, unlike the five demo utterances.
This descriptive difference has not been tested for statistical significance.
[Exact result and split hashes](results/speechocean-test.json)

## Mixed adaptation protocol

- Start from the existing Korean-adapted step-28314 model; preserve that model.
- Official Train children: 900 utterances / 45 speakers / 0.872 hours.
- Held-out Validation: 260 utterances / 13 speakers / 0.256 hours.
- Three epochs, each with all 900 child utterances and 900 randomly sampled Korean
  Train utterances, shuffled together. Korean samples are redrawn each epoch;
  they are unique within an epoch but can recur across epochs. Seed 20260916.
- AdamW at 1e-5, microbatch 1, accumulation 4, FP32, frozen BatchNorm statistics,
  native dropout, no SpecAugment, matching the previous recipe.
- Evaluate both full Validation sets at epoch 0 and after each epoch.
- Select the lowest arithmetic mean of the two Validation WERs, including epoch 0.
  Exclude a candidate if Korean Validation WER worsens by more than 0.5 percentage
  points from epoch 0. This is an engineering guardrail, not statistical significance.
- Once selected, evaluate each fixed Test separately. No Test-based checkpoint
  selection, example replacement, or automatic hyperparameter search.

```sh
python child_speech_recognition/scripts/adapt_speechocean.py
```

The script refuses to overwrite an existing experiment. Outputs go to
`.local-data/asr-speechocean-adaptation`. This is a short continuation experiment;
it does not include a matched Korean-only continuation control, so it cannot
isolate the causal contribution of the new data from additional training.

## Completed adaptation result

| Added epochs | Korean Validation WER | Ocean Validation WER | Selection |
|---:|---:|---:|---|
| 0 | 10.777% | 19.700% | **Retained** |
| 1 | 11.243% | 19.843% | Worse mean WER |
| 2 | 11.329% | 18.273% | Korean regression exceeds guardrail |
| 3 | 11.421% | 16.631% | Korean regression exceeds guardrail |

The small dataset produced an improvement on its held-out Validation speakers,
with a trade-off in Korean performance. This bounded experiment therefore retains
the previous model. It does not establish that adaptation cannot work with another
recipe. Test was evaluated only for the selected epoch-0 model, not the rejected
candidates. [Full metrics](results/speechocean-adaptation.json)

The selected model's repeat Test WER was 8.4936% on Korean and 24.0160% on Ocean.
The original Korean Test report remains 8.4970% (8.50% rounded); it is not replaced
by the slightly different repeat result. Small decode variation was observed on
repeat evaluation; no improvement is claimed for an unchanged model. The cause
of this variation has not been isolated. All 725 state tensors match the original
model exactly, all 4,567 Korean Test records have identical references and audio
hashes, and 9 raw hypotheses changed on repeat.
[Verification record](results/speechocean-verification.json)

All three epochs and both final Test evaluations are complete. No training remains
running. Experiment files and checkpoints remain in the private remote run folder.

## Label audit follow-up

[Read-only label audit](LABEL_AUDIT.md): all 2,440 child labels checked structurally,
105 recordings cross-checked with independent Whisper. The audit established no
human-confirmed corrections. A separate machine-label version was subsequently
created as described below; the original metrics remain unchanged.

## Whisper-label re-evaluation

Using a separate version of machine-generated Whisper labels, the same two frozen
models were evaluated again on the same 1,280 recordings: WER **25.03% / 25.62%**
(pretrained / Korean-adapted). This is a separate reference version; it does not
replace original-label metrics. [Protocol and interpretation](WHISPER_LABELS.md).
