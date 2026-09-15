# 아동 영어 음성 인식

[English](README.md)

**한국 아동의 영어 음성에 맞춰 ASR 모델을 파인튜닝했습니다.**

고정된 Test 음성 4,567개에서 Parakeet의 단어 오류율을 **14.45% → 8.50%**로
낮췄습니다. 단어 오류가 상대적으로 **41.2% 감소**한 결과입니다.

크레버스에서 수행했던 비원어민 아동 음성 전사 개선 업무를 재구현한 프로젝트입니다.
아래 결과는 AI Hub 데이터로 새롭게 진행한 실험이며, 당시 회사 시스템의 성능이 아닙니다.
회사 코드와 내부 데이터는 포함하지 않습니다.

## 결과

| 고정 Test · 7.41시간 | 학습 전 | 학습 후 |
|---|---:|---:|
| 단어 오류율 WER ↓ | 14.45% | **8.50%** |
| 문자 오류율 CER ↓ | 8.14% | **4.54%** |

**Validation WER 10.78%를 기록한 2.75 epoch 모델**을 선택한 뒤 Test를 평가했습니다.
전후에 동일한 음성·정답·텍스트 정규화를 사용했습니다.
Test에서는 10% 미만을 달성했지만, Validation의 10% 미만 목표는 미달입니다.

[정확한 평가 수치](results/test.json) · [학습 중 평가 기록](results/validation.json) ·
[실험 설정과 실행 방법](EXPERIMENTS.md)

## 실제 전사는 어떻게 달라졌나요?

Test 녹음에 대한 실제 모델 출력입니다.

| 학습 전 | 학습 후 | 정답 라벨 기준 단어 오류 수 |
|---|---|---:|
| It was my favourite sandwich. | It was my favorite sandwich. | 1 → 0 |
| Also there are yummy pizza trees in it. | Also, there are yummy pizza cheese in it. | 1 → 0 |
| Grandpa's house is in Soul. | Grandpa's house is in Seoul | 1 → 0 |
| And Grandpa read me a book. | And grandpa reads me a book | **0 → 1** |

설명을 위해 개선 사례 3개와 악화 사례 1개를 골랐으며 무작위 표본은 아닙니다.
첫 사례는 미국식·영국식 철자 차이이므로, 음향 인식 능력의 개선으로 단정할 수 없습니다.
정답은 제공된 데이터셋 라벨이며, 새로 사람이 검수한 전사는 아닙니다.
[예시 선택 기준과 출력](results/examples.json)

**음성은 로컬에서 직접 들어볼 수 있습니다.**
AI Hub [공식 FAQ](https://www.aihub.or.kr/aihubnews/faq/list.do)는 연구 결과물의 공유와
원본 데이터 재배포를 구분합니다. 따라서 공개 저장소에는 원본 음성·정답 라벨 파일을 넣지 않고,
승인받아 보유한 데이터를 이용해 오디오·정답·전사 결과가 담긴 HTML 페이지를 만듭니다.

```sh
python3 child_speech_recognition/scripts/build_examples.py \
  --before .local-data/asr-nemo/test-0.jsonl \
  --after .local-data/asr-nemo/test-28314.jsonl \
  --audio-zip .local-data/aihub541/VS_eng_free_01.zip \
  --private-output .local-data/asr-listening \
  --public-output child_speech_recognition/results/examples.json
```

생성된 `.local-data/asr-listening/index.html`을 브라우저에서 열면 됩니다.
페이지 안에 원본 음성이 포함되므로 HTML도 공개 업로드하지 않습니다.
데이터 접근 권한과 로컬 평가 출력 파일이 필요합니다.

## 처리 흐름

```text
AI Hub 음성 + 정제된 고정 Train/Validation/Test 목록
    → NeMo Parakeet + AdamW 학습
    → 0.25 epoch마다 Validation 평가 → 최고 모델 선택
    → 고정 Test 전후 비교 → 수치와 로컬 청취 예시
```

NeMo 모델과 CUDA TDT loss를 사용하며, 학습 순서는 명시적인 PyTorch 루프로 관리합니다.
Lightning Trainer를 사용하는 구조는 아닙니다.
BatchNorm의 통계는 고정하고 모델 가중치는 학습합니다.

## 코드 구성

| 위치 | 역할 |
|---|---|
| `scripts/runtime.py` | 모델·토크나이저·음성 로딩·TDT loss |
| `scripts/train.py` | 3 epoch 학습·체크포인트·Validation 모델 선택 |
| `scripts/evaluate_test.py` | 선택한 모델과 사전학습 모델의 Test 비교 |
| `scripts/build_examples.py` | 전후 출력 검증·로컬 오디오 예시 생성 |
| `results/` | 공개 가능한 집계 지표와 모델 출력 예시 |

[실행 방법](EXPERIMENTS.md#run-the-code)을 참고하세요.
NeMo CUDA 환경은 모노레포의 애플리케이션 환경과 분리했습니다.
완료된 실험에서 코드를 추출해 경로를 정리하고 검증했으며,
정리된 사본으로 3 epoch 전체를 새로 학습하지는 않았습니다.

## 결과를 해석할 때

데이터는 **AI Hub 541, 학습용 아동 영어 음성 데이터**의 일부를 자체 분할한 것으로,
공식 벤치마크 점수가 아닙니다. Train은 41,183개, 약 58.87시간입니다.
화자는 메타데이터 기반의 보수적인 그룹으로 분리했으며 실제 동일인 여부를 별도로 검증하지는 않았습니다.
Test는 이전 실험에서도 관찰했던 세트이므로 완전히 새로운 외부 검증은 아닙니다.
단일 분할·seed 결과를 모든 아동·발음·교실 환경으로 일반화할 수는 없습니다.

출처: [AI Hub 데이터셋](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=541) ·
[Parakeet 모델·라이선스](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
