"""Discoverable source-based routes, including provider alternatives."""

from typing import Literal

from pydantic import Field

from writing_synthesis.schemas.common import Genre, Record, Text, USGrade


class RubricOption(Record):
    """Describe one supported grade/genre/provider choice for API clients."""
    grade: USGrade
    genre: Genre
    rubric_id: Text
    rubric_version: Text
    provider: Text
    is_default: bool
    requires_sources: bool
    score_ranges: dict[str, tuple[int, int]]
    not_scorable_reasons: tuple[Text, ...]
    scope_notes: tuple[Text, ...]
    family: Literal["source", "project"] = "source"
    optional_score_ranges: dict[str, tuple[int, int]] = Field(default_factory=dict)
    source_urls: tuple[Text, ...] = ()
    source_url: Text | None
    notice: Text
