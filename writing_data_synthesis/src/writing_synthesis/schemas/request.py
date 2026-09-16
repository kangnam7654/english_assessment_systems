"""One deterministic request; source texts are inputs, not instructions."""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from writing_synthesis.criteria.catalog import (
    load_rubric,
    requires_sources,
    select_route,
)
from writing_synthesis.schemas.common import Genre, Grade, Level, Mode, Record, Text


class SourcePassage(Record):
    """Represent one labeled source passage supplied with a writing task."""
    source_id: Text
    text: Text


class WorkflowRequest(Record):
    """Validate grade, genre, mode, essay, and task inputs before model calls."""
    schema_version: Literal["1.0"] = "1.0"
    mode: Mode = "synthesis"
    user_prompt: Text
    grade_for_student: Grade = "us_6"
    grade_for_assessor: Grade = "us_6"
    genre: Genre = "narrative"
    rubric_id: Text | None = None
    level: Level = "intermediate"
    essay: Text | None = None
    source_passages: tuple[SourcePassage, ...] = ()

    @model_validator(mode="after")
    def validate_task(self) -> Self:
        """Enforce supported routing and the required inputs for the requested mode.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: essay is required for assessment; source_passages must have unique
                source_id values; US synthesis requires matching student and assessor
                grades; This source-based rubric requires source passages.
        """
        if self.mode == "assessment" and self.essay is None:
            raise ValueError("essay is required for assessment.")
        ids = [source.source_id for source in self.source_passages]
        if len(set(ids)) != len(ids):
            raise ValueError("source_passages must have unique source_id values.")
        grades = {self.grade_for_assessor}
        if self.mode == "synthesis":
            grades.add(self.grade_for_student)
        if len(grades) != 1:
            raise ValueError(
                "US synthesis requires matching student and assessor grades."
            )
        route = select_route(self.grade_for_assessor, self.genre, self.rubric_id)
        rubric = load_rubric(Path(route["rubric"]).stem)
        if requires_sources(rubric, self.genre) and not self.source_passages:
            raise ValueError("This source-based rubric requires source passages.")
        return self
