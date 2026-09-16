# Experiment record

[English overview](README.md) · [한국어 개요](README.md)

## Data and selection

| Split | Utterances | Hours | Metadata speaker groups |
|---|---:|---:|---:|
| Train | 41,183 | 58.87 | 84 |
| Validation | 5,178 | 7.16 | 10 |
| Test | 4,567 | 7.41 | 10 |

Source: the downloaded **official Validation free-speech subset** of AI Hub 541,
repartitioned locally. This is not the provider's official Train/Test protocol.
84 recordings containing a standalone `NNN`-style marker were excluded. Only two
explicit typographical label corrections were approved; grammar and ambiguous
word choices were retained. Split construction used seed 20260911; training order
used seed 20260912. Audio hashes, conservative speaker groups and split disjointness
were checked. The historical review decisions and full split manifests remain private.

Training scripts require the exact prepared manifests, checked against
[recorded hashes](results/protocol.json). This repository does not reconstruct the
entire historical manual-review process from a new download.

## Experiments completed

All values below are **Validation WER** unless marked otherwise.

| Experiment | Best / designated WER | Decision |
|---|---:|---|
| Granite, AdamW, one epoch | 14.940% | Baseline for Granite experiments |
| Granite, short → medium → long, one epoch | 15.296% | Did not help |
| Granite, AdamW, up to three epochs | 13.522% | Best at 2.75 epochs |
| Parakeet, Transformers, three epochs | 11.101% | Best at epoch 3 |
| **Parakeet, NeMo, three epochs** | **10.777%** | **Selected at 2.75 epochs** |
| NeMo, warmup + cosine, peak LR 1e-4 | 11.083% | Retained the constant-LR model |

The peak-1e-5 scheduler trial was stopped early when the peak was changed to 1e-4;
it is not a completed comparator. The 1e-4 experiment changes both peak learning
rate and schedule relative to constant 1e-5; it does not isolate the scheduler effect.
No more training is running for this work. Historical artifacts are preserved under
local `.local-data` directories, outside Git.

## Selected NeMo recipe

- NVIDIA Parakeet TDT 0.6B v2, revision `ae9ad07059c7c739ffaf932226a8fe64ae2620b0`.
- RTX 5090; Python 3.13.14; PyTorch 2.14.0+cu130; NeMo 3.0.0.
- AdamW: LR 1e-5, betas (0.9, 0.999), eps 1e-8, weight decay 0; gradient clipping 1.
- FP32; TF32 disabled; microbatch 1, gradient accumulation 4.
- One epoch = 10,296 updates. Final partial batch has 3 utterances, scaled by 3.
- Same seeded shuffled order repeated each epoch. 72 BatchNorm buffers fixed;
  all model parameters trainable. Zero loss is valid; nonfinite/negative loss is rejected.
- Native NeMo dropout retained. SpecAugment and dither disabled. CUDA TDT loss:
  mean reduction, sigma 0, omega 0. No LR scheduler in the selected run.
- Validation every 2,574 updates; minimum Validation WER selects the checkpoint.
- Explicit PyTorch loop calling NeMo encoder, decoder, joint and CUDA loss;
  not the Lightning Trainer or an unmodified official training recipe.

Native NeMo and the Transformers port differ in dropout and implementation details.
Their pretrained Validation WER matched, but training differences cannot be attributed
solely to the loss backend.

## Speed

The same first 30 update batches were compared, with the first 5 excluded as warmup:
**0.740 seconds/update in Transformers versus 0.225 in NeMo (3.28×)**.
Both used FP32, microbatch 1 and accumulation 4. NeMo peak allocated memory was
10.06 GiB. This is a short training measurement, not whole-job speed or inference RTFx.
[Measurements](results/speed.json)

## Final Test

The fixed 2.75-epoch NeMo checkpoint reached **8.497% WER / 4.541% CER**, compared
with pretrained **14.448% / 8.139%**. WER decreased 5.951 percentage points,
or 41.190% relative. Corpus scores use all 4,567 utterances; they are not averages
of the four README examples. This Test was observed in prior experiments and is not
an untouched external holdout. [Machine-readable result](results/test.json)

Text normalization: lowercase; curly apostrophe → ASCII; replace punctuation other
than apostrophes with spaces; collapse whitespace. No spelling, number or contraction
normalization. Thus `favourite` versus `favorite` is counted as a word error.

## Run the code

Use a **separate Linux/CUDA environment**. This runtime is not installed by root
`uv sync`; NeMo and the application dependencies have different requirements.
A complete package snapshot is in `requirements-nemo.lock.txt` as an environment
record, not a drop-in solver input: the historical torchaudio pairing was installed
without dependencies and tested for this workflow, not certified as generally compatible.

From the repository root on the CUDA host:

```sh
uv venv --python 3.13 .local-data/asr-nemo-venv
uv pip install --python .local-data/asr-nemo-venv/bin/python \
  'torch==2.14.0' --index-url https://download.pytorch.org/whl/cu130
uv pip install --python .local-data/asr-nemo-venv/bin/python \
  'nemo_toolkit[asr]==3.0.0' 'numba-cuda[cu13]' 'cuda-python>=13,<14' \
  'transformers==5.17.0' 'numpy==2.3.5' jiwer
uv pip install --python .local-data/asr-nemo-venv/bin/python --no-deps \
  'torchaudio==2.11.0' --index-url https://download.pytorch.org/whl/cu130
.local-data/asr-nemo-venv/bin/hf download nvidia/parakeet-tdt-0.6b-v2 \
  parakeet-tdt-0.6b-v2.nemo --revision ae9ad07059c7c739ffaf932226a8fe64ae2620b0
```

Prepare authorized `VS_eng_free_01.zip` and the recorded `splits/{train,validation,test}.jsonl`
in the data directory. Reference manifests and checkpoints are not distributed here.
Choose a new run directory to keep historical experiments intact:

```sh
export ASR_DATA_DIR="$PWD/.local-data/aihub541"
export ASR_RUN_DIR="$PWD/.local-data/asr-nemo-reproduction"
.local-data/asr-nemo-venv/bin/python -m child_speech_recognition.scripts.training.train
# Run only after Validation selection is final:
.local-data/asr-nemo-venv/bin/python -m child_speech_recognition.scripts.evaluation.evaluate_test
```

`best.pt` holds the selected model; `resume.pt` stores model, optimizer, RNG and history.
Checkpoints are local trusted files. Restarting resumes the last saved quarter-epoch;
unsaved log rows are preserved separately and replayed. Keep the run directory private:
it contains predictions with reference labels.

Dependency-free report checks:

```sh
python3 -m unittest discover -s child_speech_recognition/tests
```
