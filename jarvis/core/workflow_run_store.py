"""Indexed SQLite storage for workflow run history."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from jarvis.core import sqlite_state


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            workflow_name TEXT NOT NULL DEFAULT '',
            workflow_version INTEGER NOT NULL DEFAULT 1,
            workflow_version_id TEXT NOT NULL DEFAULT '',
            release_channel TEXT NOT NULL DEFAULT '',
            release_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            triggered_by TEXT NOT NULL DEFAULT '',
            dry_run INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            started_at REAL NOT NULL DEFAULT 0,
            completed_at REAL NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            run_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_run_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL DEFAULT '',
            step_index INTEGER NOT NULL DEFAULT 0,
            type TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            started_at REAL NOT NULL DEFAULT 0,
            completed_at REAL NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            input_json TEXT NOT NULL DEFAULT '{}',
            output_json TEXT NOT NULL DEFAULT '{}',
            entry_json TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_run_attempts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            started_at REAL NOT NULL DEFAULT 0,
            completed_at REAL NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            attempt_json TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(step_id) REFERENCES workflow_run_steps(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_run_store_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_started ON workflow_runs(workflow_id, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_version_dry ON workflow_runs(workflow_id, workflow_version_id, dry_run, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_started ON workflow_runs(status, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_release_started ON workflow_runs(release_channel, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run ON workflow_run_steps(run_id, step_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_run_attempts_step ON workflow_run_attempts(step_id, attempt)")
    conn.commit()
    return conn


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _insert_run(conn: sqlite3.Connection, run: dict[str, Any]) -> None:
    run_id = str(run.get("id") or "")
    if not run_id:
        return
    conn.execute("DELETE FROM workflow_runs WHERE id = ?", (run_id,))
    conn.execute(
        """
        INSERT INTO workflow_runs (
            id, workflow_id, workflow_name, workflow_version, workflow_version_id,
            release_channel, release_id, status, triggered_by, dry_run, error,
            started_at, completed_at, duration_ms, run_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            str(run.get("workflow_id") or ""),
            str(run.get("workflow_name") or ""),
            _int_value(run.get("workflow_version"), 1),
            str(run.get("workflow_version_id") or ""),
            str(run.get("release_channel") or ""),
            str(run.get("release_id") or ""),
            str(run.get("status") or ""),
            str(run.get("triggered_by") or ""),
            _bool_int(run.get("dry_run")),
            str(run.get("error") or ""),
            _float_value(run.get("started_at")),
            _float_value(run.get("completed_at")),
            _float_value(run.get("duration_ms")),
            _json_dumps(run),
        ),
    )
    timeline_raw = run.get("timeline")
    timeline: list[Any] = timeline_raw if isinstance(timeline_raw, list) else []
    for index, entry in enumerate(timeline):
        if not isinstance(entry, dict):
            continue
        step_id = str(entry.get("id") or f"{run_id}:step:{index}")
        conn.execute(
            """
            INSERT INTO workflow_run_steps (
                id, run_id, action_id, step_index, type, title, status,
                started_at, completed_at, duration_ms, input_json, output_json, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                run_id,
                str(entry.get("action_id") or ""),
                index,
                str(entry.get("type") or ""),
                str(entry.get("title") or ""),
                str(entry.get("status") or ""),
                _float_value(entry.get("started_at")),
                _float_value(entry.get("completed_at")),
                _float_value(entry.get("duration_ms")),
                _json_dumps(entry.get("input") if isinstance(entry.get("input"), dict) else {}),
                _json_dumps(entry.get("output") if isinstance(entry.get("output"), dict) else {}),
                _json_dumps(entry),
            ),
        )
        attempts_raw = entry.get("attempts")
        attempts: list[Any] = attempts_raw if isinstance(attempts_raw, list) else []
        for attempt_index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                continue
            attempt_number = _int_value(attempt.get("attempt"), attempt_index + 1)
            conn.execute(
                """
                INSERT INTO workflow_run_attempts (
                    id, run_id, step_id, attempt, status, error,
                    started_at, completed_at, duration_ms, attempt_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{step_id}:attempt:{attempt_number}",
                    run_id,
                    step_id,
                    attempt_number,
                    str(attempt.get("status") or ""),
                    str(attempt.get("error") or ""),
                    _float_value(attempt.get("started_at")),
                    _float_value(attempt.get("completed_at")),
                    _float_value(attempt.get("duration_ms")),
                    _json_dumps(attempt),
                ),
            )


