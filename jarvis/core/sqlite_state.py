"""SQLite-backed JSON document storage for product state.

This intentionally stores small product-state documents as JSON blobs in
SQLite. It gives us atomic writes, one durable database file, and a simple
compatibility importer from the previous JSON files without forcing a broad
schema migration before the product shape settles.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def db_path_for(legacy_path: Path) -> Path:
    """Return the product-state database next to a legacy JSON file."""
    return legacy_path.parent / "jarvis_product_state.sqlite3"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS state_documents (
            namespace TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            updated_at REAL NOT NULL,
            migrated_from TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS state_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO state_meta (key, value)
        VALUES ('schema_version', ?)
        """,
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn


def _load_legacy_json(legacy_path: Path, default: Any) -> tuple[Any, str]:
    if not legacy_path.exists():
        return default, ""
    try:
        data = json.loads(legacy_path.read_text(encoding="utf-8"))
        return data, str(legacy_path)
    except (OSError, json.JSONDecodeError):
        return default, str(legacy_path)


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def load_document(*, db_path: Path, namespace: str, legacy_path: Path, default: Any) -> Any:
    """Load a namespaced document, importing legacy JSON on first access."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT data FROM state_documents WHERE namespace = ?",
            (namespace,),
        ).fetchone()
        if row is not None:
            try:
                return json.loads(str(row["data"]))
            except json.JSONDecodeError:
                return _json_clone(default)

        data, migrated_from = _load_legacy_json(legacy_path, default)
        conn.execute(
            """
            INSERT OR REPLACE INTO state_documents (namespace, data, updated_at, migrated_from)
            VALUES (?, ?, ?, ?)
            """,
            (namespace, json.dumps(data, sort_keys=True), time.time(), migrated_from),
        )
        conn.commit()
        return _json_clone(data)


def save_document(*, db_path: Path, namespace: str, data: Any, migrated_from: str = "") -> None:
    """Save a namespaced document in SQLite."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO state_documents (namespace, data, updated_at, migrated_from)
            VALUES (?, ?, ?, COALESCE(NULLIF(?, ''), (
                SELECT migrated_from FROM state_documents WHERE namespace = ?
            ), ''))
            """,
            (namespace, json.dumps(data, sort_keys=True), time.time(), migrated_from, namespace),
        )
        conn.commit()


def migration_status(db_path: Path) -> dict[str, dict[str, Any]]:
    """Return document migration metadata for tests and diagnostics."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT namespace, updated_at, migrated_from FROM state_documents ORDER BY namespace"
        ).fetchall()
    return {
        str(row["namespace"]): {
            "updated_at": float(row["updated_at"]),
            "migrated_from": str(row["migrated_from"] or ""),
        }
        for row in rows
    }
