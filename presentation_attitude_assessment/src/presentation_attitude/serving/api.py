"""Upload and job APIs. This process never imports Torch or MediaPipe."""

import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from presentation_attitude.serving.contracts import (
    AnalysisMode,
    Conflict,
    JobRepository,
)
from presentation_attitude.serving.files import (
    EmptyUpload,
    LocalJobFiles,
    UploadTooLarge,
)
from presentation_attitude.serving.middleware import UploadLimit
from presentation_attitude.serving.settings import Settings
from presentation_attitude.serving.store import JobStore


def create_app(
    settings: Settings | None = None,
    *,
    store_factory: Callable[[Path], JobRepository] = JobStore,
    files: LocalJobFiles | None = None,
    ui_dir: Path | None = None,
) -> FastAPI:
    """Build the HTTP application without starting a worker or ML runtime.

    The lifespan creates one repository through store_factory(data_dir).
    files may select a separate local artifact root; ui_dir optionally mounts
    an already-built static UI. Neither the app factory nor HTTP polling loads
    Torch/MediaPipe. Use a lifespan-aware client when invoking it in tests.

    Args:
        settings: Validated configuration for this component.
        store_factory: Factory that creates the repository for the configured data
            directory.
        files: Local input and attempt-artifact storage.
        ui_dir: Optional directory containing a built static UI and index.html.

    Returns:
        Configured FastAPI application; resources start in its lifespan.

    Raises:
        FileNotFoundError: Build the inference UI before serving its directory.
    """
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        """Initialize app-scoped job storage before serving requests.

        Args:
            app: ASGI application or FastAPI instance whose lifecycle is being configured.

        Yields:
            Control while the application-owned resources are available.
        """
        app.state.store = store_factory(settings.data_dir)
        app.state.files = (
            files if files is not None else LocalJobFiles(settings.data_dir)
        )
        yield

    app = FastAPI(
        title="Presentation Attitude Assessment",
        description="Local portfolio API. Features are available without a classifier; assessment requires an attitude-training checkpoint. No authentication: bind to loopback.",
        lifespan=lifespan,
    )
    app.add_middleware(UploadLimit, limit=settings.max_upload_bytes + 64 * 1024)

    def get_job(job_id):
        """Look up a job or translate a missing identifier into HTTP 404.

        Args:
            job_id: Server-generated job identifier.

        Returns:
            Job snapshot returned by the repository.

        Raises:
            HTTPException: The requested resource, operation, or submitted input cannot be
                accepted.
        """
        try:
            return app.state.store.get(str(job_id))
        except KeyError:
            raise HTTPException(404, "Job not found") from None

    def status_view(job):
        # Full results belong to /result, not repeated status polls.
        """Build a lightweight polling response without embedding full analysis results.

        Args:
            job: Job snapshot including attempts and status.

        Returns:
            Polling response with status/result URLs and no embedded attempt results.
        """
        job = {
            **job,
            "attempts": [
                {k: v for k, v in item.items() if k != "result"}
                for item in job["attempts"]
            ],
        }
        job["status_url"] = f"/jobs/{job['id']}"
        job["result_url"] = f"/jobs/{job['id']}/result"
        return job

    @app.get("/health")
    def health():
        """Report API and queue availability without claiming worker readiness.

        Returns:
            API/queue status and upload limit; worker health is not probed.
        """
        backend = app.state.store.health()
        return {
            "api": "ready",
            "queue": backend,
            "worker": "separate process; not checked",
            "max_upload_bytes": settings.max_upload_bytes,
        }

    @app.post("/jobs", status_code=202)
    def upload(
        file: Annotated[
            UploadFile, File(description="Whole video: MP4, MOV, MKV, WebM or AVI")
        ],
        mode: Annotated[AnalysisMode, Query()] = "features",
    ):
        """Persist a bounded video upload and publish a queued analysis job.

        Args:
            file: Uploaded video file and its caller-owned input stream.
            mode: Requested execution mode.

        Returns:
            HTTP 202 response with job URLs and a Location header.

        Raises:
            HTTPException: The requested resource, operation, or submitted input cannot be
                accepted.
        """
        filename = Path((file.filename or "").replace("\\", "/")).name
        if Path(filename).suffix.lower() not in {
            ".mp4",
            ".m4v",
            ".mov",
            ".mkv",
            ".webm",
            ".avi",
        }:
            file.file.close()
            raise HTTPException(415, "Unsupported video extension")
        store = app.state.store
        job_id = uuid.uuid4().hex
        try:
            with app.state.files.stage_upload(
                job_id, file.file, max_bytes=settings.max_upload_bytes
            ) as uploaded:
                job = store.create(
                    job_id, filename[:255], uploaded.sha256, uploaded.size_bytes, mode
                )
        except EmptyUpload as error:
            raise HTTPException(400, str(error)) from error
        except UploadTooLarge as error:
            raise HTTPException(413, str(error)) from error
        finally:
            file.file.close()
        return JSONResponse(
            status_view(job), 202, headers={"Location": f"/jobs/{job_id}"}
        )

    @app.get("/jobs/{job_id}")
    def status(job_id: uuid.UUID):
        """Return the current job state and attempt history.

        Args:
            job_id: Server-generated job identifier.

        Returns:
            Current polling response for the requested job.
        """
        return status_view(get_job(job_id.hex))

    @app.get("/jobs/{job_id}/result")
    def result(job_id: uuid.UUID):
        """Return the latest successful analysis result, or reject unavailable results.

        Args:
            job_id: Server-generated job identifier.

        Returns:
            Latest successful attempt result.

        Raises:
            HTTPException: The requested resource, operation, or submitted input cannot be
                accepted.
        """
        job = get_job(job_id.hex)
        if job["status"] != "succeeded":
            raise HTTPException(
                409, {"message": "Result is not available", "status": job["status"]}
            )
        return job["attempts"][-1]["result"]

    @app.post("/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: uuid.UUID):
        """Explicitly requeue a failed job while retaining attempt history.

        Args:
            job_id: Server-generated job identifier.

        Returns:
            Polling response for the explicitly requeued job.

        Raises:
            HTTPException: The requested resource, operation, or submitted input cannot be
                accepted.
        """
        try:
            job = app.state.store.retry(job_id.hex)
        except KeyError:
            raise HTTPException(404, "Job not found") from None
        except Conflict as error:
            raise HTTPException(409, str(error)) from error
        return status_view(job)

    if ui_dir is not None:
        ui_dir = Path(ui_dir).resolve()
        if not (ui_dir / "index.html").is_file():
            raise FileNotFoundError(
                "Build the inference UI before serving its directory"
            )
        app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="inference-ui")

        @app.get("/", include_in_schema=False)
        def home():
            """Redirect the API root to the mounted inference UI.

            Returns:
                Redirect response pointing to /ui/.
            """
            return RedirectResponse("/ui/")

    return app
