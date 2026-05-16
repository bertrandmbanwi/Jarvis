"""Durable background job storage for long-running JARVIS work."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from jarvis.config import settings
from jarvis.core.migrations import Migration, add_column_if_missing, ensure_migrations
from jarvis.core.tracing import get_trace_id

logger = logging.getLogger("jarvis.jobs")

DB_PATH = settings.DATA_DIR / "jarvis_jobs.db"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class JobRecord:
    id: str
    kind: str
    status: str
    payload: dict[str, Any]
    result: str
    error: str
    trace_id: str
    created_at: float
    updated_at: float
    started_at: float | None = None
    completed_at: float | None = None


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _baseline_migration(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS background_jobs (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        result TEXT DEFAULT '',
        error TEXT DEFAULT '',
        trace_id TEXT DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        started_at REAL,
        completed_at REAL
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON background_jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON background_jobs(created_at DESC)")


def _metadata_migration(conn: sqlite3.Connection) -> None:
    add_column_if_missing(conn, "background_jobs", "metadata_json", "TEXT DEFAULT '{}'")


def init_jobs_db() -> None:
    """Initialize job tables and apply migrations."""
    with _connect() as conn:
        ensure_migrations(
            conn,
            "jobs",
            [
                Migration(1, "baseline_jobs", _baseline_migration),
                Migration(2, "job_metadata", _metadata_migration),
            ],
        )


def _row_to_job(row: sqlite3.Row) -> JobRecord:
    payload_raw = row["payload_json"] or "{}"
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        payload = {}
    return JobRecord(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        payload=payload,
        result=row["result"] or "",
        error=row["error"] or "",
        trace_id=row["trace_id"] or "",
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def create_job(kind: str, payload: dict[str, Any], trace_id: str | None = None) -> JobRecord:
    """Create a queued background job."""
    init_jobs_db()
    now = time.time()
    job_id = uuid.uuid4().hex
    active_trace_id = trace_id or get_trace_id()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO background_jobs (
                id, kind, status, payload_json, trace_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                kind,
                JobStatus.QUEUED.value,
                json.dumps(payload, sort_keys=True, default=str),
                active_trace_id,
                now,
                now,
            ),
        )
    job = get_job(job_id)
    if job is None:
        raise RuntimeError("Created job could not be loaded.")
    return job


def get_job(job_id: str) -> JobRecord | None:
    init_jobs_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM background_jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def list_jobs(limit: int = 50, status: str = "") -> list[JobRecord]:
    init_jobs_db()
    bounded_limit = max(1, min(limit, 200))
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM background_jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, bounded_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM background_jobs ORDER BY created_at DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
    return [_row_to_job(row) for row in rows]


def update_job_status(
    job_id: str,
    status: JobStatus,
    *,
    result: str = "",
    error: str = "",
) -> JobRecord | None:
    """Update job state and timestamps."""
    now = time.time()
    current = get_job(job_id)
    if current is None:
        return None

    started_at = current.started_at
    completed_at = current.completed_at
    if status == JobStatus.RUNNING and started_at is None:
        started_at = now
    if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        completed_at = now

    with _connect() as conn:
        conn.execute(
            """
            UPDATE background_jobs
            SET status = ?, result = COALESCE(NULLIF(?, ''), result),
                error = COALESCE(NULLIF(?, ''), error), updated_at = ?,
                started_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (status.value, result, error, now, started_at, completed_at, job_id),
        )
    return get_job(job_id)


def mark_running(job_id: str) -> JobRecord | None:
    return update_job_status(job_id, JobStatus.RUNNING)


def mark_completed(job_id: str, result: str) -> JobRecord | None:
    return update_job_status(job_id, JobStatus.COMPLETED, result=result)


def mark_failed(job_id: str, error: str) -> JobRecord | None:
    return update_job_status(job_id, JobStatus.FAILED, error=error)


def cancel_job(job_id: str) -> JobRecord | None:
    current = get_job(job_id)
    if current is None or current.status in {
        JobStatus.COMPLETED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    }:
        return current
    return update_job_status(job_id, JobStatus.CANCELLED)
