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

        Args:
            source: Source video path or caller-owned input stream, as required by this
                operation.
            output: Destination directory or file for generated artifacts.
            mode: Requested execution mode.

        Returns:
            JSON-serializable analysis result.
        """
        ...


class Conflict(ValueError):
    """The requested transition no longer applies to the current job attempt."""


class JobRepository(Protocol):
    """Define atomic job transitions independently of a storage backend."""
    def health(self) -> str:
        """Check connectivity (raise on failure) and return the backend name.

        Returns:
            Name of the reachable repository backend.
        """
        ...

    def create(
        self, job_id: str, filename: str, source_sha256: str, size_bytes: int, mode: str
    ) -> Job:
        """Publish a queued job only after its input is durably available.

        Args:
            job_id: Server-generated job identifier.
            filename: Sanitized display name of the uploaded video.
            source_sha256: SHA-256 digest of the uploaded source bytes.
            size_bytes: Number of uploaded source bytes.
            mode: Requested execution mode.

        Returns:
            Queued job snapshot.
        """
        ...

    def get(self, job_id: str) -> Job:
        """Return a consistent job/attempt snapshot; raise KeyError if absent.

        Args:
            job_id: Server-generated job identifier.

        Returns:
            Consistent job and attempt snapshot.
        """
        ...

    def claim(self) -> Job | None:
        """Atomically claim one queued job and increment its attempt number.

        Returns:
            Claimed job and its new attempt, or None when the queue is empty.
        """
        ...

    def finish(
        self,
        job_id: str,
        number: int,
        *,
        result: Job | None = None,
        error: Job | None = None,
    ) -> None:
        """Accept exactly one result/error for the active attempt, else Conflict.

        Args:
            job_id: Server-generated job identifier.
            number: Attempt number expected to be active.
            result: Successful JSON-serializable analysis result, mutually exclusive with
                error.
            error: Failure details, mutually exclusive with result.
        """
        ...

    def retry(self, job_id: str) -> Job:
        """Requeue a failed job, preserving attempts; else KeyError or Conflict.

        Args:
            job_id: Server-generated job identifier.

        Returns:
            Requeued job snapshot with earlier attempts preserved.
        """
        ...


class LocalWorkerRepository(JobRepository, Protocol):
    """Add startup recovery required by the exclusively locked local worker."""
    def recover_interrupted(self) -> int:
        """Fail running jobs ONLY under an exclusive lock covering this repository.

        This is a single-worker recovery policy, not a distributed lease mechanism.

        Returns:
            Number of running jobs marked failed during startup recovery.
        """
        ...
