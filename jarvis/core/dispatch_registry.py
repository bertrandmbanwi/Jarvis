"""
Dispatch Registry for JARVIS project builds.

Tracks all active and recent project dispatches in SQLite.
Maintains a history of build attempts with status, responses, and summaries.
Provides context injection for LLM about active/recent work.

Includes SuccessTracker for monitoring task success rates, usage patterns,
and collecting suggestions for continuous improvement.
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

            # Create task_log table for success tracking
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                prompt TEXT,
                success BOOLEAN DEFAULT 1,
                retry_count INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Create usage_patterns table for action tracking
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                keyword TEXT,
                count INTEGER DEFAULT 1,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Create suggestions table for continuous improvement
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                suggestion TEXT NOT NULL,
                accepted BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Indexes for task_log
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_log_type ON task_log(task_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_log_success ON task_log(success)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_log_created ON task_log(created_at DESC)")

            # Indexes for usage_patterns
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_action ON usage_patterns(action_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_keyword ON usage_patterns(keyword)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_last_used ON usage_patterns(last_used DESC)")

            # Indexes for suggestions
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_task ON suggestions(task_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_accepted ON suggestions(accepted)")

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


class SuccessTracker:
    """Track task success rates, usage patterns, and improvement suggestions.

    Provides monitoring and analytics for JARVIS task execution to enable
    continuous improvement and intelligent suggestion generation.
    """

    def __init__(self):
        """Initialize the success tracker."""
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure tracking tables exist in the database."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                prompt TEXT,
                success BOOLEAN DEFAULT 1,
                retry_count INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                keyword TEXT,
                count INTEGER DEFAULT 1,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                suggestion TEXT NOT NULL,
                accepted BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_log_type ON task_log(task_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_action ON usage_patterns(action_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_task ON suggestions(task_id)")

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to ensure tracking tables: %s", e)

    def log_task(
        self,
        task_type: str,
        prompt: Optional[str] = None,
        success: bool = True,
        retry_count: int = 0,
        duration_seconds: float = 0.0,
    ) -> int:
        """Log a task execution.

        Args:
            task_type: Category of the task (e.g., "code_generation", "search")
            prompt: Optional original task prompt
            success: Whether the task completed successfully
            retry_count: Number of retries before success
            duration_seconds: How long the task took

        Returns:
            Task log ID
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
            INSERT INTO task_log (task_type, prompt, success, retry_count, duration_seconds)
            VALUES (?, ?, ?, ?, ?)
            """, (task_type, prompt, success, retry_count, duration_seconds))

            task_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.debug(
                "Task logged: id=%d, type=%s, success=%s, duration=%.2fs",
                task_id, task_type, success, duration_seconds,
            )
            return task_id
        except Exception as e:
            logger.error("Failed to log task: %s", e)
            return -1

    def log_usage(
        self,
        action_type: str,
        keyword: Optional[str] = None,
    ) -> bool:
        """Log usage pattern for an action.

        Increments count if pattern exists, creates new if not.

        Args:
            action_type: Type of action (e.g., "search", "file_read")
            keyword: Optional keyword for the action (e.g., search term)

        Returns:
            True if logged successfully
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            # Check if pattern exists
            cursor.execute("""
            SELECT id, count FROM usage_patterns
            WHERE action_type = ? AND keyword = ?
            """, (action_type, keyword))

            row = cursor.fetchone()

            if row:
                # Update existing pattern
                cursor.execute("""
                UPDATE usage_patterns
                SET count = count + 1, last_used = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (row[0],))
            else:
                # Create new pattern
                cursor.execute("""
                INSERT INTO usage_patterns (action_type, keyword, count)
                VALUES (?, ?, 1)
                """, (action_type, keyword))

            conn.commit()
            conn.close()

            logger.debug(
                "Usage pattern logged: action=%s, keyword=%s",
                action_type, keyword,
            )
            return True
        except Exception as e:
            logger.error("Failed to log usage pattern: %s", e)
            return False

    def log_suggestion(
        self,
        task_id: int,
        suggestion: str,
    ) -> int:
        """Log a suggestion for improvement.

        Args:
            task_id: ID of the task to suggest improvement for
            suggestion: The suggestion text

        Returns:
            Suggestion ID
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
            INSERT INTO suggestions (task_id, suggestion, accepted)
            VALUES (?, ?, 0)
            """, (task_id, suggestion))

            suggestion_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.debug(
                "Suggestion logged: id=%d, task_id=%d",
                suggestion_id, task_id,
            )
            return suggestion_id
        except Exception as e:
            logger.error("Failed to log suggestion: %s", e)
            return -1

    def mark_suggestion_accepted(self, suggestion_id: int) -> bool:
        """Mark a suggestion as accepted.

        Args:
            suggestion_id: ID of the suggestion

        Returns:
            True if updated successfully
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
            UPDATE suggestions SET accepted = 1 WHERE id = ?
            """, (suggestion_id,))

            conn.commit()
            conn.close()

            logger.debug("Suggestion marked as accepted: id=%d", suggestion_id)
            return True
        except Exception as e:
            logger.error("Failed to mark suggestion as accepted: %s", e)
            return False

    def get_success_rate(self, task_type: Optional[str] = None) -> float:
        """Get success rate for tasks.

        Args:
            task_type: Optional task type to filter by (all if None)

        Returns:
            Success rate as percentage (0-100)
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            if task_type:
                cursor.execute("""
                SELECT COUNT(*) as total, SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
                FROM task_log WHERE task_type = ?
                """, (task_type,))
            else:
                cursor.execute("""
                SELECT COUNT(*) as total, SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
                FROM task_log
                """)

            row = cursor.fetchone()
            conn.close()

            if not row or row[0] == 0:
                return 0.0

            total, successes = row
            successes = successes or 0
            return (successes / total) * 100
        except Exception as e:
            logger.error("Failed to get success rate: %s", e)
            return 0.0

    def get_top_actions(self, limit: int = 10) -> list[dict]:
        """Get most frequently used actions.

        Args:
            limit: Maximum number of results

        Returns:
            List of action records with count and last used timestamp
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
            SELECT action_type, keyword, count, last_used
            FROM usage_patterns
            ORDER BY count DESC, last_used DESC
            LIMIT ?
            """, (limit,))

            results = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return results
        except Exception as e:
            logger.error("Failed to get top actions: %s", e)
            return []

    def get_avg_duration(self, task_type: Optional[str] = None) -> float:
        """Get average task duration.

        Args:
            task_type: Optional task type to filter by (all if None)

        Returns:
            Average duration in seconds
        """
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            if task_type:
                cursor.execute("""
                SELECT AVG(duration_seconds) as avg_duration
                FROM task_log WHERE task_type = ?
                """, (task_type,))
            else:
                cursor.execute("""
                SELECT AVG(duration_seconds) as avg_duration
                FROM task_log
                """)

            row = cursor.fetchone()
            conn.close()

            if not row or row[0] is None:
                return 0.0

            return float(row[0])
        except Exception as e:
            logger.error("Failed to get average duration: %s", e)
            return 0.0
