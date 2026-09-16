"""Reproduction metadata. Credentials and raw exception messages are excluded."""

import hashlib
from typing import Literal, Self

from pydantic import Field, model_validator

from writing_synthesis.schemas.common import Digest, Grade, Record, Text


class CriteriaReference(Record):
    """Record the rubric and standards versions used by one agent role."""
    role: Literal["student", "assessor"]
    rubric_id: Text
    rubric_version: Text
    rubric_sha256: Digest
    grade: Grade
    standard_ids: tuple[Text, ...] = ()
    standards_sha256: Digest | None = None
    source_urls: tuple[Text, ...] = ()
    crosswalk_sha256: Digest | None = None
    grade_file_sha256: Digest | None = None
    source_kind: Literal["official_source_adaptation", "project_synthesis"]


class PromptSnapshot(Record):
    """Persist exact system prompt text with its integrity hash."""
    role: Literal["student", "assessor"]
    system_prompt: Text
    sha256: Digest

    @model_validator(mode="after")
    def verify_hash(self) -> Self:
        """Check that the prompt hash matches the exact stored system text.

        Returns:
            This validated record, unchanged.

        Raises:
            ValueError: Prompt hash does not match the captured text.
        """
        if hashlib.sha256(self.system_prompt.encode()).hexdigest() != self.sha256:
            raise ValueError("Prompt hash does not match the captured text.")
        return self


class ModelSnapshot(Record):
    """Store allowed model settings without API keys or provider secrets."""
    execution_mode: Literal["live", "mock", "unknown"] = "unknown"
    adapter: Text
    model: Text | None = None
    base_url: Text | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    json_mode: bool | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
