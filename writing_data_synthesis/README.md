# 영어 글쓰기 데이터 생성

[English](README.en.md) · [모노레포](../README.md) · [학년별 루브릭](criteria/README.md)

[공통 디렉터리 기준](../docs/repository_structure.md)
**학년과 목표 수준에 맞는 글을 생성하고, 독립적으로 검수한 뒤 결과와 실행 근거를 저장하는 시스템입니다.**
크레버스에서 수행한 영어 글쓰기 데이터 생성 업무를 바탕으로 재구성한 포트폴리오 프로젝트입니다.
회사 코드와 비공개 학생 데이터는 포함하지 않습니다.

현재는 글을 한 번 생성·평가하거나, 입력한 글만 평가하는 흐름을 구현했습니다.
API·검증·저장 경로는 **고정 Mock 응답으로 확인**했습니다. 실제 모델의 품질과 교육적 타당성은
미검증이며, Mock 결과를 데이터셋으로 사용할 수는 없습니다.

## 동작 흐름

```text
요청 → 학년·글 유형의 루브릭 선택 → 글 생성 → 검수 → 결과 저장
                                  평가 전용 모드에서는 생략
각 단계 → 변경 불가능한 상태 스냅샷 → SQLite
```

예를 들어 6학년 논증문 요청은 6학년 파일의 논증문 기준을 선택합니다.
생성자는 과제·지문·기준·목표 수준을 받고, 검수자는 같은 과제와 기준에 글을 더해 받습니다.
검수자에게 생성 목표 수준은 전달하지 않습니다. 코드가 반환된 점수를 검증하고 표시값을 계산합니다.

확정된 루브릭은 13개 학년 파일, 39개 학년·글 유형 조합입니다.
내용·구성·표현·문법은 각각 1–4점이며 출처 사용은 필요한 과제에만 적용합니다.
0–100 표시값은 총점이나 학년 간 실력 비교 점수가 아닙니다.
[평가표](criteria/README.md)와 [출처·재구성 근거](docs/rubric-evidence/README.md)를 별도로 볼 수 있습니다.

## 주요 설계 결정

| 결정 | 이유 |
| --- | --- |
| Python 코드가 실행 순서를 제어 | 한 번의 생성·평가에서 단계와 분기를 명확히 추적할 수 있습니다. LLM 오케스트레이터나 LangGraph가 필요하지 않은 범위입니다. |
| 생성자와 검수자의 입력 분리 | 검수자에게 목표 수준을 숨겨 직접적인 평가 편향 요인을 줄입니다. 이것만으로 평가의 독립성이나 정확도가 입증되지는 않습니다. |
| 모델 출력은 경계에서 검증 | 필수 필드·점수 범위·학년·글 유형·평가 불가 상태를 Pydantic으로 검사한 뒤 완료 처리합니다. |
| 작은 모델 호출 인터페이스 사용 | 에이전트는 `LanguageModel.complete`에만 의존합니다. OpenAI SDK 어댑터와 Mock이 같은 인터페이스를 구현합니다. |
| 실행과 저장의 책임 분리 | `RunStore`를 통해 SQLite를 연결합니다. 단계별 상태·루브릭 해시·실제 프롬프트를 남겨 실패나 재시작 후에도 실행을 확인할 수 있습니다. |

State는 한 실행의 기록이며, 사용자 사이에 공유하는 대화 메모리가 아닙니다.
`POST /run`은 완료까지 기다리는 동기 요청입니다. 중단된 실행은 조회할 수 있지만 자동 재개하지 않습니다.
저장 오류가 발생했다면 완료 결과가 저장되었다고 확정하지 않습니다.

## 코드는 이 순서로 보면 됩니다

