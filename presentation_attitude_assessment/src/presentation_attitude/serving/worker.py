"""Single local worker, with OS lock and explicit recovery on restart."""

import fcntl
import logging
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from threading import Event

from presentation_attitude.artifacts import sha256
from presentation_attitude.serving.contracts import (
    Analyzer,
    JobRepository,
    LocalWorkerRepository,
)
from presentation_attitude.serving.files import LocalJobFiles
from presentation_attitude.serving.settings import Settings
from presentation_attitude.serving.store import JobStore

logger = logging.getLogger(__name__)


@contextmanager
def worker_lock(directory):
    """POSIX local filesystem only. The OS releases this lock even after SIGKILL."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "worker.lock").open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Another worker already owns this data directory"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class JobWorker:
    """Connect repository transitions, local artifacts and an injected analyzer.

    run_once() can be used in tests or an owned worker loop. This object does
    not acquire the single-worker lock or recover interrupted jobs itself;
    run_worker() owns that process-level policy.
    """

    def __init__(
        self, store: JobRepository, analyzer: Analyzer, *, files: LocalJobFiles
    ):
        self.store, self.analyzer, self.files = store, analyzer, files

    def run_once(self) -> bool:
        """Claim and process at most one queued attempt.

        Returns False when the queue is empty, True after handling an attempt,
        even if analysis failed. Analysis exceptions become a failed attempt;
        interruptions are recorded then re-raised. Repository failures propagate
        when the attempt cannot be finalized. Retries are always explicit.
        """
        job = self.store.claim()
        if job is None:
            return False
        directory = self.files.job_dir(job["id"])
        try:
            source = directory / "source.video"
            if sha256(source) != job["source_sha256"]:
                raise ValueError("Uploaded video integrity check failed")
            output = directory / f"attempt-{job['attempt']}"
            result = self.analyzer(source, output, job["mode"])
            self.store.finish(job["id"], job["attempt"], result=result)
        except Exception as error:
            logger.exception("Job %s attempt %s failed", job["id"], job["attempt"])
            self.store.finish(
                job["id"],
                job["attempt"],
                error={
                    "code": "analysis_failed",
                    "type": type(error).__name__,
                    "message": "Analysis failed. Check the local worker log before retrying.",
                },
            )
        except BaseException:
            self.store.finish(
                job["id"],
                job["attempt"],
                error={
                    "code": "worker_interrupted",
                    "message": "Worker stopped; retry this job.",
                },
            )
            raise
        return True


def run_worker(
    settings: Settings,
    analyzer_factory: Callable[[], Analyzer],
    stop: Event,
    *,
    poll_seconds=1,
    once=False,
    store_factory: Callable[[Path], LocalWorkerRepository] = JobStore,
    files: LocalJobFiles | None = None,
) -> None:
    # Lock precedes both recovery and model load; a second worker changes nothing.
    """Own the local worker lock, startup recovery and sequential polling loop.

    analyzer_factory is called once after exclusive lock acquisition and
    recovery. stop requests shutdown between jobs; it does not cancel a
    running analysis. once handles at most one claim, including an empty queue.
    Lock release is guaranteed on exit; this policy assumes one local worker
    and is not a multi-host lease mechanism.
    """
    with worker_lock(settings.data_dir):
        store = store_factory(settings.data_dir)
        recovered = store.recover_interrupted()
        logger.info("Recovered %s interrupted jobs as failed", recovered)
        analyzer = analyzer_factory()
        worker = JobWorker(
            store,
            analyzer,
            files=files if files is not None else LocalJobFiles(settings.data_dir),
        )
        logger.info("Worker ready: %s", settings.data_dir)
        while not stop.is_set():
            worked = worker.run_once()
            if once:
                break
            if not worked:
                stop.wait(poll_seconds)