def _trim_runs(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(
        """
        SELECT id FROM workflow_runs
        ORDER BY started_at DESC
        LIMIT -1 OFFSET ?
        """,
        (max(1, limit),),
    ).fetchall()
    if not rows:
        return
    conn.executemany("DELETE FROM workflow_runs WHERE id = ?", [(str(row["id"]),) for row in rows])


def _ensure_imported(conn: sqlite3.Connection, db_path: Path, legacy_path: Path) -> None:
    marker = conn.execute(
        "SELECT value FROM workflow_run_store_meta WHERE key = 'legacy_imported'"
    ).fetchone()
    if marker is not None:
        return

    runs = sqlite_state.load_document(
        db_path=db_path,
        namespace="workflow_runs",
        legacy_path=legacy_path,
        default=[],
    )
    if isinstance(runs, list):
        for run in runs:
            if isinstance(run, dict):
                _insert_run(conn, run)
    conn.execute(
        """
        INSERT OR REPLACE INTO workflow_run_store_meta (key, value)
        VALUES ('legacy_imported', ?)
        """,
        (str(time.time()),),
    )
    conn.commit()


def save_run(*, db_path: Path, legacy_path: Path, run: dict[str, Any], limit: int = 500) -> dict[str, Any]:
    with _connect(db_path) as conn:
        _ensure_imported(conn, db_path, legacy_path)
        _insert_run(conn, run)
        _trim_runs(conn, limit)
        conn.commit()
    return run


def list_runs(
    *,
    db_path: Path,
    legacy_path: Path,
    workflow_id: str = "",
    status: str = "",
    dry_run: bool | None = None,
    release_channel: str = "",
    workflow_version_id: str = "",
    workflow_version: int | None = None,
    started_after: float | None = None,
    started_before: float | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    dry_run_filter = None if dry_run is None else _bool_int(dry_run)
    run_limit = max(1, min(limit, 500))
    with _connect(db_path) as conn:
        _ensure_imported(conn, db_path, legacy_path)
        rows = conn.execute(
            """
            SELECT run_json FROM workflow_runs
            WHERE (? = '' OR workflow_id = ?)
              AND (? = '' OR status = ?)
              AND (? IS NULL OR dry_run = ?)
              AND (? = '' OR release_channel = ?)
              AND (? = '' OR workflow_version_id = ?)
              AND (? IS NULL OR workflow_version = ?)
              AND (? IS NULL OR started_at >= ?)
              AND (? IS NULL OR started_at <= ?)
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (
                workflow_id,
                workflow_id,
                status,
                status,
                dry_run_filter,
                dry_run_filter,
                release_channel,
                release_channel,
                workflow_version_id,
                workflow_version_id,
                workflow_version,
                workflow_version,
                started_after,
                started_after,
                started_before,
                started_before,
                run_limit,
            ),
        ).fetchall()
    return [_json_loads(str(row["run_json"]), {}) for row in rows]


def get_run(*, db_path: Path, legacy_path: Path, run_id: str) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        _ensure_imported(conn, db_path, legacy_path)
        row = conn.execute("SELECT run_json FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    run = _json_loads(str(row["run_json"]), {})
    return run if isinstance(run, dict) else None


def storage_status(*, db_path: Path, legacy_path: Path) -> dict[str, int | bool]:
    with _connect(db_path) as conn:
        _ensure_imported(conn, db_path, legacy_path)
        run_count = int(conn.execute("SELECT COUNT(*) FROM workflow_runs").fetchone()[0])
        step_count = int(conn.execute("SELECT COUNT(*) FROM workflow_run_steps").fetchone()[0])
        attempt_count = int(conn.execute("SELECT COUNT(*) FROM workflow_run_attempts").fetchone()[0])
    return {
        "runs": run_count,
        "steps": step_count,
        "attempts": attempt_count,
        "indexed": True,
    }
