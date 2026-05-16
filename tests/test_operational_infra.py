"""Tests for migrations, jobs, tracing, and secret backends."""
import sqlite3

from jarvis.core import jobs
from jarvis.core.migrations import Migration, add_column_if_missing, ensure_migrations
from jarvis.core.secrets import get_secret
from jarvis.core.tracing import get_trace_id, reset_trace_id, set_trace_id


def test_migration_runner_applies_each_version_once():
    calls = []
    conn = sqlite3.connect(":memory:")

    def migration(conn_):
        calls.append("applied")
        conn_.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")

    ensure_migrations(conn, "test", [Migration(1, "baseline", migration)])
    ensure_migrations(conn, "test", [Migration(1, "baseline", migration)])

    assert calls == ["applied"]
    assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_add_column_if_missing_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")

    add_column_if_missing(conn, "example", "trace_id", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "example", "trace_id", "TEXT DEFAULT ''")

    columns = [row[1] for row in conn.execute("PRAGMA table_info(example)").fetchall()]
    assert columns.count("trace_id") == 1


def test_job_lifecycle_uses_configured_db(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "DB_PATH", tmp_path / "jobs.db")

    job = jobs.create_job("chat", {"message": "hello"}, trace_id="trace-1")
    assert job.status == jobs.JobStatus.QUEUED.value

    running = jobs.mark_running(job.id)
    assert running is not None
    assert running.status == jobs.JobStatus.RUNNING.value

    completed = jobs.mark_completed(job.id, "done")
    assert completed is not None
    assert completed.status == jobs.JobStatus.COMPLETED.value
    assert completed.result == "done"


def test_trace_context_round_trip():
    token = set_trace_id("trace-test")
    try:
        assert get_trace_id() == "trace-test"
    finally:
        reset_trace_id(token)


def test_get_secret_prefers_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-secret")
    assert get_secret("ANTHROPIC_API_KEY") == "env-secret"
