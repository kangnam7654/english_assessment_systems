# app.py
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.state import Grade, Level, Mode
from config import create_graph, create_initial_state

logger = logging.getLogger(__name__)

graph, context_state = create_graph()


class RunRequest(BaseModel):
    mode: Mode = "synthesis"
    user_prompt: Optional[str] = "컴퓨터 코딩에 대한 취미생활인 삶에 대해 에세이를 써줘."
    grade_for_student: Grade = "mid_2"
    grade_for_assessor: Grade = "mid_2"
    level: Level = "intermediate"
    essay: Optional[str] = None


class RunResponse(BaseModel):
    grade: Optional[Grade] = None
    level: Optional[Level] = None
    essay: Optional[str] = None
    assessed_content: Optional[dict[str, Any]] = None


app = FastAPI(title="English Assessment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/run", response_model=RunResponse)
def run_agent(req: RunRequest):
    try:
        initial_state = create_initial_state(
            mode=req.mode,
            user_prompt=req.user_prompt,
            grade_for_student=req.grade_for_student,
            grade_for_assessor=req.grade_for_assessor,
            level=req.level,
            essay=req.essay,
        )

        final_state = graph.invoke(initial_state, context=context_state)

        return RunResponse(
            grade=final_state.get("grade"),
            level=final_state.get("level"),
            essay=final_state.get("essay"),
            assessed_content=final_state.get("assessed_content"),
        )
    except Exception:
        logger.exception("Pipeline execution failed")
        raise HTTPException(status_code=500, detail="Pipeline execution failed. Check server logs for details.")
