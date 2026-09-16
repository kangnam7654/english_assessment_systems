"""Network-free fixed outputs for plumbing checks, never writing-quality evaluation."""

import json

from writing_synthesis.criteria.catalog import load_rubric
from writing_synthesis.llm.types import ChatMessage
from writing_synthesis.schemas.provenance import ModelSnapshot


class MockLLM:
    """Produce deterministic synthetic essays and rubric judgments for pipeline tests."""
    def describe(self) -> ModelSnapshot:
        """Identify this client as a Mock execution with no external model.

        Returns:
            Allowlisted model identity and execution settings without credentials.
        """
        return ModelSnapshot(
            adapter=type(self).__name__, model="fixed-fixture-v1", execution_mode="mock"
        )

    def close(self) -> None:
        """Complete the client lifecycle without releasing external resources."""
        pass

    def complete(self, messages: list[ChatMessage]) -> str:
        """Return deterministic JSON from the prepared role and rubric context.

        Args:
            messages: Ordered role/content messages sent to the chat completion endpoint.

        Returns:
            Completed assistant text; Mock clients produce deterministic synthetic JSON.

        Raises:
            ValueError: Mock received an unsupported prompt.
        """
        system = messages[0]["content"]
        if system.startswith("ROLE: student"):
            return json.dumps(
                {
                    "essay_english": (
                        "This is a fixed mock essay for pipeline verification. "
                        "It does not respond to the assignment and is not training data."
                    )
                }
            )
        comment = {
            "comment_english": "Fixed mock feedback; no evaluation performed.",
            "comment_korean": "고정 Mock 피드백입니다. 실제 평가는 수행하지 않았습니다.",
        }
        feedback = {
            "summary_feedback_english": comment["comment_english"],
            "summary_feedback_korean": comment["comment_korean"],
        }
        if system.startswith("ROLE: assessor"):
            prefix = "ASSESSMENT_CONTEXT_JSON: "
            context = next(
                line[len(prefix) :]
                for line in system.splitlines()
                if line.startswith(prefix)
            )
            identity = json.loads(context)
            rubric = load_rubric(identity["rubric_id"])
            if rubric.get("assessment_kind") == "project":
                applicable = identity.pop("source_use_applicable")
                return json.dumps(
                    {
                        **identity,
                        "schema_version": "project-1.0",
                        "status": "scored",
                        "not_scorable_reason": None,
                        "per_criterion": {
                            name: {"score": 3, **comment}
                            for name in rubric["score_ranges"]
                        },
                        "source_use": {"score": 3, **comment} if applicable else None,
                        **feedback,
                    }
                )
            scores = {
                name: high if high == 2 else high - 1
                for name, (low, high) in rubric["score_ranges"].items()
            }
            return json.dumps(
                {
                    **identity,
                    "schema_version": "source-1.0",
                    "status": "scored",
                    "total_score": sum(scores.values()),
                    "not_scorable_reason": None,
                    "per_criterion": {
                        name: {"score": score, **comment}
                        for name, score in scores.items()
                    },
                    **feedback,
                }
            )
        raise ValueError("Mock received an unsupported prompt.")
