# 모노레포 구조 기준

세 프로젝트는 **같은 위치에서 같은 역할을 찾을 수 있도록** 구성합니다.
Python 구현은 `src`, 테스트는 `tests`, 상세 설명은 `docs`에 둡니다.

```text
<project>/
├── README.md                 # 한국어 소개·결과·빠른 시작
├── README.en.md              # 영어 소개
├── pyproject.toml            # 패키지·의존성·실행 명령
├── src/<package>/            # 실제 Python 코드
│   ├── cli/                  # 명령행 입력과 실행 진입점
│   └── <기능별 모듈>/        # 모델·데이터·평가·워크플로 등
├── tests/                    # 해당 프로젝트의 테스트
├── docs/                     # 설계·실험 기록·출처
└── frontend/                 # 웹 UI가 있는 프로젝트에만 사용
```

## 프로젝트별 이름

| 프로젝트 폴더 | Python import | 환경 |
|---|---|---|
| `presentation_attitude_assessment` | `presentation_attitude` | 공통 uv workspace |
| `writing_data_synthesis` | `writing_synthesis` | 공통 uv workspace |
| `child_speech_recognition` | `child_speech` | 별도 CUDA/NeMo 환경 |

환경이 달라도 패키지 구조는 같습니다. ASR의 GPU 라이브러리는 공통 환경과 충돌할 수 있어
별도로 설치합니다. 세 프로젝트 모두 Python 3.13.x를 기준으로 합니다.

## 코드를 어디에 둘까?

- `src/<package>/cli`: 인자 처리와 실행 시작점. 재사용하는 처리는 기능 모듈로 분리합니다.
- `models`: 모델 구조와 모델 입출력 계약.
- `data`: 파일 읽기, 전처리, 데이터셋 처리. 학습 전용 데이터 로더가 커지면 그 아래 `datamodules`로 분리합니다.
- `training`, `evaluation`: 학습과 성능 측정.
- `pipelines`: 여러 처리 단계를 연결하는 실행 흐름. 에이전트의 상태·재시도 흐름은 `workflows`로 구분합니다.
- `serving`, `api`: 추론 서비스와 HTTP 요청 처리. 실제 제공 기능에 맞는 이름을 사용합니다.
- `tests`: 모듈 밖에서 설치된 패키지를 import합니다. 규모에 따라 `unit`, `integration`으로 나눕니다.

모든 프로젝트에 위 폴더를 전부 만들지는 않습니다. 필요한 역할이 생길 때 추가합니다.
`utils`에 서로 무관한 기능을 모으지 않고, `paths`, `runtime`, `storage`처럼 역할을 드러내는 이름을 씁니다.
`scripts`에는 Python 구현을 쌓지 않습니다. 별도 운영용 셸 스크립트가 필요할 때만 사용합니다.

## 코드가 아닌 파일

쓰기 모듈의 `criteria/`는 학년별 루브릭 JSON과 읽기용 문서입니다. 루브릭을 선택·검증하는
Python 코드는 `src/writing_synthesis/criteria/`에 있습니다. 출처는 `docs/rubric-evidence/`에 둡니다.

ASR의 `results/`는 공개 가능한 평가 결과입니다. 현재 공개 음성 샘플은 포함하지 않습니다.
원본 학습 데이터, 체크포인트, 실행 중 생성되는 파일은 Git에서 제외한 저장소 루트의 `.local-data/`에 둡니다.

현재 실행 방식은 저장소를 내려받아 **editable 설치**하는 방식입니다. 쓰기·ASR 패키지는
프로젝트의 루브릭·결과 파일을 함께 사용합니다. 코드만 wheel로 옮길 경우 리소스도 배치하고
각각 `WDS_PROJECT_DIR`, `ASR_PROJECT_DIR`을 프로젝트 리소스 폴더로 지정해야 합니다.

## 실행과 검증

저장소 루트에서 공통 환경을 설치합니다.

```sh
uv sync --all-packages --locked
uv run --locked writing-mock-smoke --data-dir .local-data/writing-layout-smoke
uv run --locked python -m unittest discover -s presentation_attitude_assessment/tests -v
uv run --locked python -m unittest discover -s writing_data_synthesis/tests -t writing_data_synthesis -v
```

ASR은 [전용 환경 설치](../child_speech_recognition/docs/EXPERIMENTS.md#run-the-code) 후 실행합니다.
가벼운 결과 검증만 할 때는 ML 의존성 없이 패키지를 설치할 수 있습니다.

```sh
uv pip install --python .venv/bin/python --no-deps -e child_speech_recognition
.venv/bin/python -m unittest discover -s child_speech_recognition/tests -v
.venv/bin/python -m child_speech.cli.build_examples --help
```

새 프로젝트에도 이 기준을 적용합니다. 파일 이동 시 import, 리소스 경로, README 명령과 링크,
테스트를 함께 수정하며 과거 실험 수치와 데이터는 변경하지 않습니다.
