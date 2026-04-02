"""
Dispatch Registry for JARVIS project builds.

Tracks all active and recent project dispatches in SQLite.
Maintains a history of build attempts with status, responses, and summaries.
Provides context injection for LLM about active/recent work.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.core.dispatch")

DB_PATH = settings.DATA_DIR / "jarvis_dispatch.db"


class DispatchRegistry:
    """Registry of project builds and dispatches."""

    def __init__(self):
        """Initialize the dispatch registry."""
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with dispatch table."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            cursor = conn.cursor()

            # Create dispatches table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                project_path TEXT,
                original_prompt TEXT,
                refined_prompt TEXT,
                status TEXT DEFAULT 'pending',
                claude_response TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
            """)

            # Create indexes for common queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_status ON dispatches(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_updated ON dispatches(updated_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_project ON dispatches(project_name)")

            conn.commit()
            conn.close()
            logger.info("Dispatch registry initialized at %s", DB_PATH)
        except Exception as e:
            logger.error("Failed to initialize dispatch registry: %s", e)
            raise

    def register(
        self,
        project_name: str,
        project_path: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> int:
        """
        Register a new dispatch.

        Args:
            project_name: Name of the project
            project_path: Optional path to the project
            prompt: Optional original prompt

        Returns:
            Dispatch ID
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
            INSERT INTO dispatches (project_name, project_path, original_prompt, status)
            VALUES (?, ?, ?, 'pending')
            """, (project_name, project_path, prompt))

            dispatch_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.info(
                "Dispatch registered: id=%d, project=%s, path=%s",
                dispatch_id, project_name, project_path
            )
            return dispatch_id
        except Exception as e:
            logger.error("Failed to register dispatch: %s", e)
            return -1

    def update_status(
        self,
        dispatch_id: int,
        status: str,
        response: Optional[str] = None,
        summary: Optional[str] = None
    ) -> bool:
        """
        Update dispatch status and optionally response/summary.

        Args:
            dispatch_id: ID of the dispatch
            status: New status (pending, building, planning, completed, failed)
            response: Optional Claude response
            summary: Optional summary of the dispatch

        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            completed_at = None
            if status in ("completed", "failed"):
                completed_at = datetime.utcnow().isoformat()

            cursor.execute("""
            UPDATE dispatches
            SET status = ?, claude_response = COALESCE(?, claude_response),
                summary = COALESCE(?, summary),
                updated_at = CURRENT_TIMESTAMP,
                completed_at = ?
            WHERE id = ?
            """, (status, response, summary, completed_at, dispatch_id))

            conn.commit()
            conn.close()

            logger.debug(
                "Dispatch status updated: id=%d, status=%s",
                dispatch_id, status
            )
            return True
        except Exception as e:
            logger.error("Failed to update dispatch status: %s", e)
            return False

    def get_most_recent(self) -> Optional[dict]:
        """
        Get the most recently updated dispatch.

        Returns:
            Dispatch record or None
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
            SELECT id, project_name, project_path, original_prompt,
                   refined_prompt, status, claude_response, summary,
                   created_at, updated_at, completed_at
            FROM dispatches
            ORDER BY updated_at DESC
            LIMIT 1
            """)

            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else None
        except Exception as e:
            logger.error("Failed to get most recent dispatch: %s", e)
            return None

    def get_active(self) -> list[dict]:
        """
        Get all active dispatches (pending, building, planning).

        Returns:
            List of active dispatch records
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
            SELECT id, project_name, project_path, original_prompt,
                   refined_prompt, status, summary,
                   created_at, updated_at
            FROM dispatches
            WHERE status IN ('pending', 'building', 'planning')
            ORDER BY updated_at DESC
            """)

            results = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return results
        except Exception as e:
            logger.error("Failed to get active dispatches: %s", e)
            return []

    def get_by_name(self, name: str) -> Optional[dict]:
        """
        Get a dispatch by project name (fuzzy match, returns most recent).

        Args:
            name: Project name to search for

        Returns:
            Dispatch record or None
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Try exact match first
            cursor.execute("""
            SELECT id, project_name, project_path, original_prompt,
                   refined_prompt, status, claude_response, summary,
                   created_at, updated_at, completed_at
            FROM dispatches
            WHERE project_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """, (name,))

            row = cursor.fetchone()

            # Fall back to fuzzy (substring) match
            if not row:
                cursor.execute("""
                SELECT id, project_name, project_path, original_prompt,
                       refined_prompt, status, claude_response, summary,
                       created_at, updated_at, completed_at
                FROM dispatches
                WHERE project_name LIKE ?
                ORDER BY updated_at DESC
                LIMIT 1
                """, (f"%{name}%",))

                row = cursor.fetchone()

            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error("Failed to get dispatch by name: %s", e)
            return None

    def get_recent(self, limit: int = 10) -> list[dict]:
        """
        Get recent dispatches.

        Args:
            limit: Maximum number of results

        Returns:
            List of recent dispatch records
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
            SELECT id, project_name, project_path, original_prompt,
                   refined_prompt, status, summary,
                   created_at, updated_at, completed_at
            FROM dispatches
            ORDER BY updated_at DESC
            LIMIT ?
            """, (limit,))

            results = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return results
        except Exception as e:
            logger.error("Failed to get recent dispatches: %s", e)
            return []

    def format_for_prompt(self) -> str:
        """
        Format active and recent dispatches for LLM context injection.

        Returns:
            Formatted string for system prompt injection
        """
        try:
            active = self.get_active()
            recent = self.get_recent(limit=3)

            parts = []

            if active:
                active_lines = []
                for dispatch in active:
                    line = f"- [{dispatch['status']}] {dispatch['project_name']}"
                    if dispatch['summary']:
                        line += f": {dispatch['summary']}"
                    active_lines.append(line)

                parts.append("Active dispatches:\n" + "\n".join(active_lines))

            if recent:
                recent_lines = []
                for dispatch in recent:
                    if dispatch not in active:  # Don't duplicate active ones
                        line = f"- {dispatch['project_name']} ({dispatch['status']})"
                        if dispatch['updated_at']:
                            line += f" - updated {dispatch['updated_at']}"
                        recent_lines.append(line)

                if recent_lines:
                    parts.append("Recent dispatches:\n" + "\n".join(recent_lines))

            if parts:
                return "\n\n".join(parts)
            return ""
        except Exception as e:
            logger.error("Failed to format dispatches for prompt: %s", e)
            return ""
