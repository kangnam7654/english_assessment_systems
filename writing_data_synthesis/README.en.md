# English Writing Data Synthesis

[한국어](README.md) · [Monorepo](../README.en.md) · [Grade rubrics](criteria/README.en.md)

[Repository layout](../docs/repository_structure.md)
**Generate writing for a selected grade and target level, assess it independently, and
retain enough context to inspect the result.** This is a portfolio reconstruction of an
English writing data-generation workflow associated with the author's Creverse work.
It contains no company code or private student data.

The current implementation runs one generation/assessment cycle, or assesses a supplied
essay. The API, validation and persistence paths are verified with **fixed Mock outputs**.
Actual model quality and educational validity are unverified; Mock output is not a dataset.

## How it works

```text
Request → select grade/genre rubric → generate essay → assess → save result
                                     skipped for assessment-only
Each stage → immutable state snapshot → SQLite
```

For example, a grade-6 argumentative request selects the grade-6 file and its argumentative
criteria. The generator receives the assignment, passages, criteria and target level. The
assessor receives the same task and criteria plus the essay, without the generation target.
Application code validates the returned scores and computes display values.

The finalized rubric has 13 grade files and 39 grade/genre combinations. Content,
organization, expression and conventions receive separate 1–4 ratings; source use is
conditional. The 0–100 display values are neither an overall score nor a cross-grade ability
measure. [Read the rubric](criteria/README.en.md) or [inspect its sources](docs/rubric-evidence/README.en.md).

## Design decisions

| Decision | Why it is implemented this way |
| --- | --- |
| Python controls the workflow | Stage order and branching are deterministic and visible in one runner; no LLM orchestrator or LangGraph is needed for this single cycle. |
| Generator and assessor have separate inputs | The requested generation level is excluded from assessment inputs, reducing a direct source of evaluation bias. This does not prove independent or accurate judgments. |
| Validate model output at the boundary | Pydantic checks required fields, score ranges, grade/genre identity and unscorable states before a result can be marked complete. |
| Depend on a small model interface | Agents call `LanguageModel.complete`; the OpenAI SDK adapter and network-free Mock implement that contract. |
| Persist state separately from model calls | `RunStore` separates execution from SQLite. Saved stages, criteria hashes and exact prompts support inspection after failures and restarts. |

The workflow state is a record of one run, not conversational memory shared between users.
`POST /run` waits for completion. Interrupted runs can be inspected, but are not resumed
automatically. A storage failure does not confirm that a result was saved.

## Read the code in this order

1. [WorkflowRequest](src/writing_synthesis/schemas/request.py) — accepted inputs and task constraints.
2. [WritingWorkflow.run](src/writing_synthesis/workflows/runner.py) — the complete generation/assessment sequence.
3. [PromptPreparation](src/writing_synthesis/prompts/preparation.py) and [ResolvedCriteria](src/writing_synthesis/criteria/resolver.py) — selected rubric, role inputs and provenance.
4. [Student](src/writing_synthesis/agents/student.py) and [assessor](src/writing_synthesis/agents/assessor.py) — model calls and output validation; [project scores](src/writing_synthesis/schemas/project_assessment.py) — application-derived values.
5. [LanguageModel](src/writing_synthesis/llm/types.py), [OpenAI adapter](src/writing_synthesis/llm/client.py) and [Mock](src/writing_synthesis/llm/mock.py) — provider boundary.
6. [WorkflowState](src/writing_synthesis/schemas/run.py) and [SQLiteRunStore](src/writing_synthesis/storage/sqlite.py) — transitions, revisions and persistence.

[app.py](src/writing_synthesis/app.py) owns application resources; [api/routes.py](src/writing_synthesis/api/routes.py) translates HTTP
requests and results. [frontend/](frontend/) is a local interaction surface, not the workflow
implementation. [Tests](tests/integration/) exercise the same backend with Mock models and
fake SDK transport.

The primary demo explicitly selects `project-writing-v1`. `src/writing_synthesis/prompts/source.py` supports
source-specific K–12 score contracts. The former three-grade prototype, its prompt
files and temporary scoring schema have been removed. Data contracts live in `src/writing_synthesis/schemas/`;
there is no second state definition in `src/writing_synthesis/workflows/`.

