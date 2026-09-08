from typing import Any, Literal, TypedDict

from langchain_ollama import ChatOllama

Grade = Literal["elem_6", "mid_2", "high_2"]
Level = Literal["beginner", "intermediate", "advanced", "master"]
Mode = Literal["synthesis", "assessment"]


class AgentState(TypedDict):
    # IO
    system_prompt: str | None
    user_prompt: str | None

    # 생성 및 평가 결과
    essay: str | None
    assessed_content: dict[str, Any] | None

    # 오케스트레이션 메타 정보
    grade_for_student: Grade | None
    grade_for_assessor: Grade | None
    level: Level | None
    mode: Mode | None
    next_agent: str | None


class ContextState(TypedDict):
    llm: ChatOllama
