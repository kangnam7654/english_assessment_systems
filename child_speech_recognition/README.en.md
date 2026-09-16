# Child Speech Recognition

[한국어](README.md)

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

## Listen with authorized data

**Listen locally:** the [example builder](scripts/reporting/build_examples.py) creates an HTML
page containing those recordings, references and predictions. AI Hub's
[FAQ](https://www.aihub.or.kr/aihubnews/faq/list.do) permits sharing research outputs
but restricts redistribution of source data. AI Hub audio and reference-label files are
therefore excluded from this repository.

<details>
<summary>Build the local listening examples</summary>

Run from the repository root with authorized AI Hub audio and the paired prediction files.

```sh
python3 -m child_speech_recognition.scripts.reporting.build_examples \
  --before .local-data/asr-nemo/test-0.jsonl \
  --after .local-data/asr-nemo/test-28314.jsonl \
  --audio-zip .local-data/aihub541/VS_eng_free_01.zip \
  --private-output .local-data/asr-listening \
  --public-output child_speech_recognition/results/examples.json
```

Open `.local-data/asr-listening/index.html` locally. Do not upload the generated page:
it embeds the original audio. Access to the dataset and local prediction files is required.
The prediction files and trained checkpoint are not bundled, so the public repository
alone cannot regenerate these exact listening examples.

</details>

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

```text
scripts/
├── data/        # Dataset preparation, label auditing and transcription
├── training/    # Baseline and mixed-domain training
├── evaluation/  # Test, public-sample and external evaluation
├── reporting/   # Listening examples and label review pages
└── common/      # Shared model and audio runtime
```

Run entry points from the repository root with `python -m child_speech_recognition.scripts.<group>.<module>`.

| Location | Purpose |
|---|---|
| `scripts/common/runtime.py` | Model, tokenizer, audio loading and TDT loss |
| `scripts/training/train.py` | Three-epoch training, checkpointing and Validation selection |
| `scripts/evaluation/evaluate_test.py` | Evaluate the selected checkpoint against its pretrained baseline |
| `scripts/reporting/build_examples.py` | Paired-output checks and private audio examples |
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

## Supplementary experiments

The final model remains the Korean-adapted checkpoint reported above. Additional
speechocean762 experiments tested transfer to Mandarin-speaking children; mixed
adaptation did not meet our Korean Validation protection criterion. Further
adaptation is paused.

- [External evaluation and mixed adaptation](EXTERNAL_EVALUATION.md)
- [Public audio demos](samples/speechocean762/README.md): a separate dataset, not the Korean Test recordings
- [Label audit](LABEL_AUDIT.md) and [Whisper-label experiment](WHISPER_LABELS.md): machine-generated references, separate from the main results
