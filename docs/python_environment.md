# 공통 Python 환경

두 기능은 하나의 uv workspace에서 실행한다. 기능별 폴더와 의존성 선언은 분리하고,
Python 선택·버전 해석·lockfile·로컬 가상환경은 공유한다.

| 항목 | 관리 위치 |
|---|---|
| 기본 Python 3.13.15 | 루트 `.python-version` |
| 지원 Python 범위 3.13.x | 루트와 멤버 `requires-python` |
| workspace 구성·두 기능 포함 | 루트 `pyproject.toml` |
| 기능별 직접 의존성 | 각 기능의 `pyproject.toml` |
| 확정된 라이브러리 버전 | 루트 `uv.lock` 하나 |
| 설치·실행 환경 | 루트 `.venv` 하나 |

발표 태도 모듈은 `src/presentation_attitude/`의 Python 패키지이며 공통 `.venv`에
editable 설치한다. 데이터 합성 모듈과 루트는 `package = false`를 유지한다.
테스트는 각 기능의 `tests/`에 두며, 기능 간 통합 테스트가 필요할 때 루트 `tests/`를 추가한다.

## 설치와 실행

저장소 루트에서:

```sh
uv sync --locked
uv run --locked python -m unittest discover -s presentation_attitude_assessment/tests -v
uv run --locked python -m unittest discover -s writing_data_synthesis/tests -t writing_data_synthesis -v
uv run --locked uvicorn app:app --app-dir writing_data_synthesis --reload --port 8000
```

루트 프로젝트가 두 멤버에 의존하므로 기본 `uv sync`도 양쪽 라이브러리를 설치한다.
모듈 폴더 안에서 작업할 때는 `uv sync --all-packages --locked`,
`uv run --all-packages --locked ...`를 사용해 두 기능의 패키지를 함께 유지한다.
루트와 두 모듈 폴더에서 이 명령이 동일한 루트 `.venv`를 사용하는지 확인했다.

라이브러리 추가·변경은 해당 모듈에 선언한다. 예:

```sh
uv add --package writing-data-synthesis <library>
uv add --package presentation-attitude-assessment <library>
```

`uv.lock`은 uv로 생성하며 수동으로 버전을 편집하지 않는다. 모듈 선언과 루트 lockfile을
함께 관리한다. 업그레이드 후에는 위 두 테스트 모음을 같은 환경에서 검사한다.
Python을 변경할 때는 루트 `.python-version`과 전체 호환 범위를 함께 검토한다.

Next.js는 Python과 다른 런타임이므로 `writing_data_synthesis/frontend/package-lock.json`으로
기존 Node 의존성을 관리한다. FFmpeg와 Ollama도 Python lockfile이 설치하는 프로그램은 아니다.
다른 OS에서는 lockfile의 플랫폼 조건에 맞는 배포 파일이 설치된다. RTX 5090/CUDA 실행은
이번 공통 환경 검증에 포함되지 않는다.

## 통합 시 확인한 버전 (2026-09-07)

| 라이브러리 | 공통 버전 |
|---|---|
| MediaPipe | 0.10.32 |
| NumPy | 2.5.3 |
| OpenCV contrib | 4.14.0.94 |
| LangGraph | 1.0.3 |
| LangChain core | 1.0.5 |
| langchain-ollama | 1.0.0 |
| FastAPI | 0.121.2 |
| packaging | 25.0 |

기존 두 lockfile을 바탕으로 버전을 유지했다. 겹치는 `packaging`은 발표 태도 환경의
26.3과 데이터 합성 환경의 25.0 중 양쪽 제약에 맞는 25.0으로 통합했다.
그 외 기존 외부 라이브러리의 확정 버전은 변경하지 않았다.

검증: Python 3.13.15 공통 환경에서 발표 태도 테스트 25개와 데이터 합성 테스트 4개 통과.
MediaPipe 실영상 2구간·109프레임 추출·전처리를 실행했고, 3.12.14에서 얻은 랜드마크와
전처리 레코드가 모두 바이트 단위로 같았다. `uv pip check`도 통과했다.
데이터 합성 테스트는 가짜 LLM을 사용한 그래프·API 검증이며 실제 Ollama 추론은 실행하지 않았다.

모듈별 `uv.lock`, 쓰기 모듈의 `.python-version`, 이전 `.venv`는 활성 경로에서 제거했다.
이전 lockfile과 가상환경은 Git에서 제외된 `.local-data/environment-before-workspace/`에
이동·보관했으며 현재 실행에는 사용하지 않는다. 과거 실험 결과 JSON과 해당 시점의 해시는
수정하지 않았다.

[uv workspace 공식 문서](https://docs.astral.sh/uv/concepts/projects/workspaces/)에서
멤버별 의존성 선언과 단일 lockfile, 전체 workspace의 Python 범위 해석 방식을 확인할 수 있다.

## Python 3.13 전환

공통 환경의 기준을 3.12.14에서 **3.13.15**로 올렸다. Python만 올리고 라이브러리 버전은
전부 유지했다. root와 두 멤버의 `requires-python`은 `>=3.13,<3.14`로 통일했다.
루트 `.python-version`이 패치 버전을 선택하며, 실행 환경과 lockfile은 계속 하나씩만 사용한다.

[Python 공식 배포 목록](https://www.python.org/downloads/)에서 3.13.15 릴리스를 확인했다.
[MediaPipe 0.10.32 배포 파일](https://pypi.org/project/mediapipe/0.10.32/#files)의
macOS arm64 wheel과 실제 설치·추론을 검사했다. 이번 확인 환경은 Apple M4 macOS이며,
모든 운영체제에서의 호환성을 검증한 것은 아니다.

이전 3.12 공통 환경과 설정은 Git 제외 경로 `.local-data/python313-upgrade/`에 보관했다.
[현재 환경 검증 기록](python_environment_results.json)에 테스트·환경 경로·대조 결과를 기록한다.
과거 비전 실험 문서의 Python 3.12 표기는 해당 실험 당시 버전이므로 보존한다.

## GRU 학습 환경 추가

PyTorch 2.14.0을 발표 태도 멤버에 추가하고 공통 lockfile과 `.venv`에 설치했다.
기존 라이브러리 버전은 유지했다. CPU에서 테스트용 GRU 학습·재로딩과 비전 테스트 39개,
데이터 합성 테스트 4개를 확인했다. CUDA/MPS 학습은 이번 검증에 포함하지 않았다.
[GRU 학습 안내](../presentation_attitude_assessment/docs/guides/gru_training.md)를 참고한다.
