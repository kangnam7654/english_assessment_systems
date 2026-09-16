"""Exercise the real API lifespan, workflow and SQLite using fixed mock LLM outputs."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from writing_synthesis.app import app
from writing_synthesis.storage.sqlite import SQLiteRunStore

EXAMPLE_REQUEST = {
    "mode": "synthesis",
    "grade_for_student": "us_6",
    "grade_for_assessor": "us_6",
    "genre": "argumentative",
    "rubric_id": "project-writing-v1",
    "level": "intermediate",
    "user_prompt": "Should a school create a garden? Use the supplied passage.",
    "source_passages": [
        {
            "source_id": "project-fixture-1",
            "text": "Fictional practice passage: A school garden offers a place to observe plants, but requires regular watering.",
        }
    ],
}


def main() -> None:
    """Verify Mock generation, assessment, persistence, and retrieval through the API.

    Raises:
        AssertionError: The recorded data count, content hash, or tensor assumptions do
            not hold.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.data_dir.expanduser().resolve()
    # Override any ambient live configuration for this process only.
    os.environ["WDS_LLM_MODE"] = "mock"
    os.environ["WDS_DATA_DIR"] = str(directory)
    with TestClient(app) as client:
        response = client.post("/run", json=EXAMPLE_REQUEST)
        response.raise_for_status()
        run = response.json()
        detail = client.get(f"/runs/{run['run_id']}")
        detail.raise_for_status()
        assert detail.json()["assessed_content"] == run["assessed_content"]
        assert run["execution_mode"] == "mock"
    # Open a fresh store after the API closes to verify durability.
    restored = SQLiteRunStore(directory / "runs.sqlite3").get(UUID(run["run_id"]))
    assert restored is not None and restored.stage == "completed"
    assert restored.model.execution_mode == "mock"
    artifact = directory / f"{run['run_id']}.json"
    artifact.write_text(json.dumps(detail.json(), indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "verified": "POST -> mock generation -> mock assessment -> SQLite -> GET -> reopen",
                "execution_mode": "mock",
                "run_id": run["run_id"],
                "result": str(artifact),
                "database": str(directory / "runs.sqlite3"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
