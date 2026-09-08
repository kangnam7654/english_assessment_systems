# agents/orchestrator.py
import logging

from langgraph.graph import END
from langgraph.runtime import Runtime

from agents.base import BaseAgent
from agents.state import AgentState, ContextState
from prompts.builder import SystemPromptBuilder


class AgentOrchestrator(BaseAgent):
    def __init__(
        self,
        student_template_path: str,
        assessor_template_path: str,
        rubric_path: str,
    ):
        super().__init__()
        self.student_template_path = student_template_path
        self.assessor_template_path = assessor_template_path
        self.prompt_builder = SystemPromptBuilder(rubric_path)

    def __call__(self, state: AgentState, runtime: Runtime[ContextState]) -> AgentState:
        mode = state.get("mode") or "synthesis"
        essay = state.get("essay") or ""
        grade_for_student = state.get("grade_for_student") or "mid_2"
        grade_for_assessor = state.get("grade_for_assessor") or grade_for_student
        level = state.get("level") or "intermediate"
        if mode == "synthesis":
            next_agent = "student"
        elif mode == "assessment":
            next_agent = "assessor"
        else:
            logging.warning(f"Unknown mode: {mode}, ending workflow.")
            next_agent = END

        state["next_agent"] = next_agent

        # system_prompt 생성
        if next_agent == "student":
            system_prompt = self.prompt_builder.build_student_prompt(
                template_path=self.student_template_path,
                grade=grade_for_student,
                level=level,
            )
        elif next_agent == "assessor":
            system_prompt = self.prompt_builder.build_assessor_prompt(
                template_path=self.assessor_template_path,
                grade=grade_for_assessor,
            )
        else:
            system_prompt = None

        state["system_prompt"] = system_prompt
        return state
