# Python 패키지 구성

[문서 목차](../README.md)

2026-09-08: `src/presentation_attitude`를 역할별 하위 패키지로 정리했다.
`src` layout, 바깥 프로젝트 폴더, 공통 Python 3.13 환경과 CLI 명령은 유지한다.

## 역할별 패키지

| 패키지 | 파일 | 책임 |
|---|---|---|
| `models/` | `gru.py`, `runtime.py`, `assets.py` | GRU 구조, 체크포인트 로드·추론, MediaPipe 모델 자산 다운로드·검증 |
| `data/` | `dataset.py`, `manifest.py`, `preprocessing.py` | 시퀀스 텐서·배치, 학습·평가 목록 검증, 정규화·이동평균 |
| `pipelines/` | `extraction.py`, `training.py`, `training_smoke.py`, `evaluation.py` | 영상 전체 처리 및 학습·평가 실행 흐름 조율 |
| `vision/` | `video.py`, `landmarks.py` | FFmpeg 프레임 읽기, MediaPipe VIDEO 추적·추출과 audit |
| `evaluation/` | `classification.py`, `diagnostics.py`, `visualization.py` | 이진 분류 지표 계산, 검출률·누락·연속성 진단과 좌표 시각화 |
| `serving/` | `api.py`, `middleware.py`, `contracts.py`, `store.py`, `files.py`, `worker.py`, `analyzer.py`, `settings.py` | HTTP·요청 크기 제한, 저장소 계약·SQLite 구현, 로컬 파일, 워커 수명, 분석 연결 |
| `cli/` | 기존 실행 명령 모듈 | 인자 해석 및 실행 함수 연결 |

공유 특징 형식·분류 라벨은 루트 `schema.py`, 파일 입출력·해시는 `artifacts.py`, 체크아웃 리소스
탐색은 `paths.py`에 둔다. 세 파일을 담기 위해 별도 범용 `utils/` 계층을 추가하지 않는다.

`data`는 표준 PyTorch `Dataset`, collate 함수와 데이터 검증을 담는 패키지다.
Lightning의 `DataModule`을 도입하지 않았으므로 `datamodules` 대신 이 이름을 사용한다.
`models/assets.py`는 자산 관리이고, 프레임을 MediaPipe에 입력하는 실행 코드는 `vision`에 있다.

## 의존 관계와 수명

- CLI와 서빙은 pipelines의 실행 함수를 호출한다.
- 영상 추출 pipeline은 vision과 data 전처리를 연결한다.
- 학습 pipeline은 data의 Dataset과 models의 GRU/runtime을 사용한다.
- 평가 pipeline은 저장된 runtime을 재사용하고 evaluation의 분류 지표를 계산한다. `presentation-evaluate` CLI가 실행을 연결한다.
- `models/gru.py`는 네트워크만 정의한다. `models/runtime.py`가 데이터 로드와 체크포인트 추론을 연결한다.
- `data/manifest.py`는 Torch·MediaPipe를 import하지 않는다. 하위 패키지 `__init__.py`도 ML 모듈을 자동 import하지 않는다.
- FastAPI는 ML 런타임을 import하지 않는다. 워커의 GRU 재사용과 영상별 MediaPipe 추적 세션 수명은 유지한다.
- tests는 기능 프로젝트의 `tests/unit`, `tests/integration`에 유지한다.

## 서빙 코드의 책임

- `api.py`: 요청 인자·확장자 검증, 작업 접수·조회, 파일 오류를 HTTP 응답으로 변환한다.
- `middleware.py`: multipart 요청 본문 전체의 크기를 제한한다.
- `files.py`: 업로드를 청크 단위로 저장하고 해시·파일 크기를 계산한다. `stage_upload()` 안에서 저장소에 작업을 등록하며, 입력 읽기나 등록이 실패하면 임시 작업 디렉터리를 정리한다. HTTP·SQLite에 의존하지 않는다.
- `store.py`: SQLite 작업 상태와 시도 이력을 담당한다. 영상 파일을 저장하지 않는다.
- `worker.py`: 작업 선택·복구·실행 수명을, `analyzer.py`는 특징 추출과 선택적 모델 추론 연결을 담당한다.

학습·평가·서빙은 `schema.label_mapping()`의 동일한 라벨 정의를 사용한다.
합성 테스트 라벨과 실제 태도 라벨은 구분한다. 체크포인트 형식과 판정 임계값은 유지한다.

파일 저장·실패 정리와 모의 런타임을 이용한 analyzer 검사는 `tests/unit/`에 둔다.
실제 HTTP·SQLite·워커를 연결하는 검사는 `tests/integration/test_serving.py`에 둔다.

## 공개 함수와 내부 구현

| 사용하는 쪽 | 공개 진입점 | 내부에서 담당하는 일 |
|---|---|---|
| CLI·분석 워커 | `process_video()` | FFmpeg·MediaPipe 세션과 전처리 연결, 산출물 저장 |
| 학습 코드 | `read_manifest()`, `SequenceDataset`, `collate_sequences()` | 출처 검증, 시퀀스 텐서 생성, padding |
| 학습 CLI | `train()` | 모델 학습, 최적 체크포인트 저장·재로드 확인 |
| 평가 CLI | `evaluate()` | test 분리 검증, 추론, 지표·오분류 저장 |
| 저장된 특징의 추론 | `ClassifierRuntime.predict_sequence()` | 시퀀스 무결성·설정 검증 후 추론 |
| 검증된 텐서 배치의 추론 | `ClassifierRuntime.predict_logits()` | device 이동, gradient 없는 추론, 영상별 상태 초기화 |
| 작업 실행 | `JobWorker.run_once()`, `Analyzer` 계약 | 저장소·분석기 연결, 성공·실패 기록 |

