# 저장된 모델 성능 평가

[문서 목차](../README.md)

`presentation-evaluate`는 학습된 체크포인트를 별도의 `test` 데이터에 적용하고,
영상별 예측과 분류 지표를 저장한다. 가중치를 수정하거나 최적 임계값을 탐색하지 않는다.
현재 실제 태도 라벨 데이터는 없으며, 합성 숫자 패턴으로 평가 코드의 동작을 검증했다.

## Mock 데이터로 실행

저장소 루트에서 실행한다. 출력 폴더가 이미 있으면 새 경로를 사용한다.

```sh
uv sync --locked
uv run --locked presentation-training-smoke \
  --output .local-data/presentation-attitude/evaluation-demo
uv run --locked presentation-evaluate \
  --checkpoint .local-data/presentation-attitude/evaluation-demo/training/best.pt \
  --manifest .local-data/presentation-attitude/evaluation-demo/test-data/manifest.json \
  --training-manifest .local-data/presentation-attitude/evaluation-demo/data/manifest.json \
  --output .local-data/presentation-attitude/evaluation-demo/evaluation \
  --device mps
```

첫 명령은 train 8개·validation 4개로 CPU 학습하고, 다른 seed의 독립적인 test 시퀀스
4개도 생성한다. 두 번째 명령은 저장된 GRU를 MPS에 한 번 로드해 test 시퀀스를 평가한다.
이 데이터는 MediaPipe에서 추출한 영상이 아닌, 전처리 결과 형식의 합성 좌표다.

평가의 `--device` 기본값은 `auto`이며 MPS가 가능하면 MPS, 아니면 CPU를 선택한다.
`--device mps`를 명시했는데 사용할 수 없으면 오류를 낸다. CPU는 `--device cpu`로 선택한다.
이번 검증은 CPU 학습과 CPU·MPS 평가를 확인했으며 MPS 학습 검증을 의미하지 않는다.

## 실제 평가 데이터 준비

`--manifest`에는 **test split만 담긴 별도 manifest**를 전달한다.
`--training-manifest`에는 체크포인트를 만들 때 사용한 train·validation manifest를 전달한다.
각 `sequence_dir`는 완료된 영상 처리 출력(`sequence.jsonl`, `summary.json`)을 가리킨다.
경로는 manifest 파일이 있는 폴더 기준이다.

아래는 실데이터용 형식 예시이며, 실제 확보된 자료가 아니다.

```json
{
  "schema_version": 1,
  "purpose": "attitude_training",
  "samples": [
    {
      "id": "heldout_001",
      "sequence_dir": "sequences/heldout_001",
      "speaker_id": "new_speaker",
      "source_video_id": "new_source",
      "source_kind": "real",
      "annotation_status": "reviewed",
      "training_eligible": true,
      "label": 1,
      "split": "test"
    }
  ]
}
```

공통 manifest 검증을 사용하므로 평가 자료도 사람이 검토한 `reviewed`, `training_eligible=true`
상태여야 한다. 이는 데이터의 이용 조건이나 라벨 적합성을 코드가 인증한다는 뜻은 아니다.
라벨은 0=`inappropriate`, 1=`appropriate`다. Mock은 `purpose=pipeline_smoke`와
`source_kind=synthetic_test`, `test_pattern_a/b`를 사용하며 실데이터와 섞지 않는다.

평가 전에 다음을 검사한다.

- 원래 학습 manifest의 해시가 체크포인트와 일치하는지.
- train·validation과 test 사이에 ID, 출력 폴더, 발표자, 원본 ID, 원본 해시 또는 특징 시퀀스 해시가 겹치는지.
- 체크포인트와 입력 데이터의 목적, 라벨 매핑, 특징 설정이 일치하는지.
- 시퀀스 해시, 좌표·결측 마스크·시각·프레임 수가 유효한지.

