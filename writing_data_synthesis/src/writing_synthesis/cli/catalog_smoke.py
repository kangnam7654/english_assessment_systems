"""Run every supported provider route through Mock API, SQLite and retrieval."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from writing_synthesis.app import create_app
from writing_synthesis.criteria.catalog import available_routes
from writing_synthesis.storage.sqlite import SQLiteRunStore


def example_request(
    option: dict, mode: str = "synthesis", level: str = "intermediate"
) -> dict:
    """Project-authored task material, not a real student or benchmark example.

    Args:
        option: One grade/genre/rubric option returned by the catalog.
        mode: Requested execution mode.
        level: Requested generation difficulty; omitted for assessment.

    Returns:
        Synthetic request payload suitable for the selected rubric option.
    """
    genre = option["genre"]
    tasks = {
        "opinion": "Would you prefer a garden or a reading corner? Explain your choice.",
        "argumentative": "Argue whether the school should create a garden; use the supplied sources.",
        "informative": "Explain how a school garden works, using the supplied information when available.",
        "narrative": "Tell a story about a child finding a seed at school.",
    }
    body = {
        "grade_for_student": option["grade"],
        "grade_for_assessor": option["grade"],
        "genre": genre,
        "rubric_id": option["rubric_id"],
        "level": level,
        "mode": mode,
        "user_prompt": tasks[genre],
    }
    if option["requires_sources"]:
        body["source_passages"] = [
            {
                "source_id": "project-fixture-1",
                "text": "Fictional practice note: A school garden lets students observe plant growth.",
            },
            {
                "source_id": "project-fixture-2",
                "text": "Fictional practice note: Plants need regular watering, including during holidays.",
            },
            {
                "source_id": "project-fixture-3",
                "text": "Fictional practice note: A shared schedule helps a class care for its garden.",
            },
        ]
    if mode == "assessment":
        body["essay"] = (
            "This is a fixed mock input for plumbing verification, not a student answer."
        )
    return body


def main() -> None:
    """Exercise every selected catalog route through the Mock API and SQLite store.

    Raises:
        AssertionError: The recorded data count, content hash, or tensor assumptions do
            not hold.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--family", choices=("source", "project"), default="source")
    args = parser.parse_args()
    directory = args.data_dir.expanduser().resolve()
    os.environ["WDS_LLM_MODE"] = "mock"
    os.environ["WDS_DATA_DIR"] = str(directory)
    runs = []
    with TestClient(create_app()) as client:
        options = client.get("/criteria", params={"family": args.family}).json()
        assert len(options) == len(available_routes(args.family))
        for option in options:
            for mode in ("synthesis", "assessment"):
                response = client.post("/run", json=example_request(option, mode))
                response.raise_for_status()
                body = response.json()
                detail = client.get(f"/runs/{body['run_id']}")
                detail.raise_for_status()
                assert detail.json()["assessed_content"] == body["assessed_content"]
                assert body["execution_mode"] == "mock"
                assert body["assessed_content"]["rubric_id"] == option["rubric_id"]
                runs.append(
                    {
                        "run_id": body["run_id"],
                        "grade": option["grade"],
                        "genre": option["genre"],
                        "rubric_id": option["rubric_id"],
                        "mode": mode,
                        "stage": body["stage"],
                    }
                )
    store = SQLiteRunStore(directory / "runs.sqlite3")
    for row in runs:
        state = store.get(UUID(row["run_id"]))
        assert state is not None and state.stage == "completed"
    result = {
        "execution_mode": "mock",
        "family": args.family,
        "default_routes": sum(o["is_default"] for o in options),
        "provider_choices": len(options),
        "rubrics": len({o["rubric_id"] for o in options}),
        "completed_runs": len(runs),
        "reopened_after_shutdown": True,
        "runs": runs,
    }
    output = directory / "catalog-smoke.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))
    print(output)


if __name__ == "__main__":
    main()
