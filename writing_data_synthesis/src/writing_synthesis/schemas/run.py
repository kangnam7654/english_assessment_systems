"""Versioned run records with validated, immutable transitions and JSON round trips."""

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator

from writing_synthesis.criteria.catalog import source_use_applies
from writing_synthesis.schemas.assessment import Assessment, SourceAssessment
from writing_synthesis.schemas.common import Record, Text, utc_now
from writing_synthesis.schemas.project_assessment import ProjectAssessment
from writing_synthesis.schemas.provenance import (
    CriteriaReference,
    ModelSnapshot,
    PromptSnapshot,
)
from writing_synthesis.schemas.request import WorkflowRequest


class Stage(StrEnum):
    """Enumerate the allowed workflow lifecycle stages."""
    PENDING = "pending"
    PREPARING = "preparing"
    GENERATING = "generating"
    ASSESSING = "assessing"
    COMPLETED = "completed"
    FAILED = "failed"


class StageEvent(Record):
    """Timestamp one transition in an immutable run history."""
    stage: Stage
    at: AwareDatetime = Field(default_factory=utc_now)


class EssayAttempt(Record):
    """Pair an essay with its origin, word count, and optional assessment."""
    number: int = Field(strict=True, ge=1)
    origin: Literal["generated", "provided"]
    essay: Text
    word_count: int = Field(strict=True, ge=1)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    assessment: Assessment | None = None

    @model_validator(mode="after")
    def check_word_count(self) -> Self:
        """Verify the stored count against whitespace-delimited essay words.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: word_count must match whitespace-delimited essay words.
        """
        if self.word_count != len(self.essay.split()):
            raise ValueError("word_count must match whitespace-delimited essay words.")
        return self


class RunError(Record):
    """Record a safe failure message and the stage that produced it."""
    stage: Stage
    code: Literal["preparation_failed", "invalid_output", "model_call_failed"]
    exception_type: Text
    message: Text


_TRANSITIONS = {
    Stage.PENDING: {Stage.PREPARING},
    Stage.PREPARING: {Stage.GENERATING, Stage.ASSESSING, Stage.FAILED},
    Stage.GENERATING: {Stage.ASSESSING, Stage.FAILED},
    Stage.ASSESSING: {Stage.COMPLETED, Stage.FAILED},
}


