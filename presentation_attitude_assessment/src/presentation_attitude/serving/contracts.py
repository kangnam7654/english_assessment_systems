"""Storage contracts shared by API and workers; no database or ML imports."""

from pathlib import Path
from typing import Any, Literal, Protocol

Job = dict[str, Any]
AnalysisMode = Literal["features", "assessment"]


class Analyzer(Protocol):
    """Synchronous analysis callable injected into a worker; no ML import required."""

    def __call__(
        self, source: Path, output: Path, mode: AnalysisMode
    ) -> dict[str, Any]:
        """Analyze an existing input into a fresh attempt directory.

        Return a JSON-serializable result or raise for the worker to record failure.
        The callable owns its model resources and may be reused across jobs.
        """
        ...


class Conflict(ValueError):
    """The requested transition no longer applies to the current job attempt."""


class JobRepository(Protocol):
    def health(self) -> str:
        """Check connectivity (raise on failure) and return the backend name."""
        ...

    def create(
        self, job_id: str, filename: str, source_sha256: str, size_bytes: int, mode: str
    ) -> Job:
        """Publish a queued job only after its input is durably available."""
        ...

    def get(self, job_id: str) -> Job:
        """Return a consistent job/attempt snapshot; raise KeyError if absent."""
        ...

    def claim(self) -> Job | None:
        """Atomically claim one queued job and increment its attempt number."""
        ...

    def finish(
        self,
        job_id: str,
        number: int,
        *,
        result: Job | None = None,
        error: Job | None = None,
    ) -> None:
        """Accept exactly one result/error for the active attempt, else Conflict."""
        ...

    def retry(self, job_id: str) -> Job:
        """Requeue a failed job, preserving attempts; else KeyError or Conflict."""
        ...


class LocalWorkerRepository(JobRepository, Protocol):
    def recover_interrupted(self) -> int:
        """Fail running jobs ONLY under an exclusive lock covering this repository.

        This is a single-worker recovery policy, not a distributed lease mechanism.
        """
        ...
