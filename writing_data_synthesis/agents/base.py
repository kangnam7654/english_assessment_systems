import json
from json import JSONDecodeError

from langgraph.runtime import Runtime

from agents.state import AgentState, ContextState


class BaseAgent:
    """Base class for all agents."""

    def __call__(self, state: AgentState, runtime: Runtime[ContextState]) -> AgentState:
        raise NotImplementedError

    @staticmethod
    def parse_json(raw: str, agent_label: str = "Agent") -> dict:
        """LLM 응답에서 JSON을 파싱한다. 실패 시 첫 번째 {...} 블록을 추출한다."""
        try:
            return json.loads(raw)
        except JSONDecodeError:
            text = raw.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                raise ValueError(f"No JSON object found in LLM result ({agent_label}).")
            return json.loads(text[start:end])
