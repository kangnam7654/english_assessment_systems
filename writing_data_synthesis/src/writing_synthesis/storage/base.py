"""Storage boundary independent of the workflow and HTTP layer."""

from typing import Protocol
from uuid import UUID

from writing_synthesis.schemas.run import WorkflowState


class StorageError(RuntimeError):
    """Persistence failed; callers must not report a successful stored run."""


class RunStore(Protocol):
    """Define persistence and retrieval of immutable workflow snapshots."""
    def save(self, state: WorkflowState) -> None:
        """Persist one validated workflow revision.

        Args:
            state: Validated immutable workflow snapshot.
        """
        ...
    def get(self, run_id: UUID) -> WorkflowState | None:
        """Read the latest snapshot for a run, or None when absent.

        Args:
            run_id: Unique identifier of the persisted workflow run.

        Returns:
            Latest validated workflow state, or None when the run is absent.
        """
        ...
