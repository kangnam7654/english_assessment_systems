# agents/assessor.py
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from agents.base import BaseAgent
from agents.state import AgentState, ContextState


class AgentAssessor(BaseAgent):
    """
    Orchestrator가 넣어준 Assessor system_prompt를 사용해
    state["essay"]를 평가하는 에이전트.
    """

    def __call__(self, state: AgentState, runtime: Runtime[ContextState]) -> AgentState:
        llm = runtime.context["llm"]

        system_prompt = state.get("system_prompt") or ""
        if not system_prompt:
            raise ValueError("system_prompt is missing in state for AgentAssessor.")

        essay = state.get("essay") or ""
        if not essay:
            raise ValueError("No essay found in state['essay'] for AgentAssessor.")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=essay),
        ]

        llm_result = llm.invoke(messages)
        result = self.parse_json(llm_result.content, "Assessor")

        state["assessed_content"] = result
        return state
