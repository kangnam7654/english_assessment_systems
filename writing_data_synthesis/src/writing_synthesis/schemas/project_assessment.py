"""Project judgments and application-derived display scores, never source equating."""

from typing import Literal, Self

from pydantic import Field, model_validator

from writing_synthesis.criteria.catalog import select_route
from writing_synthesis.schemas.common import Genre, Record, Text, USGrade


class ProjectDimension(Record):
    """Store a raw 1–4 project judgment with bilingual feedback."""
    score: int = Field(strict=True, ge=1, le=4)
    comment_english: Text
    comment_korean: Text


class ProjectCriteria(Record):
    """Group the four core dimensions shared by project writing rubrics."""
    task_content: ProjectDimension
    organization: ProjectDimension
    language_expression: ProjectDimension
    conventions: ProjectDimension


class ProjectNormalizedScores(Record):
    """Store application-derived display positions on a 0–100 scale."""
    task_content: float = Field(strict=True, ge=0, le=100)
    organization: float = Field(strict=True, ge=0, le=100)
    language_expression: float = Field(strict=True, ge=0, le=100)
    conventions: float = Field(strict=True, ge=0, le=100)


def display_score(score: int) -> float:
    """An ordinal position for display, not percent mastery or a calibrated score.

    Args:
        score: Raw ordinal rubric score.

    Returns:
        Rounded ordinal display position from 0 to 100; not percent mastery.

    Raises:
        ValueError: A project score must be an integer from 1 to 4.
    """
    if type(score) is not int or not 1 <= score <= 4:
        raise ValueError("A project score must be an integer from 1 to 4.")
    return round((score - 1) * 100 / 3, 2)


class ProjectJudgment(Record):
    """Only these fields are requested from the model; derived values are excluded."""

    schema_version: Literal["project-1.0"] = "project-1.0"
    rubric_id: Literal["project-writing-v1"] = "project-writing-v1"
    grade: USGrade
    genre: Genre
    status: Literal["scored", "not_scorable"]
    per_criterion: ProjectCriteria | None
    source_use: ProjectDimension | None
    not_scorable_reason: Literal["insufficient_text", "non_english"] | None
    summary_feedback_english: Text
    summary_feedback_korean: Text

    @model_validator(mode="after")
    def check_judgment(self) -> Self:
        """Validate grade routing and scored versus unscorable judgment fields.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: Not-scorable judgments must have null scores; Not-scorable judgments
                need a reason; Scored judgments need core scores and no NS reason.
        """
        select_route(self.grade, self.genre, self.rubric_id)
        if self.status == "not_scorable":
            if self.per_criterion is not None or self.source_use is not None:
                raise ValueError("Not-scorable judgments must have null scores.")
            if self.not_scorable_reason is None:
                raise ValueError("Not-scorable judgments need a reason.")
        elif self.per_criterion is None or self.not_scorable_reason is not None:
            raise ValueError("Scored judgments need core scores and no NS reason.")
        return self


class ProjectAssessment(ProjectJudgment):
    """Persist raw judgments and verified display values together for round trips."""

    normalization_method: Literal["minmax_display_v1"] = "minmax_display_v1"
    normalized_scores: ProjectNormalizedScores | None
    source_use_applicable: bool = Field(strict=True)
    source_use_status: Literal["scored", "not_applicable", "not_scorable"]
    source_use_normalized: float | None = Field(strict=True, ge=0, le=100)

    @classmethod
    def from_judgment(
        cls, judgment: ProjectJudgment, *, source_use_applicable: bool
    ) -> Self:
        """Derive display values from a validated raw judgment and task applicability.

        Args:
            judgment: Validated model judgment before display-score derivation.
            source_use_applicable: Whether the task requires a separate source-use judgment.

        Returns:
            Assessment combining raw judgments with validated display values.
        """
        derived = cls._derived(judgment, source_use_applicable)
        return cls.model_validate(
            {
                **judgment.model_dump(),
                **derived,
                "source_use_applicable": source_use_applicable,
            }
        )

    @staticmethod
    def _derived(judgment: ProjectJudgment, applicable: bool) -> dict:
        """Compute display positions and source-use status from raw ordinal judgments.

        Args:
            judgment: Validated model judgment before display-score derivation.
            applicable: Whether source use applies to this task.

        Returns:
            Derived normalized scores and source-use status fields.

        Raises:
            ValueError: Source-use score must match task applicability and status.
        """
        scored = judgment.status == "scored"
        if (judgment.source_use is not None) != (applicable and scored):
            raise ValueError(
                "Source-use score must match task applicability and status."
            )
        normalized = None
        if judgment.per_criterion is not None:
            normalized = {
                name: display_score(getattr(judgment.per_criterion, name).score)
                for name in ProjectCriteria.model_fields
            }
        return {
            "normalized_scores": normalized,
            "source_use_status": (
                "not_applicable"
                if not applicable
                else "scored"
                if scored
                else "not_scorable"
            ),
            "source_use_normalized": (
                display_score(judgment.source_use.score)
                if judgment.source_use is not None
                else None
            ),
        }

    @model_validator(mode="after")
    def check_derived_values(self) -> Self:
        """Reject stored display values inconsistent with raw judgments.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: Display scores/status must match raw project judgments.
        """
        expected = self._derived(self, self.source_use_applicable)
        actual = self.model_dump(include=set(expected))
        if actual != expected:
            raise ValueError("Display scores/status must match raw project judgments.")
        return self
