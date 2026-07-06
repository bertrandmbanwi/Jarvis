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

from jarvis.config import settings
from jarvis.core.migrations import Migration, add_column_if_missing, ensure_migrations

logger = logging.getLogger("jarvis.core.dispatch")

DB_PATH = settings.DATA_DIR / "jarvis_dispatch.db"


def _add_dispatch_trace_columns(conn: sqlite3.Connection) -> None:
    add_column_if_missing(conn, "dispatches", "trace_id", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "task_log", "trace_id", "TEXT DEFAULT ''")


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

            ensure_migrations(
                conn,
                "dispatch",
                [
                    Migration(1, "baseline_dispatch_schema", lambda _conn: None),
                    Migration(2, "dispatch_trace_columns", _add_dispatch_trace_columns),
                ],
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_trace ON dispatches(trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_log_trace ON task_log(trace_id)")

            conn.commit()
            conn.close()
            logger.info("Dispatch registry initialized at %s", DB_PATH)
        except Exception as e:
            logger.error("Failed to initialize dispatch registry: %s", e)
            raise

    def register(
        self,
        project_name: str,
        project_path: str | None = None,
        prompt: str | None = None
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

            dispatch_id = int(cursor.lastrowid or -1)
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
        response: str | None = None,
        summary: str | None = None
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
        prompt: str | None = None,
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

            task_id = int(cursor.lastrowid or -1)
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


