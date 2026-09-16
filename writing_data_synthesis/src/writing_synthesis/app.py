"""Application factory and resource lifetime; HTTP behavior lives in api.routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from writing_synthesis.api.routes import router
from writing_synthesis.config import create_llm, create_store
from writing_synthesis.workflows.runner import WritingWorkflow


def create_app(workflow: WritingWorkflow | None = None) -> FastAPI:
    """Create an isolated app; injected workflows remain owned by the caller.

    Without injection, each lifespan creates and closes its own model client.
    Importing this module does not open a database or create a model connection.

    Args:
        workflow: Optional injected workflow whose lifetime remains caller-owned.

    Returns:
        Configured FastAPI application; resources start in its lifespan.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Acquire app-owned workflow resources and close the model client on shutdown.

        Args:
            app: ASGI application or FastAPI instance whose lifecycle is being configured.

        Yields:
            Control while the application-owned resources are available.
        """
        if workflow is not None:
            app.state.workflow = workflow
            try:
                yield
            finally:
                del app.state.workflow
            return
        store = create_store()
        llm = create_llm()
        try:
            app.state.workflow = WritingWorkflow(llm, store)
            yield
        finally:
            llm.close()
            if hasattr(app.state, "workflow"):
                del app.state.workflow

    application = FastAPI(title="English Assessment API", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
