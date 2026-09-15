# Child Speech Recognition

[한국어](README.ko.md)

**Adapting English ASR to Korean children's speech.**

Parakeet fine-tuning reduced word error rate from **14.45% to 8.50%** on a fixed
4,567-utterance Test split — a **41.2% relative reduction in word errors**.

This project reconstructs a Creverse task: improving transcription for non-native
children. These are new experiments using AI Hub data, not results from the
historical company system. No company code or private company data are included.

## Result

| Fixed Test · 7.41 hours | Pretrained Parakeet | Fine-tuned Parakeet |
|---|---:|---:|
| Word error rate ↓ | 14.45% | **8.50%** |
| Character error rate ↓ | 8.14% | **4.54%** |

The checkpoint was selected at **2.75 epochs using Validation WER (10.78%)**.
The same Test audio, reference text and normalization were used before and after.
The Test result is below 10%; the Validation target of below 10% was not reached.

[Exact metrics](results/test.json) · [Validation curve](results/validation.json) ·
[Experiment details](EXPERIMENTS.md)

## What changed in the transcripts?

Actual model outputs on four Test recordings:

| Before | After | Reference-based word errors |
|---|---|---:|
| It was my favourite sandwich. | It was my favorite sandwich. | 1 → 0 |
| Also there are yummy pizza trees in it. | Also, there are yummy pizza cheese in it. | 1 → 0 |
| Grandpa's house is in Soul. | Grandpa's house is in Seoul | 1 → 0 |
| And Grandpa read me a book. | And grandpa reads me a book | **0 → 1** |

Three improvements and one regression were deliberately selected for illustration;
these examples are not a random sample. The first is a spelling-convention change,
not proof of better acoustic recognition. Reference labels are supplied dataset
labels, not newly adjudicated transcripts. [Selection rule and outputs](results/examples.json)

**Listen locally:** the [example builder](scripts/build_examples.py) creates an HTML
page containing those recordings, references and predictions. AI Hub's
[FAQ](https://www.aihub.or.kr/aihubnews/faq/list.do) permits sharing research outputs
but restricts redistribution of source data. AI Hub audio and reference-label files are
therefore excluded from this repository.

```sh
python3 child_speech_recognition/scripts/build_examples.py \
  --before .local-data/asr-nemo/test-0.jsonl \
  --after .local-data/asr-nemo/test-28314.jsonl \
  --audio-zip .local-data/aihub541/VS_eng_free_01.zip \
  --private-output .local-data/asr-listening \
  --public-output child_speech_recognition/results/examples.json
```

Open `.local-data/asr-listening/index.html` locally. Do not upload the generated page:
it embeds the original audio. Access to the dataset and local prediction files is required.

## Public audio samples

Listen to [five speechocean762 child recordings](samples/speechocean762/README.md)
(ages 6–10, Mandarin first language). WAV files, a local browser player, references,
and CC BY 4.0 attribution are included. These external demo samples are separate
from the AI Hub Test results above. On these five recordings, word errors increased
from 8 to 9 (WER 28.57% → 32.14%); all paired outputs are included.

## Pipeline

```text
Authorized AI Hub audio + cleaned, fixed split manifests
    → native NeMo Parakeet + AdamW
    → Validation every 0.25 epoch → best checkpoint
    → fixed Test before/after → metrics + private listening examples
```

Training uses NVIDIA's native NeMo model and CUDA TDT loss inside an explicit
PyTorch training loop. It does not use Lightning Trainer. BatchNorm running
statistics are frozen; model weights remain trainable.

## Code and reproduction

| Location | Purpose |
|---|---|
| `scripts/runtime.py` | Model, tokenizer, audio loading and TDT loss |
| `scripts/train.py` | Three-epoch training, checkpointing and Validation selection |
| `scripts/evaluate_test.py` | Evaluate the selected checkpoint against its pretrained baseline |
| `scripts/build_examples.py` | Paired-output checks and private audio examples |
| `results/` | Small public metrics and model-output excerpts |

See [environment and run instructions](EXPERIMENTS.md#run-the-code). The CUDA/NeMo
runtime is separate from the monorepo's application environment. The scripts were
extracted from the completed experiment and checked after relocation; a fresh
three-epoch run of this reorganized copy has not been performed.

## Scope of the evidence

The data are a locally repartitioned subset of **AI Hub 541, 학습용 아동 영어 음성 데이터**,
not an official AI Hub benchmark. Training used 41,183 utterances (58.87 hours).
Speaker separation uses a conservative metadata proxy, not independently verified
speaker identities. This Test had also been observed in earlier experiments;
it is not a new, untouched external evaluation. A single split and seed do not
establish performance for every child, accent or classroom.

Source: [AI Hub dataset](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=541) ·
[Parakeet model and license](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
