"""A narrow model-facing JSON schema for only the selected rubric's dimensions."""

from typing import Any

from writing_synthesis.criteria.resolver import ResolvedCriteria


def assessment_output_schema(criteria: ResolvedCriteria) -> dict[str, Any]:
    """Build the model output contract for the selected rubric's dimensions and ranges.

    Args:
        criteria: Resolved grade, genre, rubric, and provenance.

    Returns:
        JSON-compatible description of the required assessment output.
    """
    rubric = criteria.rubric
    text = {"type": "string", "minLength": 1, "pattern": r"\S"}
    dimensions = {
        name: {
            "type": "object",
            "additionalProperties": False,
            "required": ["score", "comment_english", "comment_korean"],
            "properties": {
                "score": {"type": "integer", "minimum": low, "maximum": high},
                "comment_english": text,
                "comment_korean": text,
            },
        }
        for name, (low, high) in rubric["score_ranges"].items()
    }
    fields = {
        "schema_version": {"const": "source-1.0"},
        "rubric_id": {"const": rubric["id"]},
        "grade": {"const": criteria.grade},
        "genre": {"const": criteria.genre},
        "status": {"enum": ["scored", "not_scorable"]},
        "per_criterion": {
            "anyOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(dimensions),
                    "properties": dimensions,
                },
                {"type": "null"},
            ]
        },
        "total_score": {
            "anyOf": [
                {
                    "type": "integer",
                    "minimum": sum(r[0] for r in rubric["score_ranges"].values()),
                    "maximum": sum(r[1] for r in rubric["score_ranges"].values()),
                },
                {"type": "null"},
            ]
        },
        "not_scorable_reason": {"enum": [*rubric["not_scorable"], None]},
        "summary_feedback_english": text,
        "summary_feedback_korean": text,
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(fields),
        "properties": fields,
    }
