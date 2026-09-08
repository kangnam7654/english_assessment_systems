# 작은 GRU 학습 파이프라인

[문서 목차](../README.md)

현재 단계는 모델과 학습 경로의 동작 검증이다. 실제 태도 라벨은 0건이며, 이번 학습에
사용한 데이터는 숫자로 만든 테스트용 좌표 시퀀스다. AI 생성 영상이나 사람의 발표 데이터가 아니다.
테스트 패턴을 구별하는 loss 감소를 발표 태도 분류 성능으로 해석하지 않는다.

## 모델 입력과 구조

```text
sequence.jsonl
  → 프레임별 [얼굴 XY 956 + Left XY 42 + Right XY 42 + valid 3]
  → [batch, 최대 영상 길이, 1043] + 각 영상의 실제 길이
  → packed sequence → GRU(hidden=32, 1 layer) → Linear(32, 1)
  → 영상당 logit 하나
```

`smoothed_xy`의 얼굴·Left·Right 순서로 XY를 펼친다. z와 별도의 얼굴 위치·크기 정보는
이번 기본 모델 입력에서 제외한다. 유효하지 않은 좌표는 **텐서 변환 시에만** 0을 넣고
마지막 3개 값으로 각 부위의 유효 여부를 전달한다. 원본 JSONL의 null과 raw는 수정하지 않는다.
영상 내부에서 검출이 누락된 프레임도 시간 순서와 실제 길이에 포함한다.

다른 길이의 영상을 배치로 묶기 위해 붙이는 padding은 별도 `padding_mask`로 표시한다.
`pack_padded_sequence`에 실제 길이를 전달하므로 padding은 GRU의 마지막 상태에 영향을
주지 않는다. 시각 배열도 반환하지만 현재 모델은 고정 FPS의 순서를 사용하며 시각 값을
추가 특징으로 입력하지 않는다. 모든 샘플은 FPS·전처리 설정·모델 명세가 같아야 한다.

기본 파라미터 수는 103,425개다. GRU의 최종 hidden state를 이진 분류 logit으로 바꾸고,
학습에는 `BCEWithLogitsLoss`, Adam, gradient clipping(1.0)을 사용한다.
실영상 학습 시 라벨은 0=`inappropriate`, 1=`appropriate`다.
테스트 학습의 라벨은 0=`test_pattern_a`, 1=`test_pattern_b`로 별도 저장한다.

