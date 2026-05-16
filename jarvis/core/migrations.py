"""Small SQLite migration runner shared by local stores."""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass

logger = logging.getLogger("jarvis.migrations")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def ensure_migrations(
    conn: sqlite3.Connection,
    namespace: str,
    migrations: Iterable[Migration],
) -> None:
    """Apply missing migrations for one database namespace."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        namespace TEXT NOT NULL,
        version INTEGER NOT NULL,
        name TEXT NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (namespace, version)
    )
    """)
    applied = {
        int(row[0])
        for row in conn.execute(
            "SELECT version FROM schema_migrations WHERE namespace = ?",
            (namespace,),
        ).fetchall()
    }
    for migration in sorted(migrations, key=lambda m: m.version):
        if migration.version in applied:
            continue
        logger.info("Applying SQLite migration %s:%s %s", namespace, migration.version, migration.name)
        migration.apply(conn)
        conn.execute(
            "INSERT INTO schema_migrations (namespace, version, name) VALUES (?, ?, ?)",
            (namespace, migration.version, migration.name),
        )


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return whether a table has a column."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Add a column if absent. Definition should start after the column name."""
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