새 체크포인트는 학습 시점의 샘플 출처와 메타데이터 해시도 보관한다. 평가 때 이를 대조해
학습 후 데이터 설명이 바뀐 경우 거절한다. 이전 체크포인트는 이 스냅샷이 없으므로 현재 제공된
학습 자료의 메타데이터에 의존하며, 결과의 `provenance_basis`에 이 차이를 기록한다.
검사는 기록된 ID와 해시를 대조하는 것으로, 잘못 기록된 발표자 ID나 재인코딩된 동일 영상까지
자동으로 알아내지는 않는다. 데이터 분할 자체는 사람이 정확히 관리해야 한다.

## 결과 읽기

| 파일 | 내용 |
|---|---|
| `summary.json` | 실행 상태, 장치, 입력·구현 해시, 라벨 매핑, 전체 지표와 혼동행렬 |
| `predictions.jsonl` | 영상당 정답, 예측, 양성 클래스 확률, 프레임 수, 정답 여부 |
| `misclassifications.jsonl` | 오분류된 영상만 같은 형식으로 저장. 없으면 빈 파일 |

`summary.json`의 `metrics`에는 accuracy, precision, recall, F1, macro F1, ROC-AUC와 클래스별
precision·recall·F1·support가 있다. 대표 precision·recall·F1의 양성 클래스는 **1**이다.
따라서 실제 태도 모델에서는 적절한 태도에 대한 값이며, 부적절한 태도 검출률은
`per_class["0"].recall`에서 확인한다.

혼동행렬은 행=정답, 열=예측, 클래스 순서 `[0, 1]`인 `[[TN, FP], [FN, TP]]`다.
평가 단위는 프레임이 아닌 영상 하나다. 단일 클래스의 test도 허용하며 분모가 0인 지표는
`null`로 남긴다. 클래스별 F1 중 하나라도 정의되지 않으면 macro F1도 `null`이다.

임계값은 기본 0.5이며 `--threshold`로 지정한다. 확률이 임계값 이상이면 클래스 1이다.
임계값은 validation에서 정하고 test에서는 고정해 평가한다. 출력 확률의 보정 여부는 검증하지 않았다.

`metrics.roc_auc`는 클래스 1의 예측 확률로 계산하며 `--threshold`와 무관하다.
양성 영상이 음성 영상보다 높은 점수를 받은 비율로 계산하고, 동점은 0.5로 반영한다.
완벽한 순위 구분은 1.0, 모두 동점인 경우는 0.5, 완전히 뒤집힌 순위는 0.0이다.
test에 한 클래스만 있으면 정의할 수 없으므로 `null`을 저장한다. ROC 곡선 이미지는 생성하지 않는다.

입력 사전 검사에서 실패하면 출력 폴더를 만들지 않는다. 추론 도중 손상된 입력이나 전체 결측
영상을 만나면 일부 영상을 제외한 지표를 발표하지 않고 실행을 실패 처리한다.
`status=failed`, `metrics=null`과 오류를 남기며 진행 중 예측은 `.partial` 파일로 보존한다.
기본 `--max-frames 10000` 초과 입력은 임의로 자르지 않고 거절한다.

## 확인한 범위

2026-09-08 Apple M4, Python 3.13.15, PyTorch 2.14.0에서 평가 관련 테스트 11개를 포함한
비전 테스트 66개를 통과했다. 설치된 CLI로 독립 합성 test 4개를 CPU와 MPS에서 평가했다.
정확도·F1은 모두 1.0이지만 구분하기 쉽게 만든 숫자 패턴에 대한 결과이며 실제 태도 성능이 아니다.
이 명령은 분류 성능 평가용이며 처리 지연·처리량 벤치마크는 포함하지 않는다.

[실행 검증 기록](../history/evaluation_results.json)에 결과와 검증 범위를 남겼다.

같은 날 ROC-AUC를 추가한 뒤 테스트 68개와 Ruff 검사를 통과했다. 완벽한 순위·역순·동점·
혼합 순위·단일 클래스와 임계값 독립성을 검사했고, MPS CLI 실행의 합성 test ROC-AUC는 1.0이었다.
해당 결과는 저장소 루트 `.local-data/evaluation-cli-check-20260908/evaluation-roc-auc-mps/summary.json`에 있다.
