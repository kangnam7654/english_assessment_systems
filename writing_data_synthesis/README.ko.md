# English Writing Data Synthesis — 영어 쓰기 데이터 합성

[English](README.md) · [모노레포](../README.ko.md)

학년·수준별 영어 에세이를 생성하고 LLM의 루브릭 평가를 붙이는 LangGraph 워크플로입니다.
포트폴리오에서 데이터 합성 관점의 기능을 담습니다. 기존 에세이를 입력하는 평가 전용 모드도 있습니다.

## 흐름과 구성

```text
synthesis:  orchestrator → student → orchestrator → assessor → END
assessment: orchestrator → assessor → END
```

- `agents/`: Orchestrator가 프롬프트와 경로를 선택하고, Student가 에세이를 생성하며,
  Assessor가 평가합니다. Student는 생성 후 모드를 assessment로 바꿉니다.
- `prompts/`: 역할별 템플릿, 학년·수준별 루브릭과 프롬프트 빌더.
- `workflow_builder.py`: LangGraph 그래프와 모듈 위치를 기준으로 한 리소스 경로.
- `config.py`: Ollama 모델(`gpt-oss:20b`), 그래프 팩토리와 초기 상태.
- `app.py`: FastAPI `POST /run` API.
- `tests/integration/`: 가짜 LLM으로 그래프·프롬프트 파일·API 연결을 확인하는 테스트.
- `frontend/`: 생성·평가를 실행하는 Next.js/React 데모.
- `docs/`: 과거 다이어그램 원본과 이미지. Gradio로 표기된 과거 UI 설명이 남아 있으므로
  당시 설계 기록으로 참고합니다. 현재 UI는 Next.js입니다.

## 실행

루트 `.python-version`·`uv.lock`·`.venv`를 공유하며 별도 Python 환경을 만들지 않습니다.
[공통 환경 안내](../docs/python_environment.md)를 따릅니다. 전체 데모에는 Python 3.13.15, uv, Ollama와 Node.js/npm이 필요합니다.
`ollama serve`로 서버를 실행하고 별도 터미널에서 `ollama pull gpt-oss:20b`로 모델을 준비합니다.

저장소 루트에서:

```sh
uv sync --locked
uv run --all-packages --locked uvicorn app:app --app-dir writing_data_synthesis --reload --port 8000
```

또는 이 모듈 폴더 안에서:

```sh
uv sync --all-packages --locked
uv run --all-packages --locked uvicorn app:app --reload --port 8000
```

UI는 저장소 루트의 다른 터미널에서:

```sh
cd writing_data_synthesis/frontend
npm ci
npm run dev
```

`http://localhost:3000`을 엽니다. API 주소의 기본값은 `http://localhost:8000`이며
`NEXT_PUBLIC_API_URL`로 바꿀 수 있습니다. 백엔드 CORS는 현재 로컬 3000번 포트를 허용합니다.

`POST http://127.0.0.1:8000/run` 요청 예시:

```json
{
  "mode": "synthesis",
  "user_prompt": "Write an essay about studying computer science as a hobby.",
  "grade_for_student": "mid_2",
  "grade_for_assessor": "mid_2",
  "level": "intermediate"
}
```

기존 글을 평가할 때는 `mode: "assessment"`와 `essay` 문자열을 보냅니다.
응답은 `grade`, `level`, `essay`, `assessed_content`입니다. 기존 구현의 최상위 `grade`는
null일 수 있고, LLM이 만드는 평가 payload에는 엄격한 스키마 검증이 없습니다.

## 검증과 현재 범위

```sh
# 저장소 루트에서 실행. Ollama 추론 없이 검증
uv run --all-packages --locked python -m unittest discover -s writing_data_synthesis/tests -t writing_data_synthesis -v
```

가짜 LLM 응답으로 생성·평가 분기, 모든 학년·수준 조합의 프롬프트,
다른 작업 디렉터리에서의 리소스 로딩과 `/run` API를 검증합니다.
실제 모델 응답의 품질이나 Ollama 추론 성공을 검증하는 테스트는 아닙니다.

분리 검증(2026-09-07): 오프라인 테스트 4개 통과, 루트·모듈 폴더 양쪽에서 Uvicorn 시작과
OpenAPI 응답 확인, 프런트엔드 lint·프로덕션 빌드 통과. 옮긴 39개 파일 중 내용이 바뀐 것은
워크플로 리소스 경로, 프로젝트 메타데이터와 lockfile뿐입니다.

현재는 요청 단위 합성 프로토타입입니다. 배치 저장, 데이터셋 버전 관리, 사람의 라벨 검토,
품질 기준과 학습·평가 분할은 아직 구현하지 않았습니다. 생성된 평가를 사람이 검증한 정답으로
사용할 수 있다고 단정하지 않습니다. 폴더 분리는 기존 그래프·프롬프트·루브릭·UI 동작을 유지합니다.

[MIT License](../LICENSE).