`ClassifierRuntime`의 네트워크는 `_model`에 두고 외부에서 직접 호출하거나
학습 모드를 바꾸지 않는다. 학습 후 재로드 검증과 저장 시퀀스 추론도 동일한
`predict_logits()`를 사용한다. 텐서 배치를 직접 전달할 때는 호출자가 체크포인트의
특징 설정을 맞춰야 하며, 파일 기반 검증이 필요하면 `predict_sequence()`를 사용한다.

전처리의 좌표 검증·앵커 계산·손 선택 보조 함수와 SQLite `_connect()`는 내부
구현으로 표시한다. Python의 `_`는 사용 경계를 나타내는 관례이며 접근 제한 장치는 아니다.
독립적인 전처리·지표 계산은 함수로, 모델·프로세스·저장소처럼 수명을 가진 자원은
클래스로 유지한다. `Analyzer` Protocol은 대체 분석기와 테스트용 callable의
입출력을 명시하며, 구현 클래스의 상속이나 새 런타임 의존성은 요구하지 않는다.

주요 공개 함수의 docstring에는 입력·반환 형식, tensor shape·단위, 결측과 padding의
차이, 파일 생성·오류·모델 수명을 기록한다. 코드를 그대로 읽어주는 줄별 주석보다
정규화 scale의 이유, 스트리밍 검증을 끝까지 소비해야 하는 이유처럼 설계 근거를 남긴다.
간단한 접근자와 CLI 인자마다 같은 설명을 반복하지 않는다.

## import 경로 변경

```python
from presentation_attitude.data.dataset import SequenceDataset, collate_sequences
from presentation_attitude.data.manifest import read_manifest
from presentation_attitude.artifacts import iter_sequence
from presentation_attitude.models.gru import GRUClassifier
from presentation_attitude.models.runtime import ClassifierRuntime
from presentation_attitude.pipelines.extraction import process_video
from presentation_attitude.pipelines.training import train
from presentation_attitude.vision.video import FFmpegVideoReader
```

기존 `presentation_attitude.model`, `.dataset`, `.pipeline` 같은 평면 모듈 경로는
새 경로로 바뀐다. 내부 import·테스트의 mock 경로·사용 예시를 함께 갱신했으며,
이전 경로용 shim 파일은 남기지 않는다. 외부 개인 스크립트가 있다면 위 새 경로로 수정한다.
함수 이름과 CLI 명령, API 경로·포트 43187, JSON 형식, 체크포인트 state_dict 형식은 유지한다.

정의가 다른 파일로 이동한 뒤 남아 있던 재노출 import도 정리했다.
`read_manifest`는 `data.manifest`, `INPUT_SIZE` 등 특징 정의는 `schema`,
`iter_sequence`는 `artifacts`에서 직접 가져온다. `data.dataset`이나
`pipelines.extraction`을 경유하는 예전 import는 사용하지 않는다.

이동 자체로 구현 해시는 바뀐다. 과거 결과 JSON과 그 시점의 해시는 수정하지 않으며,
새 실행은 `artifacts.implementation_hashes()`가 하위 패키지를 포함해 재귀적으로 기록한다.
계산식·하이퍼파라미터·추론 정책·성능 최적화는 변경하지 않았다.

## 검사 명령

```sh
uvx ruff==0.16.6 check presentation_attitude_assessment
uvx ruff==0.16.6 format --check presentation_attitude_assessment
uv run --locked python -m unittest discover -s presentation_attitude_assessment/tests -v
```

이번 구조 변경의 확인 결과는 [package_layout_results.json](../history/package_layout_results.json)에 기록한다.

2026-09-08 서빙 책임·공통 라벨·import 정리 후에는 발표 태도 테스트 75개와
데이터 합성 테스트 4개, Ruff 검사·포맷 검사가 통과했다. 동일 시드 42로 CPU에서
합성 시퀀스를 3 epoch 학습한 정리 전후의 전체 loss 이력, 체크포인트 가중치와
메타데이터가 모두 일치했다. 이는 코드 정리의 회귀 검증이며 실제 태도 성능 측정은 아니다.

## 이전 리팩터링 검증 기록

- 발표 태도 테스트 42개와 데이터 합성 테스트 4개 통과.
- 리팩터링 전후 합성 학습의 모든 epoch loss와 저장된 모델 가중치가 동일함.
- 기존 MIT 700프레임 전처리와 실제 짧은 영상 9프레임의 새 추출·전처리 결과가 바이트 단위로 동일함.
- `schema`와 `manifest`만 import할 때 PyTorch·MediaPipe가 로드되지 않음.
- Ruff 검사·포맷 검사, 패키지 빌드, 공통 환경 의존성 검사 통과.

[대조 결과](../history/refactoring_results.json)를 기록했다. 과거 실행 결과와 해당 시점의 해시는 수정하지 않는다.