이것은 당시 회사 모델의 정확한 복원이 아닌 재구현의 기본 모델이다.
[PyTorch GRU](https://docs.pytorch.org/docs/2.14/generated/torch.nn.GRU.html)와
[가변 길이 packing](https://docs.pytorch.org/docs/2.14/generated/torch.nn.utils.rnn.pack_padded_sequence.html)의
공식 API를 사용한다. 긴 발표에서 최종 hidden state가 충분한지는 실제 데이터로 평가해야 한다.

## 테스트용 학습 실행

저장소 루트에서 새 출력 경로로 실행한다.

```sh
uv sync --locked
uv run --locked presentation-training-smoke \
  --output .local-data/presentation-attitude/gru-smoke
```

합성 시퀀스 12개(8–20프레임)를 생성하고 train 8개, validation 4개로 나눈다.
별도 seed로 독립 test 시퀀스 4개도 생성하며 학습·체크포인트 선택에는 사용하지 않는다.
숫자의 분포가 다른 두 패턴과 일부 결측을 섞는다. 각 split에 두 클래스가 모두 있다.
기본값은 CPU, 3 epoch, batch 4, hidden 32, learning rate 0.001, seed 42다.
이 검사는 네트워크나 영상·MediaPipe 모델 없이 실행된다. Python 의존성 설치는 별도다.

출력:

- `data/manifest.json`, `data/fixture_*/`: 테스트 전용 시퀀스와 분할 정보.
- `test-data/manifest.json`, `test-data/test_*/`: 독립 평가용 합성 시퀀스 4개.
- `training/summary.json`: 설정·데이터 해시·epoch별 loss·가중치 변경·재로딩 검사 결과.
- `training/best.pt`: validation loss가 가장 낮은 epoch의 가중치와 모델·특징 설정.

체크포인트에는 가중치·epoch·데이터 출처를 기록한다. optimizer 상태를 복원하는 학습
재개 기능은 아직 없다. 체크포인트를 읽을 때 `weights_only=True`를 사용한다.

저장된 모델은 `presentation-evaluate`로 평가한다. [평가 실행 안내](evaluation.md)를 참고한다.

### Mock으로 어디까지 확인할 수 있는가?

실제 태도 라벨 데이터 없이도 학습·평가 지표 계산·체크포인트 추론·작업 API 연결을
검증할 수 있다. 2026-09-08에 위 합성 좌표로 train 8개·validation 4개, 3 epoch를
실행했고, 저장한 GRU를 별도 테스트 워커에 올려 업로드 작업 2건의 결과 조회까지 확인했다.

- 전처리는 합성 원시 랜드마크를 사용하는 기존 테스트 10개로 별도 검증했다.
- 학습 시퀀스는 이미 전처리된 형식의 두 숫자 패턴이다. 이 생성기는 정규화·이동평균을 실행하지 않는다.
- 아래 초기 실행 기록의 평가 지표는 체크포인트 선택에 사용한 validation 4개 기준이며 독립 테스트 성능이 아니다.
  Accuracy·precision·recall·F1 모두 1.0이었지만 실제 태도 분류 성능을 뜻하지 않는다.
- 서빙 검증은 FastAPI TestClient와 SQLite, 별도 Python 워커, 실제 FFmpeg 디코딩과
  학습된 GRU를 사용했다. 단색 테스트 영상의 MediaPipe·전처리 결과는 고정된 합성
  시퀀스로 대체했다. 실제 사람 영상에서 좌표를 추출한 전체 판정 검증은 아니다.
- 결과는 `test_pattern_a/b`이며 `assessment=null`이다. 테스트에서만 분석기를 주입했고,
  일반 `assessment` 서빙이 `pipeline_smoke` 체크포인트를 거절하는 정책은 유지한다.

[Mock 파이프라인 실행 기록](../history/mock_pipeline_results.json)에 지표·입출력·검증 범위를 남겼다.
실데이터 확보 전에도 이 방식으로 기능 연결을 계속 개발할 수 있다.

## 준비된 데이터로 학습

```sh
uv run --locked presentation-train \
  --manifest /path/to/manifest.json \
  --output .local-data/presentation-attitude/gru-run \
  --epochs 3 --batch-size 4 --hidden-size 32 --device cpu
```

manifest의 `purpose`는 `pipeline_smoke` 또는 `attitude_training`이다.
아래는 실영상 manifest의 **형식 예시**이며 존재하는 학습 자료가 아니다.

```json
{
  "schema_version": 1,
  "purpose": "attitude_training",
  "samples": [
    {
      "id": "example-video",
      "sequence_dir": "sequences/example-video",
      "speaker_id": "example-speaker",
      "source_video_id": "example-source",
      "source_kind": "real",
      "annotation_status": "reviewed",
      "training_eligible": true,
      "label": 1,
      "split": "train"
    }
  ]
}
```

`sequence_dir`는 manifest 파일 위치 기준이며 `presentation-process`의 완료된 출력 폴더다.
실제로 실행하려면 train과 validation 각각에 두 클래스가 있어야 한다.
같은 발표자·원본 영상 ID·입력 영상 해시가 두 split에 걸치면 거부한다.
`training_eligible`은 출처·이용 조건·목표 맥락을 검토한 결과를 사람이 입력하는 값이지,
코드가 해당 적합성을 자동 판정했다는 뜻이 아니다. 상세 주석 근거는 기존 주석 기록에 보관한다.

읽을 때마다 시퀀스 해시와 프레임 수·좌표 형태·유한 값·마스크를 검사한다.
전체 영상에 사용 가능한 특징이 하나도 없으면 학습 입력을 거부한다.
학습은 한 배치의 전체 시퀀스를 메모리에 올리므로 메모리 사용량은 배치와 영상 길이에 비례한다.
기본 `--max-frames 10000`을 넘는 영상은 잘라내지 않고 오류로 알린다.
시간에 따른 고급 batching이나 장시간 영상 chunking은 아직 구현하지 않았다.

## 모델과 추적 상태의 수명

| 객체 | 현재 유지 범위 |
|---|---|
| MediaPipe 얼굴·손 추적 세션 | 영상 하나 전체. 학습 코드에서는 생성하지 않음 |
| 학습용 GRU·optimizer | 학습 실행 전체, epoch마다 재생성하지 않음 |
| `ClassifierRuntime`의 GRU 가중치 | runtime 객체를 만들 때 한 번 로드, 반복 호출에서 재사용 |
| GRU hidden state | 각 영상에서 0으로 시작. 이전 요청의 상태를 보관하지 않음 |

```python
from presentation_attitude.models.runtime import ClassifierRuntime

runtime = ClassifierRuntime("/path/to/best.pt")
result = runtime.predict_sequence("/path/to/completed-sequence")
# 같은 runtime 객체로 다음 영상도 처리할 수 있다.
```

결과에 체크포인트의 `purpose`와 `label_mapping`을 함께 반환한다.
테스트용 체크포인트는 테스트용 특징 설정에만 맞으며 실제 영상 평가용으로 사용하지 않는다.
HTTP 서버·작업 큐는 [서빙 안내](serving.md)에 구현돼 있다. MediaPipe의 영상 간 모델 상주는 아직 구현하지 않았다.
MediaPipe 초기화 비용과 프레임 처리 시간을 분리 측정하는 최적화도 후속 작업이다.

## 검증 범위

Python 3.13.15, PyTorch 2.14.0, Apple M4의 CPU에서 실행했다.
기본 모델로 테스트 시퀀스 12개를 3 epoch 학습해 optimizer step 6회를 수행했다.
train loss는 0.729900에서 0.354907, validation loss는 0.554458에서 0.280806으로 줄었다.
이는 인위적으로 구분하기 쉽게 만든 두 숫자 패턴에 대한 결과다.
실제 가중치 변경과 best checkpoint 재로딩 후 logit의 동일성을 확인했다.

비전 테스트 39개와 데이터 합성 테스트 4개가 통과했다. padding에 큰 값을 넣어도 출력이
변하지 않는지, 다른 영상을 처리한 뒤 같은 영상의 결과가 동일한지, 데이터 분할 누수와
손상된 입력을 거부하는지도 검사했다. 기존 실영상의 1,317프레임을 `[1317, 1043]` 텐서로
변환해 **미학습 모델**에서 유한한 logit 하나가 나오는 것까지 확인했다.
이 과정에 MediaPipe import나 추론은 없었다. 실제 태도 라벨·분류 성능과 RTX 5090/CUDA는 미검증이다.

[실행 검증 기록](../history/gru_training_results.json)에 체크포인트·요약 해시와 결과를 기록한다.