1. [WorkflowRequest](src/writing_synthesis/schemas/request.py) — 입력과 과제 제약.
2. [WritingWorkflow.run](src/writing_synthesis/workflows/runner.py) — 생성·평가 전체 실행 순서.
3. [PromptPreparation](src/writing_synthesis/prompts/preparation.py)와 [ResolvedCriteria](src/writing_synthesis/criteria/resolver.py) — 루브릭 선택, 역할별 입력과 재현 정보.
4. [생성자](src/writing_synthesis/agents/student.py)와 [검수자](src/writing_synthesis/agents/assessor.py) — 모델 호출과 출력 검증. [프로젝트 점수](src/writing_synthesis/schemas/project_assessment.py) — 코드가 계산하는 표시값.
5. [LanguageModel](src/writing_synthesis/llm/types.py), [OpenAI 어댑터](src/writing_synthesis/llm/client.py), [Mock](src/writing_synthesis/llm/mock.py) — 모델 제공자와의 연결 경계.
6. [WorkflowState](src/writing_synthesis/schemas/run.py)와 [SQLiteRunStore](src/writing_synthesis/storage/sqlite.py) — 상태 전이, 리비전과 저장.

[app.py](src/writing_synthesis/app.py)는 앱 자원의 수명을 관리하고, [api/routes.py](src/writing_synthesis/api/routes.py)는 HTTP 요청과 결과를 변환합니다.
[frontend/](frontend/)는 실행을 확인하는 화면이며 핵심 워크플로는 백엔드에 있습니다.
[테스트](tests/integration/)는 같은 백엔드를 Mock 모델과 가짜 SDK 전송 계층으로 검증합니다.

주요 데모는 `project-writing-v1`을 명시적으로 선택합니다. `src/writing_synthesis/prompts/source.py`는 K–12 출처별 척도를 지원합니다.
예전 3개 학년용 임시 루브릭·프롬프트·평가 스키마는 삭제했습니다.
데이터 계약은 `src/writing_synthesis/schemas/`에 모았으며 `src/writing_synthesis/workflows/`에는 별도의 State 정의를 두지 않습니다.

`elem_6`, `mid_2`, `high_2`와 `essay` 장르는 더 이상 허용하지 않습니다. 학년과 장르를 생략하면
`us_6`, `narrative`를 사용하며 두 실행 모드 모두 과제 설명이 필요합니다.
이전 임시 형식의 저장 결과는 자동 변환하지 않으며 현재 API에서 읽을 수 없습니다.
기존 DB 파일은 그대로 두고 현재 계약으로 새로 실행합니다.

## 모델 서버 없이 실행하기

저장소 루트에서:

```sh
uv sync --all-packages --locked
cd writing_data_synthesis
uv run --all-packages --locked python -m writing_synthesis.cli.mock_smoke --data-dir ../.local-data/writing-data-synthesis/mock-smoke
```

실제 API 수명 주기로 6학년 프로젝트 루브릭 요청을 실행하고, 결과 조회와 종료 후 SQLite 재열기까지 확인합니다.
실행 ID와 결과 파일 경로를 출력합니다.

UI를 사용하려면 `writing_data_synthesis/frontend`에서 `npm ci`를 한 번 실행한 뒤, 저장소 루트에서:

```sh
uv run --all-packages --locked python -m writing_synthesis.cli.ui
```

