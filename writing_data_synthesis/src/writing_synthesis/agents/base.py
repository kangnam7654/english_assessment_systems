"""Shared model interface and JSON response parsing."""

import json
from json import JSONDecodeError
from typing import Any

from writing_synthesis.llm.types import LanguageModel


class BaseAgent:
    """Share completion and JSON parsing across generator and assessor roles."""
    def __init__(self, llm: LanguageModel):
        """Store the injected model client without creating a second connection.

        Args:
            llm: Injected language-model client implementing the shared completion contract.
        """
        self._llm = llm

    def _complete_json(
        self, *, system_prompt: str, user_content: str, label: str
    ) -> dict[str, Any]:
        """Send the same text-only message contract for both agent roles.

        Args:
            system_prompt: Prepared role instructions and the selected rubric.
            user_content: User-role task content sent separately from system instructions.
            label: Agent role label used in parse-error messages.

        Returns:
            Parsed model output as a JSON object.
        """
        response = self._llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
        return self.parse_json(response, label)

    @staticmethod
    def parse_json(raw: str, agent_label: str = "Agent") -> dict[str, Any]:
        """Accept a JSON object, optionally surrounded by model prose/fences.

        Args:
            raw: Raw model response text to parse.
            agent_label: Agent role label used in parse-error messages.

        Returns:
            Parsed JSON object extracted from the response text.

        Raises:
            TypeError: The provider response is not text.
            ValueError: The response contains no valid, nonempty JSON object.
        """
        if not isinstance(raw, str):
            raise TypeError(f"Expected a text response ({agent_label}).")
        try:
            result = json.loads(raw)
        except JSONDecodeError:
            text = raw.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                raise ValueError(f"No JSON object found in LLM result ({agent_label}).")
            result = json.loads(text[start:end])
        if not isinstance(result, dict) or not result:
            raise ValueError(f"Expected a non-empty JSON object ({agent_label}).")
        return result
