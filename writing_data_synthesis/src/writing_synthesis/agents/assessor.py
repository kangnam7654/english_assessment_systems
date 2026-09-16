"""Rubric assessment without access to the generator's target level."""

import json
from typing import Literal

from writing_synthesis.agents.base import BaseAgent
from writing_synthesis.schemas.assessment import Assessment, SourceAssessment
from writing_synthesis.schemas.project_assessment import (
    ProjectAssessment,
    ProjectJudgment,
)


class AgentAssessor(BaseAgent):
    """Request rubric judgments and validate the selected assessment contract."""
    def assess(
        self,
        *,
        system_prompt: str,
        essay: str,
        assignment: str | None,
        assessment_kind: Literal["source", "project"],
        source_use_applicable: bool = False,
    ) -> Assessment:
        # Explicitly construct the payload instead of passing the workflow state.
        """Assess an essay and derive project display scores outside the model.

        Args:
            system_prompt: Prepared role instructions and the selected rubric.
            essay: English essay to assess.
            assignment: Writing task with any source passages supplied by the caller.
            assessment_kind: Selected output contract: project or source.
            source_use_applicable: Whether the task requires a separate source-use judgment.

        Returns:
            Validated source assessment or project assessment with derived display scores.
        """
        payload = json.dumps(
            {"assignment": assignment, "essay": essay}, ensure_ascii=False
        )
        result = self._complete_json(
            system_prompt=system_prompt, user_content=payload, label="Assessor"
        )
        if assessment_kind == "project":
            return ProjectAssessment.from_judgment(
                ProjectJudgment.model_validate(result),
                source_use_applicable=source_use_applicable,
            )
        return SourceAssessment.model_validate(result)