Requests using `elem_6`, `mid_2`, `high_2` or genre `essay` are rejected. Omitted grade and
genre now default to `us_6` and `narrative`; both modes require an assignment. Old prototype
snapshots are not migrated or readable through the current API. Existing database files
are left intact; use a new run to exercise the current contracts.

## Run without a model server

From the repository root:

```sh
uv sync --all-packages --locked
cd writing_data_synthesis
uv run --all-packages --locked python -m writing_synthesis.cli.mock_smoke --data-dir ../.local-data/writing-data-synthesis/mock-smoke
```

This submits a grade-6 project-rubric request through the real API lifecycle, retrieves the
result and reopens SQLite after shutdown. It prints the run ID and result-file path.

For the optional UI, run `npm ci` once in `writing_data_synthesis/frontend`, then from the
repository root:

```sh
uv run --all-packages --locked python -m writing_synthesis.cli.ui
```

Open [the local UI](http://127.0.0.1:18742), fill the fictional example and run it. The launcher
always selects Mock, starts API/UI on 18741/18742, and stops both with Ctrl+C. Occupied ports
fail explicitly; use `--api-port` and `--ui-port` to choose alternatives. Saved run IDs remain
usable after restart; the UI's recent-run selector covers only its current page session.

## API and configuration

| Endpoint | Purpose |
| --- | --- |
| `POST /run` | Generate and assess, or assess an existing essay |
| `GET /runs/{run_id}` | Retrieve saved state, essay, scores and safe error information |
| `GET /criteria?family=project` | Discover the 39 finalized grade/genre selections |
| `GET /runtime` | Identify Mock/live/unknown execution mode without provider settings |

Requests for the primary rubric specify `rubric_id: "project-writing-v1"`, a grade such as
`us_6`, a supported `genre`, and `user_prompt`. Synthesis uses matching student/assessor
grades and a `level`; assessment-only adds `essay`. Argumentative tasks require
`source_passages`. Existing requests without a rubric ID retain provider-specific defaults.

<details>
<summary>Model configuration and storage details</summary>

The shared environment is [Python 3.13](../docs/python_environment.md). The live adapter uses
the OpenAI SDK's text-only Chat Completions format. No Ollama-specific SDK is required.

| Variable | Default / purpose |
| --- | --- |
| `WDS_LLM_MODE` | `openai`; the UI and smoke launchers explicitly force `mock` |
| `WDS_DATA_DIR` | Defaults to `.local-data/writing-data-synthesis/` in the repository |
| `WDS_LLM_BASE_URL` | `http://localhost:11434/v1` |
| `WDS_LLM_MODEL` | `gpt-oss:20b` |
| `WDS_LLM_API_KEY` | Loopback placeholder; explicitly required for remote servers |
| `WDS_LLM_TIMEOUT_SECONDS` | `120`, per HTTP call rather than the whole workflow |
| `WDS_LLM_TEMPERATURE` | Omitted unless configured |
| `WDS_LLM_JSON_MODE` | `false`; enable only if supported by the provider |
| `WDS_API_URL` | Next.js proxy destination, default `http://127.0.0.1:18741` |

SQLite uses WAL and append-only, revision-checked snapshots. Public retrieval excludes
internal prompts and provider settings. Each API lifespan creates and closes its model
client; caller-injected workflows retain caller ownership. Ambient `OPENAI_API_KEY` and
`OPENAI_BASE_URL` are not used. Empty, refused and truncated model responses fail explicitly.

</details>

## Verification and scope

From the repository root:

```sh
uv run --all-packages --locked python -m unittest discover -s writing_data_synthesis/tests -t writing_data_synthesis -q
uvx ruff check writing_data_synthesis
```

Tests cover grade/genre routing, score contracts, target-level isolation, failure records,
concurrent runs, storage conflicts and restart retrieval. To exercise all 39 project
selections through API/storage in both modes, run `python -m writing_synthesis.cli.catalog_smoke --family project`
with `--data-dir` from the module directory. The UI has also been exercised with Playwright
on desktop/mobile, including persisted retrieval and an unscorable response fixture.

**Implemented:** one-cycle orchestration, validated contracts, rubric routing, adapters,
API, persistence and local UI. **Not implemented:** acceptance/rejection rules, regeneration,
batch dataset export, automatic recovery, authentication or production operations.
Real model outputs, scoring reliability and suitability as training labels remain unverified.

[MIT License](../LICENSE); external reference materials retain their own terms.
