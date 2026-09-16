"""Prepare agent inputs and their provenance without running models or saving state."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from writing_synthesis.criteria.catalog import source_use_applies
from writing_synthesis.criteria.resolver import ResolvedCriteria
from writing_synthesis.prompts.project import build_project_prompt
from writing_synthesis.prompts.source import build_source_prompt
from writing_synthesis.schemas.provenance import CriteriaReference, PromptSnapshot
from writing_synthesis.schemas.request import WorkflowRequest

AgentRole = Literal["student", "assessor"]


@dataclass(frozen=True)
class PreparedPrompt:
    """Keep the exact text snapshot paired with the criteria that produced it."""

    reference: CriteriaReference
    snapshot: PromptSnapshot

    @property
    def text(self) -> str:
        """Return the exact system text stored in the prompt snapshot.

        Returns:
            Exact system prompt text.
        """
        return self.snapshot.system_prompt


class PromptPreparation:
    """Resolve the selected K–12 rubric once for both agent roles."""

    def __init__(self, request: WorkflowRequest):
        """Resolve the request's assessment rubric once for both role prompts.

        Args:
            request: Validated task, grade, genre, mode, and optional source/essay inputs.
        """
        self._request = request
        self._resolved = ResolvedCriteria(
            request.grade_for_assessor, request.genre, request.rubric_id
        )

    @property
    def assessment_kind(self) -> Literal["source", "project"]:
        """Return the source or project output contract for the resolved rubric.

        Returns:
            The string project or source for the selected output contract.
        """
        return "project" if self.uses_project_rubric else "source"

    @property
    def uses_project_rubric(self) -> bool:
        """Report whether the selected rubric uses project-derived display scores.

        Returns:
            Whether the resolved rubric is a project rubric.
        """
        return self._resolved.rubric.get("assessment_kind") == "project"

    @property
    def source_use_applicable(self) -> bool:
        """Determine source-use applicability from the request, not model output.

        Returns:
            Whether supplied sources should be assessed for the requested genre.
        """
        return source_use_applies(
            self._request.genre, bool(self._request.source_passages)
        )

    @property
    def rubric_id(self) -> str:
        """Return the resolved rubric identifier.

        Returns:
            Identifier of the resolved rubric.
        """
        return self._resolved.rubric["id"]

    @property
    def assignment(self) -> str:
        """Serialize the task, genre, and source passages as user-role content.

        Returns:
            JSON string containing task, genre, and source passages.
        """
        request = self._request
        return json.dumps(
            {
                "task": request.user_prompt,
                "genre": request.genre,
                "source_passages": [p.model_dump() for p in request.source_passages],
            },
            ensure_ascii=False,
        )

    def build(self, role: AgentRole) -> PreparedPrompt:
        """Build a role prompt and pair its exact text hash with criteria provenance.

        Args:
            role: Agent role receiving the prompt: student or assessor.

        Returns:
            Prepared system prompt paired with its text hash and criteria reference.
        """
        request = self._request
        level = request.level if role == "student" else None
        if self.uses_project_rubric:
            text = build_project_prompt(
                self._resolved,
                role,
                level=level,
                source_use_applicable=self.source_use_applicable,
            )
        else:
            text = build_source_prompt(self._resolved, role, level)
        reference = self._resolved.reference(role)
        return PreparedPrompt(
            reference=reference,
            snapshot=PromptSnapshot(
                role=role,
                system_prompt=text,
                sha256=hashlib.sha256(text.encode()).hexdigest(),
            ),
        )
