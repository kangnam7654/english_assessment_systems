# Public listening samples / 공개 청취 샘플

Five English recordings from Mandarin-speaking children aged 6–10.
중국어가 모국어인 6~10세 아동의 영어 음성 5개입니다.

Download this folder and open [index.html](index.html) to listen in a browser.
GitHub에서는 아래 WAV 링크로 파일을 열거나 다운로드할 수 있습니다.
폴더를 내려받아 `index.html`을 열면 연속해서 들어볼 수 있습니다.

| Audio | Age / 나이 | Duration | Dataset reference / 제공 문장 |
|---|---:|---:|---|
| [000030012](000030012.wav) | 6 | 3.36s | MARK IS GOING TO SEE ELEPHANT |
| [000490017](000490017.wav) | 7 | 4.71s | DORA CAN SEE THE SHEEP |
| [010500012](010500012.wav) | 8 | 2.74s | JAYME CAN PAINT THE PIG |
| [020140004](020140004.wav) | 9 | 2.81s | JAYME CAN DRAW THE WAR |
| [030070015](030070015.wav) | 10 | 3.19s | IS THERE A GOOD PLACE AT TABLE |

These are external demo samples, not the Korean AI Hub Test recordings behind
our reported 14.45% → 8.50% WER. Paired predictions are shown below.
The supplied text is preserved, including grammatical irregularities; it is not
an independently verified verbatim transcript.

기존 한국 아동 Test 성능 수치와 별개의 외부 데모입니다. 학습 전후 추론 결과는 아래에 있습니다. 제공 문장은 문법을 수정하지 않고 그대로 보존했습니다.

Selection was fixed before inference: for each age 6–10, select the first utterance
ID in sorted order with 5–12 reference words. This small sample is not a benchmark
or a representative accent/age distribution. [Provenance and checksums](manifest.json)

## Before / after inference · 학습 전후 추론

On these five fixed samples (28 reference words), **WER increased from 28.57% to
32.14% (8 → 9 word errors)**; CER decreased from 19.84% to 17.46%.
One sample improved, two regressed, and two were unchanged by word error count.

이 5개에서는 단어 오류가 **8 → 9개**로 늘었습니다. 개선 1개, 악화 2개, 동일 2개이며,
한국 아동 데이터에서의 개선이 다른 모국어 아동에게도 이어진다는 근거는 아닙니다.

| Sample | Before / 학습 전 | After / 학습 후 | Word errors |
|---|---|---|---:|
| 000030012 | Mark is going to see elephant. | Mark is going to see elephant. | 0 → 0 |
| 000490017 | Fraud can seize the sheep. | Frog can seize sheep. | 2 → 3 |
| 010500012 | Jeremy can panic pig | Jamie chimpanzee pig | 3 → 4 |
| 020140004 | Jamie can join the world. | Jamie can draw the wall. | 3 → 2 |
| 030070015 | Is there a good place at table? | Is there a good place at table? | 0 → 0 |

`JAYME` versus `Jamie` is counted as an error, even though an audio recording cannot
establish the spelling of a name. The supplied reading text may also differ from
what the child actually says. These labels have not been independently adjudicated.
표본이 28단어뿐이므로 한 단어 오류가 WER을 약 3.57%p 바꿉니다. 이름 철자 차이도
오류에 포함되며, 제공 문장과 실제 발화의 일치 여부를 별도로 청취 검수하지 않았습니다.

The original Parakeet and the Validation-selected step-28314 checkpoint used the
same NeMo FP32 greedy-batch decoder and Test text normalization. All five audio
hashes were verified. No samples were replaced after seeing the outputs.
[Exact outputs and protocol](predictions.json). The manifest records the original
pre-inference selection snapshot.

Run in the [CUDA/NeMo environment](../../EXPERIMENTS.md#run-the-code), with the
original cached model and selected checkpoint available:

```sh
python child_speech_recognition/scripts/evaluate_samples.py
```

## Attribution / 출처

**speechocean762: An Open-Source Non-native English Speech Corpus For Pronunciation
Assessment** — Junbo Zhang, Zhiwen Zhang, Yongqing Wang, Zhiyong Yan, Qiong Song,
Yukai Huang, Ke Li, Daniel Povey, and Yujun Wang, Interspeech 2021.

[Original repository](https://github.com/jimbozhang/speechocean762) ·
[OpenSLR dataset and license declaration](https://www.openslr.org/101/) ·
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

The audio and source-derived metadata in this folder are licensed under **CC BY 4.0**,
not the repository's code license. Retain attribution and the license link when
redistributing, and describe any further changes. No endorsement is implied.
Audio bytes and reference text are unchanged; the filename extension is lowercased
and the metadata is a selected subset. Source revision and individual file URLs
are recorded in the manifest.
