# config.py
from langchain_ollama import ChatOllama

from agents.state import AgentState, Grade, Level, Mode
from workflow_builder import build_workflow

LLM_MODEL = "gpt-oss:20b"
LLM_TEMPERATURE = 0


def create_llm() -> ChatOllama:
    return ChatOllama(model=LLM_MODEL, temperature=LLM_TEMPERATURE)


def create_graph():
    """LLM과 workflow graph를 생성한다. 프로세스당 1회 호출."""
    llm = create_llm()
    return build_workflow(llm)


def create_initial_state(
    *,
    mode: Mode = "synthesis",
    user_prompt: str | None = None,
    grade_for_student: Grade = "mid_2",
    grade_for_assessor: Grade = "mid_2",
    level: Level = "intermediate",
    essay: str | None = None,
) -> AgentState:
    return {
        "system_prompt": None,
        "user_prompt": user_prompt,
        "essay": essay if mode == "assessment" else None,
        "assessed_content": None,
        "grade_for_student": grade_for_student,
        "grade_for_assessor": grade_for_assessor,
        "level": level,
        "mode": mode,
        "next_agent": None,
    }
