"""Essay generation without workflow state mutation."""

from writing_synthesis.agents.base import BaseAgent


class AgentStudent(BaseAgent):
    """Generate English essays from prepared task and grade instructions."""
    def generate(self, *, system_prompt: str, assignment: str) -> str:
        """Request an essay and reject missing or blank generated text.

        Args:
            system_prompt: Prepared role instructions and the selected rubric.
            assignment: Writing task with any source passages supplied by the caller.

        Returns:
            Nonblank generated English essay.

        Raises:
            ValueError: Student must return a non-empty essay_english string.
        """
        result = self._complete_json(
            system_prompt=system_prompt, user_content=assignment, label="Student"
        )
        essay = result.get("essay_english")
        if not isinstance(essay, str) or not essay.strip():
            raise ValueError("Student must return a non-empty essay_english string.")
        return essay
