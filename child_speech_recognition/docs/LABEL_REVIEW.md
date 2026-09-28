# 라벨 검수

[← 한국어 개요](../README.md) · [English: Label review](EXPERIMENTS.md#label-review)

## 이번 실험에서 한 일

AI Hub 541의 공식 Validation 자유발화 라벨 중 텍스트에서 명백한 표기 오류 2건을
사람이 승인해 고쳤습니다. 이때는 해당 음성을 직접 확인하지 않았습니다. 이후 표본 70개를
로컬 Whisper로 전사해 라벨과 대조했습니다. Whisper 결과는 검토할 대상을 찾는 참고
자료로만 썼고, 전사 결과로 원본 라벨을 자동 교체하지 않았습니다. `NNN` 표식 84건은
정답을 추측하지 않고 제외했습니다. 문법이나 단어 선택이 애매한 경우는 그대로 뒀습니다.

아래 스크립트는 이 규칙을 **새로 재사용 가능하게 정리한 것**입니다. 당시 학습에 쓴
비공개 승인 파일이나 고정 데이터 분할을 복원하는 스크립트는 아닙니다.

## 스크립트가 동작하는 순서

1. `queue`가 원본 라벨 ZIP의 JSON을 읽고, 독립 ASR 전사가 있으면 함께 비교합니다.
   `NNN` 표식, 연속 작은따옴표 `''`, ASR 전사와의 불일치가 있는 라벨을
   `review-queue.jsonl`에 모읍니다. **이 단계에서는 어떤 라벨도 바꾸지 않습니다.**
2. 검토자가 후보의 원본 라벨과 음성을 살펴보고, 수정할 항목만 별도 결정 파일에
   `approved`로 적습니다. ASR과 다르다는 사실만으로 수정하지 않습니다.
3. `apply`가 라벨 ZIP의 SHA-256과 수정 전 문장을 결정 파일과 대조합니다. 일치하는
   승인 항목만 `eligible.jsonl`에 반영하고 `NNN` 표식은 `excluded.jsonl`로 보냅니다.
   원본 ZIP을 덮어쓰거나 기존 출력 디렉터리에 다시 쓰지 않습니다.

예를 들어 아래는 **가상의 문장**입니다. 실제 AI Hub 원문이나 당시의 승인 내역이 아닙니다.

| 원본 라벨 | 독립 ASR 또는 검토 결과 | 결정 | 최종 처리 |
|---|---|---|---|
| `I can spel.` | `I can spell.` | 오타 확인 후 승인 | `I can spell.` |
| `NNN sees a rose.` | 정답 불명 | 수정하지 않음 | 제외 |
| `I saw a tree.` | ASR: `I see a tree.` | 발음만으로 확정 불가 | 원본 유지 |

## 실행하기

저장소 루트에서 실행합니다. 접근 권한이 있는 라벨 ZIP을 `.local-data/aihub541/`에
준비하세요. 예측 JSONL은 선택 사항이며, 각 줄에 `audio_filename`(또는 `audio`)과
`hypothesis`가 있어야 합니다. 예측 파일을 생략해도 `NNN`·연속 작은따옴표는 검사합니다.

```sh
export ASR_DATA_DIR="$PWD/.local-data/aihub541"
PYTHONPATH=child_speech_recognition/src python3 -m child_speech.cli.review_labels queue \
  --labels "$ASR_DATA_DIR/VL_eng_free_01.zip" \
  --suggestions "$ASR_DATA_DIR/local-asr-predictions.jsonl" \
  --output-dir "$ASR_DATA_DIR/review-queue-new"
```

예측 파일이 없으면 `--suggestions` 옵션을 제거합니다. 실행 결과의 `summary.json`에서
`source_sha256` 값을 확인하고, 사람이 검토해 승인한 변경만 다음 형식의 **비공개**
`approved-decisions.json`에 기록합니다.

```json
{
  "source_sha256": "<summary.json의 source_sha256 값>",
  "corrections": [
    {
      "audio_filename": "example.wav",
      "before": "I can spel.",
      "after": "I can spell.",
      "reason": "검토자가 확인한 명백한 철자 오류",
      "status": "approved"
    }
  ]
}
```

이 JSON도 형식을 보여주는 가상 예시입니다. 실제 파일명·문장은 자신의 데이터에 맞게
입력해야 합니다. 수정할 항목이 없으면 `corrections`를 빈 배열로 둡니다.

```sh
PYTHONPATH=child_speech_recognition/src python3 -m child_speech.cli.review_labels apply \
  --labels "$ASR_DATA_DIR/VL_eng_free_01.zip" \
  --decisions "$ASR_DATA_DIR/approved-decisions.json" \
  --output-dir "$ASR_DATA_DIR/curated-new"
```

결과의 `eligible.jsonl`은 사용할 수 있는 라벨, `excluded.jsonl`은 제외한 라벨,
`summary.json`은 건수와 원본 ZIP 해시입니다. 이 파일에는 비공개 전사문이 들어 있으므로
Git에 추가하지 마세요. 이 명령은 Train/Validation/Test를 나누거나 음성 ZIP을 수정하지
않습니다. 그 데이터 준비 범위는 [README의 Data Preparation](../README.md#data-preparation)을
참고하세요.
