"""Atomic snapshots with optimistic revision checks; no automatic job resumption."""

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from writing_synthesis.schemas.run import WorkflowState
from writing_synthesis.storage.base import StorageError


class SQLiteRunStore:
    """Use short-lived connections so concurrent requests never share a transaction."""

    def __init__(self, path: Path):
        """Initialize a versioned SQLite snapshot database with WAL journaling.

        Args:
            path: Filesystem path to the input or output artifact.

        Raises:
            StorageError: Unsupported run database version; Could not initialize run
                storage.
        """
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection, connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1}:
                    raise StorageError("Unsupported run database version.")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS run_snapshots (
                        run_id TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        state_json TEXT NOT NULL,
                        PRIMARY KEY (run_id, revision)
                    )
                """)
                connection.execute("PRAGMA user_version=1")
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("Could not initialize run storage.") from exc

    def _connect(self) -> sqlite3.Connection:
        """Open an operation-local SQLite connection with a five-second lock timeout.

        Returns:
            New SQLite connection owned by the caller.
        """
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def _latest(connection: sqlite3.Connection, run_id: UUID) -> tuple[int, str] | None:
        """Read the latest stored revision and serialized state within a transaction.

        Args:
            connection: SQLite connection owned by the current operation.
            run_id: Unique identifier of the persisted workflow run.

        Returns:
            Latest (revision, state_json) row, or None when the run is absent.
        """
        return connection.execute(
            """
            SELECT revision, state_json FROM run_snapshots
            WHERE run_id=? ORDER BY revision DESC LIMIT 1
            """,
            (str(run_id),),
        ).fetchone()

    @staticmethod
    def _validate_append(state: WorkflowState, row: tuple[int, str] | None) -> None:
        """Check continuity against the snapshot read inside the write transaction.

        Args:
            state: Validated immutable workflow snapshot.
            row: Latest (revision, serialized state) from this transaction, or None.

        Raises:
            StorageError: The revision conflicts, a terminal run is being changed, or immutable
                inputs and prior event history differ from the stored snapshot.
        """
        if row is None:
            if state.revision != 0 or state.stage != "pending":
                raise StorageError("A run must start pending at revision zero.")
            return
        revision, payload = row
        if state.revision != revision + 1:
            raise StorageError("Conflicting run revision.")
        previous = WorkflowState.model_validate_json(payload)
        if previous.stage in {"completed", "failed"}:
            raise StorageError("Terminal runs cannot be overwritten.")
        if (
            previous.request != state.request
            or previous.model != state.model
            or previous.created_at != state.created_at
        ):
            raise StorageError("Run inputs cannot change across revisions.")
        if state.events[: len(previous.events)] != previous.events:
            raise StorageError("Run history cannot be rewritten.")

    def save(self, state: WorkflowState) -> None:
        """Append one revision atomically, accepting an identical latest snapshot idempotently.

        Args:
            state: Validated immutable workflow snapshot.

        Raises:
            StorageError: Could not save run state.
        """
        payload = state.model_dump_json()
        try:
            with closing(self._connect()) as connection, connection:
                # Lock before reading the revision to avoid a check/write race.
                connection.execute("BEGIN IMMEDIATE")
                row = self._latest(connection, state.run_id)
                if row == (state.revision, payload):
                    return  # Retrying the exact latest snapshot is idempotent.
                self._validate_append(state, row)
                connection.execute(
                    "INSERT INTO run_snapshots (run_id, revision, state_json) VALUES (?, ?, ?)",
                    (str(state.run_id), state.revision, payload),
                )
        except (sqlite3.Error, ValidationError) as exc:
            raise StorageError("Could not save run state.") from exc

    def get(self, run_id: UUID) -> WorkflowState | None:
        """Load and validate the latest stored snapshot for a run.

        Args:
            run_id: Unique identifier of the persisted workflow run.

        Returns:
            Latest validated workflow state, or None when the run is absent.

        Raises:
            StorageError: Stored run identity mismatch; Could not read run state.
        """
        try:
            with closing(self._connect()) as connection:
                row = self._latest(connection, run_id)
            if row is None:
                return None
            state = WorkflowState.model_validate_json(row[1])
            if state.run_id != run_id:
                raise StorageError("Stored run identity mismatch.")
            return state
        except (sqlite3.Error, ValidationError) as exc:
            raise StorageError("Could not read run state.") from exc
