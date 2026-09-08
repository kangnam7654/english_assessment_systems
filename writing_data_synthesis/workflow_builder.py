from pathlib import Path

from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from agents.assessor import AgentAssessor
from agents.orchestrator import AgentOrchestrator
from agents.state import AgentState, ContextState
from agents.student import AgentStudent


def router_fn(state: AgentState) -> str:
    next_agent = state.get("next_agent") or END
    return next_agent


def build_workflow(llm: ChatOllama):
    context_state: ContextState = {"llm": llm}

    agent_student = AgentStudent()
    agent_assessor = AgentAssessor()
    prompt_root = Path(__file__).resolve().parent / "prompts"
    agent_orchestrator = AgentOrchestrator(
        student_template_path=str(prompt_root / "system_prompts/student.md"),
        assessor_template_path=str(prompt_root / "system_prompts/assessor.md"),
        rubric_path=str(prompt_root / "rubric/rubric.json"),
    )

    workflow = StateGraph(state_schema=AgentState, context_schema=ContextState)
    workflow.add_node("orchestrator", agent_orchestrator)
    workflow.add_node("student", agent_student)
    workflow.add_node("assessor", agent_assessor)
    workflow.set_entry_point("orchestrator")

    workflow.add_conditional_edges(
        "orchestrator",
        router_fn,
        {
            "student": "student",
            "assessor": "assessor",
            END: END,
        },
    )
    workflow.add_edge("student", "orchestrator")
    workflow.add_edge("assessor", END)

    graph = workflow.compile()
    return graph, context_state
