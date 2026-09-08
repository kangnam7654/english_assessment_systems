# agents/student.py
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from agents.base import BaseAgent
from agents.state import AgentState, ContextState


class AgentStudent(BaseAgent):
    """
    Orchestrator가 넣어준 system_prompt를 사용해
    해당 grade/level 수준의 에세이를 생성하는 에이전트.
    """

    def __call__(self, state: AgentState, runtime: Runtime[ContextState]) -> AgentState:
        llm = runtime.context["llm"]

        system_prompt = state.get("system_prompt") or ""
        user_prompt = state.get("user_prompt") or ""
        if not system_prompt:
            raise ValueError("system_prompt is missing in state for AgentStudent.")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        llm_result = llm.invoke(messages)
        result = self.parse_json(llm_result.content, "Student")

        essay = result.get("essay_english", "")
        if not essay:
            raise ValueError("LLM result does not contain 'essay_english'.")

        state["essay"] = essay
        state["mode"] = "assessment"

        return state
