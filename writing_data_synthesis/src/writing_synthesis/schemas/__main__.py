"""Export JSON Schema documents from the Python contracts.

Run from writing_data_synthesis:
    uv run --all-packages --locked python -m writing_synthesis.schemas --output-dir /path/to/schemas
"""

import argparse
import json
from pathlib import Path

from writing_synthesis.schemas.api import ErrorResponse, RunDetail, RunResponse
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import WorkflowState


def main() -> None:
    """Export public Pydantic contracts as JSON Schema documents."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    output = parser.parse_args().output_dir
    output.mkdir(parents=True, exist_ok=True)
    for model in (
        WorkflowRequest,
        WorkflowState,
        RunResponse,
        ErrorResponse,
        RunDetail,
    ):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (output / f"{model.__name__}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Exported 5 schema documents to {output.resolve()}")


if __name__ == "__main__":
    main()
