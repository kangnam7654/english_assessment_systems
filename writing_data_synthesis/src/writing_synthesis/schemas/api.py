"""Public response, excluding internal prompts and provider credentials."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from writing_synthesis.schemas.assessment import Assessment
from writing_synthesis.schemas.common import Genre, Grade, Level, Record, Text
from writing_synthesis.schemas.run import RunError, Stage, WorkflowState


class RunResponse(Record):
    """Expose a completed run, essay, and validated assessment to API clients."""
    schema_version: Literal["1.0"] = "1.0"
    execution_mode: Literal["live", "mock", "unknown"] = "unknown"
    run_id: UUID
    stage: Literal["completed"] = "completed"
    grade: Grade
    # Retained for existing UI compatibility: requested, not assessed, level.
    level: Level
    essay: Text
    assessed_content: Assessment


class FailedRunResponse(Record):
    """Describe the failed stage using safe public error codes and messages."""
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    stage: Literal["failed"] = "failed"
    failed_stage: Literal["preparing", "generating", "assessing"]
    code: Literal["preparation_failed", "invalid_output", "model_call_failed"]
    message: Text


class ErrorResponse(Record):
    """Wrap a failed run in the API error response envelope."""
    detail: FailedRunResponse


class RunDetail(Record):
    """Public snapshot: essay and safe errors, without prompts or provider settings."""

    run_id: UUID
    revision: int
    stage: Stage
    execution_mode: Literal["live", "mock", "unknown"]
    grade: Grade
    genre: Genre
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    essay: Text | None
    assessed_content: Assessment | None
    error: RunError | None

    @classmethod
    def from_state(cls, state: WorkflowState) -> "RunDetail":
        """Project internal workflow state onto the public retrieval response.

        Args:
            state: Validated immutable workflow snapshot.

        Returns:
            Public run detail excluding internal prompts and provider configuration.
        """
        return cls(
            run_id=state.run_id,
            revision=state.revision,
            stage=state.stage,
            execution_mode=state.model.execution_mode,
            grade=state.request.grade_for_assessor,
            genre=state.request.genre,
            created_at=state.created_at,
            finished_at=state.finished_at,
            essay=state.essay,
            assessed_content=state.assessed_content,
            error=state.error,
        )