[로컬 UI](http://127.0.0.1:18742)에서 가상 예시를 채워 실행할 수 있습니다.
실행 명령은 항상 Mock 모드이며 API/UI를 18741/18742 포트에 띄웁니다. Ctrl+C로 둘 다 종료합니다.
사용 중인 포트는 오류를 내며 `--api-port`, `--ui-port`로 다른 포트를 직접 지정할 수 있습니다.
실행 ID를 보관하면 재시작 후에도 조회할 수 있습니다. 화면의 최근 실행 목록은 현재 페이지 세션 범위입니다.

## API와 설정

| 경로 | 역할 |
| --- | --- |
| `POST /run` | 글 생성·평가 또는 기존 글 평가 |
| `GET /runs/{run_id}` | 저장된 상태·글·점수·오류 정보 조회 |
| `GET /criteria?family=project` | 확정된 39개 학년·글 유형 조합 확인 |
| `GET /runtime` | 제공자 설정을 노출하지 않고 Mock/live/unknown 실행 모드 확인 |

주요 루브릭 요청은 `rubric_id: "project-writing-v1"`, `us_6` 같은 학년, 지원하는 `genre`,
과제인 `user_prompt`를 지정합니다. 생성 모드는 학생·검수자 학년을 같게 하고 `level`을 지정합니다.
평가 전용 모드는 `essay`를 추가합니다. 논증문에는 `source_passages`가 필요합니다.
루브릭 ID를 생략한 기존 요청은 기관별 기본값을 유지합니다.

<details>
<summary>모델 연결과 저장 설정</summary>

공유 환경은 [Python 3.13](../docs/python_environment.md)입니다.
실제 연결 어댑터는 OpenAI SDK의 텍스트 Chat Completions 형식을 사용하며 Ollama 전용 SDK는 필요하지 않습니다.

| 변수 | 기본값 / 용도 |
| --- | --- |
| `WDS_LLM_MODE` | `openai`; UI·Smoke 실행 명령은 명시적으로 `mock` 적용 |
| `WDS_DATA_DIR` | 저장소의 `.local-data/writing-data-synthesis/` |
| `WDS_LLM_BASE_URL` | `http://localhost:11434/v1` |
| `WDS_LLM_MODEL` | `gpt-oss:20b` |
| `WDS_LLM_API_KEY` | 루프백은 임시값, 원격 서버는 명시적으로 지정 |
| `WDS_LLM_TIMEOUT_SECONDS` | `120`; 전체 실행이 아닌 HTTP 호출 제한 시간 |
| `WDS_LLM_TEMPERATURE` | 지정하지 않으면 생략 |
| `WDS_LLM_JSON_MODE` | `false`; 모델 제공자가 지원할 때만 활성화 |
| `WDS_API_URL` | Next.js 프록시 대상. 기본값 `http://127.0.0.1:18741` |

SQLite는 WAL과 리비전 검사, 추가 기록 방식의 스냅샷을 사용합니다.
공개 조회에는 내부 프롬프트와 제공자 설정이 포함되지 않습니다. 앱 수명마다 모델 클라이언트를 생성·종료하고,
외부에서 주입한 워크플로의 자원은 호출자가 관리합니다. 일반 `OPENAI_API_KEY`, `OPENAI_BASE_URL`은 읽지 않습니다.
빈 응답·거부·잘린 모델 응답은 명시적으로 실패 처리합니다.

</details>

## 검증과 현재 범위

저장소 루트에서:

```sh
uv run --all-packages --locked python -m unittest discover -s writing_data_synthesis/tests -t writing_data_synthesis -q
uvx ruff check writing_data_synthesis
```

학년·글 유형 선택, 점수 계약, 목표 수준 분리, 실패 기록, 동시 실행, 저장 충돌과 재시작 후 조회를 검증합니다.
전체 프로젝트 조합을 API와 저장까지 확인하려면 모듈 폴더에서 `python -m writing_synthesis.cli.catalog_smoke --family project`에
`--data-dir`을 지정해 실행합니다. UI는 Playwright로 데스크톱·모바일 동작과 저장 조회를 확인했고,
평가 불가 표시는 별도 모의 응답으로 확인했습니다.

**구현됨:** 한 번의 생성·평가, 스키마 검증, 루브릭 선택, 모델 어댑터, API, 저장과 로컬 UI.
**미구현:** 채택·거절 규칙, 재생성, 데이터셋 일괄 내보내기, 자동 복구, 인증과 운영 환경.
실제 모델 출력의 품질, 평가 신뢰도, 학습 라벨로서의 적합성은 검증하지 않았습니다.

[MIT License](../LICENSE). 외부 참고 자료에는 각 자료의 이용 조건이 적용됩니다.
