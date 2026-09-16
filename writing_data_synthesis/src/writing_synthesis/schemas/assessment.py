"""Score contracts for source-based and project rubric assessments."""

from typing import Literal, Self

from pydantic import Field, model_validator

from writing_synthesis.criteria.catalog import load_rubric
from writing_synthesis.schemas.common import Genre, Record, Text, USGrade
from writing_synthesis.schemas.project_assessment import ProjectAssessment


class ArgumentDimension(Record):
    """Store a 1–4 argument score with English and Korean feedback."""
    score: int = Field(strict=True, ge=1, le=4)
    comment_english: Text
    comment_korean: Text


class ConventionsDimension(Record):
    """Store a 0–2 conventions score with bilingual feedback."""
    score: int = Field(strict=True, ge=0, le=2)
    comment_english: Text
    comment_korean: Text


class ArgumentCriteria(Record):
    """Group the three dimensions of the original argument rubric."""
    organization_purpose: ArgumentDimension
    evidence_elaboration: ArgumentDimension
    conventions: ConventionsDimension


class ArgumentativeAssessment(Record):
    """Source-scale scores from a project adaptation, not validated official scoring."""

    rubric_id: Literal["sb-argumentative-summary-v1"]
    grade: Literal["us_6"]
    status: Literal["scored", "not_scorable"]
    per_criterion: ArgumentCriteria | None
    total_score: int | None = Field(strict=True, ge=2, le=10)
    not_scorable_reason: (
        Literal[
            "insufficient_including_copied", "non_english", "off_topic", "off_purpose"
        ]
        | None
    )
    summary_feedback_english: Text
    summary_feedback_korean: Text

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        """Check scored versus unscorable fields and the sum of argument dimensions.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: Scored essays require dimensions and no NS reason; total_score must
                equal the three dimension scores; Not-scorable essays require a reason and
                null scores.
        """
        if self.status == "scored":
            if self.per_criterion is None or self.not_scorable_reason is not None:
                raise ValueError("Scored essays require dimensions and no NS reason.")
            dimensions = self.per_criterion
            total = sum(
                d.score
                for d in (
                    dimensions.organization_purpose,
                    dimensions.evidence_elaboration,
                    dimensions.conventions,
                )
            )
            if total != self.total_score:
                raise ValueError("total_score must equal the three dimension scores.")
        elif (
            self.per_criterion is not None
            or self.total_score is not None
            or self.not_scorable_reason is None
        ):
            raise ValueError("Not-scorable essays require a reason and null scores.")
        return self


class SourceDimension(Record):
    """Store a source-scale score whose exact range is checked against its rubric."""
    score: int = Field(strict=True, ge=0, le=6)
    comment_english: Text
    comment_korean: Text


class NarrativeCriteria(Record):
    """Group organization, development, and conventions for narrative writing."""
    organization_purpose: SourceDimension
    development_elaboration: SourceDimension
    conventions: SourceDimension


class EarlyWritingCriteria(Record):
    """Group focus/organization and conventions for early writing."""
    focus_organization: SourceDimension
    conventions: SourceDimension


class OregonNarrativeCriteria(Record):
    """Represent the six-trait Oregon narrative scoring contract."""
    ideas_content: SourceDimension
    organization: SourceDimension
    voice: SourceDimension
    word_choice: SourceDimension
    sentence_fluency: SourceDimension
    conventions: SourceDimension


class OregonResearchCriteria(OregonNarrativeCriteria):
    """Extend the six writing traits with source-use evidence."""
    use_of_sources: SourceDimension


SourceCriteria = (
    ArgumentCriteria
    | NarrativeCriteria
    | EarlyWritingCriteria
    | OregonNarrativeCriteria
    | OregonResearchCriteria
)


class SourceAssessment(Record):
    """Validate against the selected immutable rubric, including exact dimensions."""

    schema_version: Literal["source-1.0"] = "source-1.0"
    rubric_id: Text
    grade: USGrade
    genre: Genre
    status: Literal["scored", "not_scorable"]
    per_criterion: SourceCriteria | None
    total_score: int | None = Field(strict=True, ge=0)
    not_scorable_reason: Text | None
    summary_feedback_english: Text
    summary_feedback_korean: Text

    @model_validator(mode="after")
    def validate_rubric(self) -> Self:
        """Enforce the selected rubric's scope, exact dimensions, score ranges, and total.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: The rubric scope, dimensions, score ranges, unscorable reason, or total
                do not match the selected source contract.
        """
        rubric = load_rubric(self.rubric_id)
        if rubric.get("assessment_kind") == "project":
            raise ValueError("Project rubrics require the project assessment contract.")
        grade = self.grade.removeprefix("us_")
        if grade not in {
            str(g) for g in rubric.get("grades", [])
        } or self.genre not in rubric.get("genres", []):
            raise ValueError("Assessment grade/genre is outside the rubric scope.")
        if self.status == "not_scorable":
            if self.per_criterion is not None or self.total_score is not None:
                raise ValueError("Not-scorable results must have null scores.")
            if self.not_scorable_reason not in rubric["not_scorable"]:
                raise ValueError("Not-scorable reason is not supported by this rubric.")
            return self
        if self.not_scorable_reason is not None or self.per_criterion is None:
            raise ValueError("Scored results require dimensions and no NS reason.")
        dimensions = {
            name: getattr(self.per_criterion, name)
            for name in type(self.per_criterion).model_fields
        }
        if set(dimensions) != set(rubric["score_ranges"]):
            raise ValueError(
                "Assessment dimensions must match the selected rubric exactly."
            )
        for name, dimension in dimensions.items():
            low, high = rubric["score_ranges"][name]
            if not low <= dimension.score <= high:
                raise ValueError(f"Score outside rubric range: {name}.")
        if self.total_score != sum(d.score for d in dimensions.values()):
            raise ValueError("Total must equal the sum of dimension scores.")
        return self


# Keep the original grade-6 contract readable for previously stored snapshots.
Assessment = ArgumentativeAssessment | SourceAssessment | ProjectAssessment
