"""Workflow persistence: SQLite-backed load/save for each workflow document.

Extracted from workflows.py. Owns the file-path constants (patched by tests to
redirect state to a temp dir) and the load/save helpers built on sqlite_state.
"""
from __future__ import annotations

from typing import Any

from jarvis.config import settings
from jarvis.core import sqlite_state, workflow_run_store

WORKFLOWS_FILE = settings.DATA_DIR / "workflows.json"
WORKFLOW_RUNS_FILE = settings.DATA_DIR / "workflow_runs.json"
WORKFLOW_APPROVALS_FILE = settings.DATA_DIR / "workflow_approvals.json"
WORKFLOW_VERSIONS_FILE = settings.DATA_DIR / "workflow_versions.json"
WORKFLOW_RELEASES_FILE = settings.DATA_DIR / "workflow_releases.json"
WORKFLOW_EDIT_SESSIONS_FILE = settings.DATA_DIR / "workflow_edit_sessions.json"


def _state_db_path():
    return sqlite_state.db_path_for(WORKFLOWS_FILE)


def _load_list(namespace: str, legacy_path, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = sqlite_state.load_document(
        db_path=_state_db_path(),
        namespace=namespace,
        legacy_path=legacy_path,
        default=default,
    )
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return default


def _save_list(namespace: str, data: list[dict[str, Any]]) -> None:
    sqlite_state.save_document(
        db_path=_state_db_path(),
        namespace=namespace,
        data=data,
    )


def _load_workflows() -> list[dict[str, Any]]:
    return _load_list("workflows", WORKFLOWS_FILE, [])


def _save_workflows(items: list[dict[str, Any]]) -> None:
    _save_list("workflows", items)


def _load_runs() -> list[dict[str, Any]]:
    return workflow_run_store.list_runs(
        db_path=_state_db_path(),
        legacy_path=WORKFLOW_RUNS_FILE,
        limit=500,
    )


def _save_runs(items: list[dict[str, Any]]) -> None:
    for item in items[-500:]:
        workflow_run_store.save_run(
            db_path=_state_db_path(),
            legacy_path=WORKFLOW_RUNS_FILE,
            run=item,
            limit=500,
        )


def _load_approvals() -> list[dict[str, Any]]:
    return _load_list("workflow_approvals", WORKFLOW_APPROVALS_FILE, [])


def _save_approvals(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_approvals", items[-500:])


def _load_versions() -> list[dict[str, Any]]:
    return _load_list("workflow_versions", WORKFLOW_VERSIONS_FILE, [])


def _save_versions(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_versions", items[-1000:])


def _load_releases() -> list[dict[str, Any]]:
    return _load_list("workflow_releases", WORKFLOW_RELEASES_FILE, [])


def _save_releases(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_releases", items[-1000:])


def _load_edit_sessions() -> list[dict[str, Any]]:
    return _load_list("workflow_edit_sessions", WORKFLOW_EDIT_SESSIONS_FILE, [])


def _save_edit_sessions(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_edit_sessions", items[-500:])
