"""Translate HTTP requests/results without creating clients or owning workflow state."""

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from writing_synthesis.criteria.catalog import available_routes
from writing_synthesis.schemas.api import (
    ErrorResponse,
    FailedRunResponse,
    RunDetail,
    RunResponse,
)
from writing_synthesis.schemas.catalog import RubricOption
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.storage.base import StorageError
from writing_synthesis.workflows.runner import WorkflowExecutionError, WritingWorkflow

logger = logging.getLogger(__name__)
router = APIRouter()


def get_workflow(request: Request) -> WritingWorkflow:
    """Read resources from this app, never from a module-global test override.

    Args:
        request: Validated writing request or HTTP request supplying app-scoped
            resources.

    Returns:
        Workflow owned by the current FastAPI application.
    """
    return request.app.state.workflow


WorkflowDependency = Annotated[WritingWorkflow, Depends(get_workflow)]


@router.post(
    "/run", response_model=RunResponse, responses={500: {"model": ErrorResponse}}
)
def run_agent(req: WorkflowRequest, workflow: WorkflowDependency):
    """Execute a writing workflow and expose validated results or a safe failed-run response.

    Args:
        req: Validated writing request received by the API.
        workflow: Optional injected workflow whose lifetime remains caller-owned.

    Returns:
        Completed-run response or a safe JSON error response for a failed workflow.

    Raises:
        HTTPException: The requested resource, operation, or submitted input cannot be
            accepted.
    """
    request = req

    try:
        final_state = workflow.run(request)

        return RunResponse(
            run_id=final_state.run_id,
            execution_mode=final_state.model.execution_mode,
            stage=final_state.stage,
            grade=request.grade_for_assessor,
            level=request.level,
            essay=final_state.essay,
            assessed_content=final_state.assessed_content,
        )
    except StorageError as exc:
        raise HTTPException(
            503, "Run storage unavailable; completion is not confirmed."
        ) from exc
    except WorkflowExecutionError as exc:
        state = exc.state
        logger.error(
            "Run %s failed at %s (%s)",
            state.run_id,
            state.failed_stage,
            state.error.code,
        )
        failure = FailedRunResponse(
            run_id=state.run_id,
            failed_stage=state.failed_stage,
            code=state.error.code,
            message=state.error.message,
        )
        raise HTTPException(
            status_code=500, detail=failure.model_dump(mode="json")
        ) from exc


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: UUID, workflow: WorkflowDependency):
    """Retrieve a saved workflow as a public response snapshot.

    Args:
        run_id: Unique identifier of the persisted workflow run.
        workflow: Optional injected workflow whose lifetime remains caller-owned.

    Returns:
        Public snapshot of the latest persisted workflow revision.

    Raises:
        HTTPException: The requested resource, operation, or submitted input cannot be
            accepted.
    """
    store = workflow.store
    if store is None:
        raise HTTPException(503, "Run storage is not configured.")
    try:
        state = store.get(run_id)
    except StorageError as exc:
        raise HTTPException(503, "Run storage unavailable.") from exc
    if state is None:
        raise HTTPException(404, "Run not found.")
    return RunDetail.from_state(state)


@router.get("/criteria", response_model=list[RubricOption])
def get_criteria(family: Literal["source", "project"] = "source"):
    """List supported grade/genre/provider combinations and their native score ranges.

    Args:
        family: Rubric family to expose: source or project.

    Returns:
        Supported catalog options with score ranges and source provenance.
    """
    return available_routes(family)


@router.get("/runtime")
def get_runtime(workflow: WorkflowDependency):
    """Expose the execution mode without provider configuration or credentials.

    Args:
        workflow: Optional injected workflow whose lifetime remains caller-owned.

    Returns:
        Public execution-mode metadata without provider credentials.
    """
    return {"execution_mode": workflow.model.execution_mode}