class WorkflowState(Record):
    """Serializable snapshot; persistence is delegated to a RunStore."""

    schema_version: Literal["1.0"] = "1.0"
    revision: int = Field(default=0, strict=True, ge=0)
    run_id: UUID = Field(default_factory=uuid4)
    request: WorkflowRequest
    model: ModelSnapshot = Field(
        default_factory=lambda: ModelSnapshot(adapter="unspecified")
    )
    stage: Stage = Stage.PENDING
    created_at: AwareDatetime = Field(default_factory=utc_now)
    finished_at: AwareDatetime | None = None
    events: tuple[StageEvent, ...] = Field(
        default_factory=lambda: (StageEvent(stage=Stage.PENDING),)
    )
    criteria: tuple[CriteriaReference, ...] = ()
    prompts: tuple[PromptSnapshot, ...] = ()
    attempts: tuple[EssayAttempt, ...] = ()
    error: RunError | None = None

    @property
    def history(self) -> list[Stage]:
        """Return the ordered stages recorded in the event history.

        Returns:
            Chronological list of recorded workflow stages.
        """
        return [event.stage for event in self.events]

    @property
    def essay(self) -> str | None:
        """Return the latest essay, or None before an attempt exists.

        Returns:
            Latest essay text, or None when no attempt exists.
        """
        return self.attempts[-1].essay if self.attempts else None

    @property
    def assessed_content(self) -> Assessment | None:
        """Return the latest assessment, or None before successful scoring.

        Returns:
            Latest validated assessment, or None before successful assessment.
        """
        return self.attempts[-1].assessment if self.attempts else None

    @property
    def failed_stage(self) -> Stage | None:
        """Return the failing stage, or None for runs without an error.

        Returns:
            Stage recorded in the run error, or None without an error.
        """
        return self.error.stage if self.error else None

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        """Validate transitions, timestamps, role provenance, and essay/assessment consistency.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: Stage history, timestamps, role provenance, essay origin, or assessment
                fields conflict with the request or current lifecycle stage.
        """
        if (
            not self.events
            or self.events[0].stage != Stage.PENDING
            or self.events[-1].stage != self.stage
        ):
            raise ValueError("Events must start pending and end at the current stage.")
        for previous, current in zip(self.events, self.events[1:]):
            if (
                current.stage not in _TRANSITIONS.get(previous.stage, set())
                or current.at < previous.at
            ):
                raise ValueError("Invalid or out-of-order stage history.")
        if self.events[0].at < self.created_at:
            raise ValueError("Events cannot precede run creation.")
        terminal = self.stage in {Stage.COMPLETED, Stage.FAILED}
        if terminal != (self.finished_at is not None):
            raise ValueError("Only terminal runs have finished_at.")
        if terminal and self.finished_at != self.events[-1].at:
            raise ValueError("finished_at must match the terminal event.")
        if self.stage == Stage.FAILED:
            if self.error is None or self.error.stage != self.events[-2].stage:
                raise ValueError("Failed runs require the failing stage and error.")
        elif self.error is not None:
            raise ValueError("Only failed runs have an error.")
        if [a.number for a in self.attempts] != list(range(1, len(self.attempts) + 1)):
            raise ValueError("Attempt numbers must be consecutive.")
        if self.request.mode == "assessment" and Stage.GENERATING in self.history:
            raise ValueError("Assessment-only runs cannot generate essays.")
        for records in (self.criteria, self.prompts):
            if len({record.role for record in records}) != len(records):
                raise ValueError("Criteria and prompt roles must be unique.")
        for reference in self.criteria:
            expected = (
                self.request.grade_for_student
                if reference.role == "student"
                else self.request.grade_for_assessor
            )
            if reference.grade != expected:
                raise ValueError("Criteria grade must match its request role.")
        if self.stage in {Stage.GENERATING, Stage.ASSESSING, Stage.COMPLETED}:
            roles = (
                {"assessor", "student"}
                if self.request.mode == "synthesis"
                else {"assessor"}
            )
            if {r.role for r in self.criteria} != roles or {
                p.role for p in self.prompts
            } != roles:
                raise ValueError(
                    "Active runs require criteria and prompts for their agent roles."
                )
        if self.stage in {Stage.ASSESSING, Stage.COMPLETED} and not self.attempts:
            raise ValueError("Assessment requires an essay attempt.")
        for attempt in self.attempts:
            expected_origin = (
                "provided" if self.request.mode == "assessment" else "generated"
            )
            if attempt.origin != expected_origin:
                raise ValueError("Essay origin must match the request mode.")
            if not self.created_at <= attempt.created_at <= self.events[-1].at:
                raise ValueError("Attempt timestamp must fall within the recorded run.")
            if (
                attempt.assessment
                and attempt.assessment.grade != self.request.grade_for_assessor
            ):
                raise ValueError(
                    "Assessment grade must match the requested assessor grade."
                )
            if isinstance(attempt.assessment, ProjectAssessment):
                expected_applicability = source_use_applies(
                    self.request.genre, bool(self.request.source_passages)
                )
                if attempt.assessment.source_use_applicable != expected_applicability:
                    raise ValueError("Source-use applicability must match the request.")
            if isinstance(attempt.assessment, (SourceAssessment, ProjectAssessment)):
                if attempt.assessment.genre != self.request.genre:
                    raise ValueError("Assessment genre must match the request.")
                if (
                    self.request.rubric_id is not None
                    and attempt.assessment.rubric_id != self.request.rubric_id
                ):
                    raise ValueError(
                        "Assessment must use the explicitly requested rubric."
                    )
        if self.stage == Stage.COMPLETED and self.assessed_content is None:
            raise ValueError("Completed runs require a validated assessment.")
        return self

    def evolve(self, **changes) -> Self:
        """Replace fields through validation; model_copy(update=...) skips validation.

        Args:
            **changes: Fields to replace in the next validated state revision.

        Returns:
            New validated state with an incremented revision.
        """
        return type(self).model_validate(
            {**self.model_dump(), **changes, "revision": self.revision + 1}
        )

    def advance(self, stage: Stage, **changes) -> Self:
        """Append a valid stage event and return a newly validated state revision.

        Args:
            stage: Next workflow stage to enter.
            **changes: Fields to replace in the next validated state revision.

        Returns:
            New state with incremented revision, appended event, and terminal time if
            applicable.

        Raises:
            ValueError: The requested stage is not an allowed next transition or the resulting
                state fails validation.
        """
        if stage not in _TRANSITIONS.get(self.stage, set()):
            raise ValueError(f"Invalid transition: {self.stage} -> {stage}")
        event = StageEvent(stage=stage)
        return self.evolve(
            **changes,
            stage=stage,
            events=(*self.events, event),
            finished_at=event.at if stage in {Stage.COMPLETED, Stage.FAILED} else None,
        )
