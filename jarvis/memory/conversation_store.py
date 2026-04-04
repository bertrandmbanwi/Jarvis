"""
SQLite-backed conversation history for JARVIS.

Replaces the previous JSON file approach with a proper database that supports:
- WAL mode for concurrent reads during active conversation
- Indexed lookups by timestamp for efficient history slicing
- Automatic pruning of old turns beyond the retention limit
- Atomic writes (no partial JSON corruption on crash)

The conversation_history.json file is automatically migrated on first use.
"""
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.memory.conversation")

DB_PATH = settings.DATA_DIR / "jarvis_conversation.db"
LEGACY_JSON_PATH = settings.DATA_DIR / "conversation_history.json"

# Maximum number of turns to retain in the database. Older turns are pruned
# on each save to keep the table bounded. This is deliberately higher than
# the context window limit (20 turns) so that full history is available for
# memory searches and analytics.
MAX_RETAINED_TURNS = 500


@dataclass
class ConversationTurn:
    """Single conversation turn with metadata."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    tier_used: str = ""
    tool_calls: list = field(default_factory=list)
    request_id: str = ""


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_conversation_db() -> None:
    """Initialize the conversation history table."""
    try:
        conn = _get_conn()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp REAL NOT NULL,
            tier_used TEXT DEFAULT '',
            request_id TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_turns_timestamp
        ON conversation_turns(timestamp)
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_turns_request_id
        ON conversation_turns(request_id)
        """)
        conn.commit()
        conn.close()
        logger.info("Conversation database initialized at %s", DB_PATH)
    except Exception as e:
        logger.error("Failed to initialize conversation database: %s", e)


def _migrate_from_json() -> int:
    """Migrate legacy JSON conversation history to SQLite.

    Returns the number of turns migrated. Renames the old file to
    .json.migrated so it is not re-processed.
    """
    if not LEGACY_JSON_PATH.exists():
        return 0

    try:
        data = json.loads(LEGACY_JSON_PATH.read_text(encoding="utf-8"))
        if not data:
            return 0

        conn = _get_conn()
        migrated = 0
        for entry in data:
            conn.execute(
                "INSERT INTO conversation_turns (role, content, timestamp, tier_used) "
                "VALUES (?, ?, ?, ?)",
                (
                    entry.get("role", "user"),
                    entry.get("content", ""),
                    entry.get("timestamp", 0.0),
                    entry.get("tier_used", ""),
                ),
            )
            migrated += 1
        conn.commit()
        conn.close()

        # Rename the old file so we do not re-migrate
        backup_path = LEGACY_JSON_PATH.with_suffix(".json.migrated")
        LEGACY_JSON_PATH.rename(backup_path)
        logger.info(
            "Migrated %d conversation turns from JSON to SQLite. "
            "Old file renamed to %s",
            migrated, backup_path,
        )
        return migrated
    except Exception as e:
        logger.warning("JSON migration failed (non-critical): %s", e)
        return 0


def load_conversation(limit: int = 100) -> list[ConversationTurn]:
    """Load the most recent conversation turns from SQLite.

    Args:
        limit: Maximum number of turns to load.

    Returns:
        List of ConversationTurn objects ordered oldest-first.
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT role, content, timestamp, tier_used, request_id "
            "FROM conversation_turns ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()

        turns = []
        for row in reversed(rows):  # Reverse so oldest is first
            turns.append(ConversationTurn(
                role=row["role"],
                content=row["content"],
                timestamp=row["timestamp"],
                tier_used=row["tier_used"] or "",
                request_id=row["request_id"] or "",
            ))
        return turns
    except Exception as e:
        logger.error("Failed to load conversation: %s", e)
        return []


def save_turn(turn: ConversationTurn) -> None:
    """Persist a single conversation turn to SQLite."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO conversation_turns (role, content, timestamp, tier_used, request_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (turn.role, turn.content, turn.timestamp, turn.tier_used, turn.request_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to save conversation turn: %s", e)


def save_turns_batch(turns: list[ConversationTurn]) -> None:
    """Persist multiple conversation turns in a single transaction."""
    if not turns:
        return
    try:
        conn = _get_conn()
        conn.executemany(
            "INSERT INTO conversation_turns (role, content, timestamp, tier_used, request_id) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (t.role, t.content, t.timestamp, t.tier_used, t.request_id)
                for t in turns
            ],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Failed to batch save conversation turns: %s", e)


def prune_old_turns(keep: int = MAX_RETAINED_TURNS) -> int:
    """Delete conversation turns beyond the retention limit.

    Returns the number of turns deleted.
    """
    try:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0]
        if total <= keep:
            conn.close()
            return 0

        to_delete = total - keep
        conn.execute(
            "DELETE FROM conversation_turns WHERE id IN "
            "(SELECT id FROM conversation_turns ORDER BY timestamp ASC LIMIT ?)",
            (to_delete,),
        )
        conn.commit()
        conn.close()
        logger.info("Pruned %d old conversation turns (kept %d).", to_delete, keep)
        return to_delete
    except Exception as e:
        logger.warning("Conversation pruning failed: %s", e)
        return 0


def clear_conversation() -> None:
    """Delete all conversation turns."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM conversation_turns")
        conn.commit()
        conn.close()
        logger.info("Conversation history cleared.")
    except Exception as e:
        logger.error("Failed to clear conversation: %s", e)


def get_turn_count() -> int:
    """Get the total number of stored conversation turns."""
    try:
        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def initialize() -> None:
    """Initialize the conversation store: create tables, migrate legacy data."""
    init_conversation_db()
    migrated = _migrate_from_json()
    if migrated > 0:
        prune_old_turns()
