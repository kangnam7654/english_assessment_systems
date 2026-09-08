"""SQLite queue and attempt history shared by the API and one local worker."""

import json
import sqlite3
import time
from contextlib import contextmanager

from presentation_attitude.serving.contracts import Conflict


class JobStore:
    """SQLite implementation of the job repository contracts.

    Each operation opens its own connection/transaction. No connection is
    shared across API threads and no video files are managed here. Queue
    claims and attempt checks remain in SQL so state transitions are atomic.
    """

    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.database = directory / "jobs.sqlite3"
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('features', 'assessment')),
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
                    attempt INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    error TEXT,
                    result TEXT,
                    PRIMARY KEY(job_id, number)
                );
                CREATE INDEX IF NOT EXISTS queued_jobs ON jobs(status, updated_at);
            """)

    @contextmanager
    def _connect(self):
        """Scope a private connection and commit or roll back its transaction."""
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, job_id, filename, source_sha256, size_bytes, mode):
        now = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?)",
                (job_id, filename, source_sha256, size_bytes, mode, now, now),
            )
        return self.get(job_id)

    def get(self, job_id):
        with self._connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            job = dict(row)
            job["attempts"] = []
            for row in db.execute(
                "SELECT * FROM attempts WHERE job_id=? ORDER BY number", (job_id,)
            ):
                attempt = dict(row)
                for field in ("error", "result"):
                    attempt[field] = (
                        json.loads(attempt[field]) if attempt[field] else None
                    )
                job["attempts"].append(attempt)
            return job

    def claim(self):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id, attempt FROM jobs WHERE status='queued' ORDER BY updated_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            now, number = time.time(), row["attempt"] + 1
            db.execute(
                "UPDATE jobs SET status='running', attempt=?, updated_at=? WHERE id=?",
                (number, now, row["id"]),
            )
            db.execute(
                "INSERT INTO attempts (job_id,number,status,started_at) VALUES (?,?,'running',?)",
                (row["id"], number, now),
            )
        return self.get(row["id"])

    def finish(self, job_id, number, *, result=None, error=None):
        if (result is None) == (error is None):
            raise ValueError("Provide either a result or an error")
        status = "succeeded" if error is None else "failed"
        with self._connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status=?, updated_at=? WHERE id=? AND attempt=? AND status='running'",
                (status, time.time(), job_id, number),
            ).rowcount
            if changed != 1:
                raise Conflict("Attempt is no longer running")
            db.execute(
                "UPDATE attempts SET status=?,finished_at=?,result=?,error=? WHERE job_id=? AND number=?",
                (
                    status,
                    time.time(),
                    json.dumps(result, allow_nan=False) if result is not None else None,
                    json.dumps(error) if error is not None else None,
                    job_id,
                    number,
                ),
            )

    def retry(self, job_id):
        with self._connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='queued', updated_at=? WHERE id=? AND status='failed'",
                (time.time(), job_id),
            ).rowcount
            if changed != 1:
                if (
                    db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone()
                    is None
                ):
                    raise KeyError(job_id)
                raise Conflict("Only failed jobs can be retried")
        return self.get(job_id)

    def recover_interrupted(self):
        """Call ONLY while holding the exclusive worker lock."""
        error = json.dumps(
            {
                "code": "worker_interrupted",
                "message": "Worker stopped before completion; retry this job.",
            }
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE attempts SET status='failed',finished_at=?,error=? WHERE status='running'",
                (time.time(), error),
            )
            return db.execute(
                "UPDATE jobs SET status='failed', updated_at=? WHERE status='running'",
                (time.time(),),
            ).rowcount

    def health(self):
        with self._connect() as db:
            db.execute("SELECT 1").fetchone()
        return "sqlite"
