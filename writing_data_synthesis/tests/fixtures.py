"""Offline requests and responses for tests, not educational labels."""

# Keep source-contract tests independent of the portfolio demo's rubric selection.
SOURCE_REQUEST = {
    "mode": "synthesis",
    "grade_for_student": "us_6",
    "grade_for_assessor": "us_6",
    "genre": "argumentative",
    "rubric_id": "sb-argumentative-summary-v2",
    "level": "intermediate",
    "user_prompt": "Should a school create a garden? Use the supplied passage.",
    "source_passages": [
        {
            "source_id": "test-passage-1",
            "text": "Fictional practice passage: A school garden offers a place to observe plants, but requires regular watering.",
        }
    ],
}


def assessment(score=3, grade="us_6", genre="narrative"):
    """A source-scale judgment, independent of runtime Mock implementation.

    Args:
        score: Raw ordinal rubric score.
        grade: Requested US grade identifier, from us_K through us_12.
        genre: Requested writing genre.

    Returns:
        Valid source-assessment dictionary with the requested fixture scores.
    """
    dimensions = (
        ["organization_purpose", "evidence_elaboration", "conventions"]
        if genre == "argumentative"
        else ["organization_purpose", "development_elaboration", "conventions"]
    )
    return {
        "schema_version": "source-1.0",
        "rubric_id": "sb-argumentative-summary-v2"
        if genre == "argumentative"
        else "sb-narrative-summary-v1",
        "grade": grade,
        "genre": genre,
        "status": "scored",
        "total_score": score * 2 + 2,
        "not_scorable_reason": None,
        "per_criterion": {
            name: {
                "score": 2 if name == "conventions" else score,
                "comment_english": "Some support is present.",
                "comment_korean": "일부 근거가 있습니다.",
            }
            for name in dimensions
        },
        "summary_feedback_english": "Explain the supporting details.",
        "summary_feedback_korean": "뒷받침하는 내용을 설명하세요.",
    }
