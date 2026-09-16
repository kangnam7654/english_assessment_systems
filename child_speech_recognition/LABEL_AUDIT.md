# speechocean762 label audit / 라벨 검수

**후속 실험:** [Whisper 라벨 버전](WHISPER_LABELS.md)을 별도로 만들었습니다.
아래 기록은 교체 전 검수 당시의 상태이며, 사람이 라벨 오류를 확정한 기록은 아닙니다.

**2026-09-16: automated inspection completed; audio adjudication pending.**
No source label was modified, and no corrected-label model was trained.

## What was checked

All **2,440 child records** (900 Train, 260 Validation, 1,280 Test) were checked
against the pinned source `scores.json`, `scores-detail.json`, and word annotations.
No empty labels, repeated-apostrophe/NNN placeholders, unexpected characters under
the recorded rule, or inconsistent source text were found. Agreement among these
files is internal consistency, not independent proof that the transcript is right.

- 73 records repeat adjacent words; 47 are number sequences. Repetition is not an error by itself.
- 222 records contain at least one word with source pronunciation accuracy <=3/10.
  These are review candidates, not automatically excluded or mislabeled examples.
- Whisper large-v3-turbo independently transcribed 100 Train/Validation samples
  stratified by split and age, plus the five public Test demos, without reference prompts.
- Of those 105, 51 matched under existing text normalization, 2 differed only by
  digit-versus-word formatting, and 52 require audio adjudication. This is not a label-error rate.

[Machine-readable counts and model revision](results/label-audit.json)

## Findings requiring care

| Source text | Whisper output | Assessment |
|---|---|---|
| JIM ATE A LITTLE TOLL FULL | James ate a little tofu. | Possible segmentation or label mismatch; neither name nor phrase corrected |
| YOU MUST DO YOU BEST | You must do your best. | Could be a missing final consonant, label error, or Whisper grammar repair |
| THE GREAT WORK IT SHALL BE CARRY ON | The great work it shall be carried on. | Inflection mismatch; keep pending |
| JAYME CAN DRAW THE WAR | Jamie can draw the world | Parakeet produced `world` / `wall`; ambiguous, no majority-vote correction |
| FIVE NINE SEVEN SEVEN | 5-9-7-7 | Formatting equivalence; no label correction needed |

The public `DORA` sample has source word accuracy 3/10. Its disagreement with
Parakeet and Whisper may reflect difficult pronunciation. `JAYME` is a valid name
spelling; its source canonical phones are JH EY1 M IY0. Replacing it with `Jamie`
would not be justified by sound alone.

**현재 확인한 것은 텍스트 구조와 자동 음성 교차검증입니다. 직접 듣고 판정한 것은 아닙니다.**
명백한 라벨 오타로 확정하여 수정한 항목은 0개입니다. 52개 불일치는 라벨 오류·실제 읽기
실수·모델 오류가 섞일 수 있어, 청취 검수 전까지 원본을 유지합니다.

## Reproduction and local review

1. Run `prepare_speechocean.py` as documented in [external evaluation](EXTERNAL_EVALUATION.md).
2. Place the three generated split JSON files in `.local-data/speechocean-audit/`.
   Download `resource/scores.json` and `resource/scores-detail.json` from the source
   revision below into the same folder. Their SHA256 hashes are in the audit result.
3. Run `python -m child_speech_recognition.scripts.data.audit_speechocean_labels`.
4. In the CUDA Transformers environment with cached Whisper weights, run
   `python -m child_speech_recognition.scripts.data.transcribe_label_audit`.
5. Copy the selected `source_path` audio files under `.local-data/speechocean-audit/`,
   preserving paths, then run `python -m child_speech_recognition.scripts.reporting.build_label_review`.

Open `.local-data/speechocean-audit/index.html` to compare audio, source text,
Whisper output, and source pronunciation scores. The queue preserves split IDs,
audio hashes, null corrections, and `audio_adjudicated: false`. No training or Test
labels are rewritten. A model disagreement must never automatically become a correction.

Source: [speechocean762 pinned revision](https://github.com/jimbozhang/speechocean762/tree/613968e3b0b789fc33936fb5eba1973176ba7d11)
· [Paper: acquisition and scoring](https://arxiv.org/html/2104.01378)
· [CC BY 4.0 dataset license](https://www.openslr.org/101/).

The paper describes reading a text script and pronunciation scoring, including
missing or incorrectly pronounced words. This makes the supplied text potentially
different from a strict verbatim ASR transcript; it does not establish that any
specific label is wrong. Grammatical oddness alone is not a correction criterion.
