"""
SQLite + FTS5 memory layer for JARVIS.

Complements ChromaDB vector store with fast, structured lookup for:
- Memories (facts, preferences, context)
- Tasks (with priority, due dates, tags)
- Notes (freeform, searchable)

Uses FTS5 virtual tables for full-text search and WAL mode for concurrent reads.
All functions handle exceptions gracefully with logging.
"""
import asyncio
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.memory.sqlite")

DB_PATH = settings.DATA_DIR / "jarvis_memory.db"


def init_db() -> None:
    """Initialize SQLite database with tables and FTS5 virtual tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cursor = conn.cursor()

        # Create memories table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            mem_type TEXT NOT NULL,
            source TEXT,
            importance INTEGER DEFAULT 5,
            access_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create FTS5 virtual table for memories
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            mem_type,
            source,
            content='memories',
            content_rowid='id'
        )
        """)

        # Create tasks table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 3,
            due_date DATE,
            due_time TIME,
            project TEXT,
            status TEXT DEFAULT 'open',
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """)

        # Create FTS5 virtual table for tasks
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
            title,
            description,
            project,
            tags,
            content='tasks',
            content_rowid='id'
        )
        """)

        # Create notes table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            title TEXT,
            topic TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create FTS5 virtual table for notes
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            content,
            title,
            topic,
            tags,
            content='notes',
            content_rowid='id'
        )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(mem_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at DESC)")

        conn.commit()
        conn.close()
        logger.info("SQLite memory database initialized at %s", DB_PATH)
    except Exception as e:
        logger.error("Failed to initialize SQLite database: %s", e)
        raise


def remember(
    content: str,
    mem_type: str,
    source: Optional[str] = None,
    importance: int = 5
) -> int:
    """
    Store a memory in the database.

    Args:
        content: The memory content (fact, preference, context)
        mem_type: Type of memory (fact, preference, context, etc.)
        source: Where this memory came from (user, system, etc.)
        importance: Importance score (1-10)

    Returns:
        Memory ID
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO memories (content, mem_type, source, importance)
        VALUES (?, ?, ?, ?)
        """, (content, mem_type, source, importance))

        mem_id = cursor.lastrowid

        # Add to FTS5 index
        cursor.execute("""
        INSERT INTO memories_fts (rowid, content, mem_type, source)
        VALUES (?, ?, ?, ?)
        """, (mem_id, content, mem_type, source or ""))

        conn.commit()
        conn.close()
        logger.debug("Memory stored: id=%d, type=%s, importance=%d", mem_id, mem_type, importance)
        return mem_id
    except Exception as e:
        logger.error("Failed to remember: %s", e)
        return -1


def recall(query: str, limit: int = 10) -> list[dict]:
    """
    Search memories using FTS5.

    Args:
        query: Search query
        limit: Maximum results to return

    Returns:
        List of matching memories, ranked by relevance
    """
    try:
        query = _sanitize_fts_query(query)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT m.id, m.content, m.mem_type, m.source, m.importance,
               m.access_count, m.created_at, m.last_accessed,
               memories_fts.rank
        FROM memories m
        JOIN memories_fts ON m.id = memories_fts.rowid
        WHERE memories_fts MATCH ?
        ORDER BY memories_fts.rank DESC, m.importance DESC
        LIMIT ?
        """, (query, limit))

        results = []
        for row in cursor.fetchall():
            # Update access tracking
            cursor.execute("""
            UPDATE memories
            SET access_count = access_count + 1,
                last_accessed = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (row["id"],))

            results.append(dict(row))

        conn.commit()
        conn.close()
        logger.debug("Recalled %d memories for query: %s", len(results), query)
        return results
    except Exception as e:
        logger.error("Failed to recall memories: %s", e)
        return []


def get_recent_memories(limit: int = 20) -> list[dict]:
    """Get the most recently created memories."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, content, mem_type, source, importance, access_count,
               created_at, last_accessed
        FROM memories
        ORDER BY created_at DESC
        LIMIT ?
        """, (limit,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.error("Failed to get recent memories: %s", e)
        return []


def get_important_memories(limit: int = 10) -> list[dict]:
    """Get the most important memories."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, content, mem_type, source, importance, access_count,
               created_at, last_accessed
        FROM memories
        WHERE importance >= 7
        ORDER BY importance DESC, access_count DESC
        LIMIT ?
        """, (limit,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.error("Failed to get important memories: %s", e)
        return []


def create_task(
    title: str,
    description: Optional[str] = None,
    priority: int = 3,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    project: Optional[str] = None,
    tags: Optional[str] = None
) -> int:
    """
    Create a new task.

    Args:
        title: Task title
        description: Optional description
        priority: Priority (1-5, higher is more urgent)
        due_date: Optional due date (YYYY-MM-DD)
        due_time: Optional due time (HH:MM)
        project: Optional project name
        tags: Comma-separated tags

    Returns:
        Task ID
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO tasks (title, description, priority, due_date,
                          due_time, project, tags, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
        """, (title, description, priority, due_date, due_time, project, tags))

        task_id = cursor.lastrowid

        # Add to FTS5 index
        cursor.execute("""
        INSERT INTO tasks_fts (rowid, title, description, project, tags)
        VALUES (?, ?, ?, ?, ?)
        """, (task_id, title, description or "", project or "", tags or ""))

        conn.commit()
        conn.close()
        logger.debug("Task created: id=%d, title=%s, priority=%d", task_id, title, priority)
        return task_id
    except Exception as e:
        logger.error("Failed to create task: %s", e)
        return -1


def get_open_tasks(project: Optional[str] = None) -> list[dict]:
    """
    Get open tasks, optionally filtered by project.

    Args:
        project: Optional project name to filter by

    Returns:
        List of open tasks ordered by priority and due date
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if project:
            cursor.execute("""
            SELECT id, title, description, priority, due_date, due_time,
                   project, tags, created_at
            FROM tasks
            WHERE status = 'open' AND project = ?
            ORDER BY priority DESC, due_date ASC
            """, (project,))
        else:
            cursor.execute("""
            SELECT id, title, description, priority, due_date, due_time,
                   project, tags, created_at
            FROM tasks
            WHERE status = 'open'
            ORDER BY priority DESC, due_date ASC
            """)

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.error("Failed to get open tasks: %s", e)
        return []


def complete_task(task_id: int) -> bool:
    """Mark a task as completed."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
        UPDATE tasks
        SET status = 'completed', completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (task_id,))

        conn.commit()
        conn.close()
        logger.debug("Task completed: id=%d", task_id)
        return True
    except Exception as e:
        logger.error("Failed to complete task %d: %s", task_id, e)
        return False


def search_tasks(query: str, limit: int = 10) -> list[dict]:
    """
    Search tasks using FTS5.

    Args:
        query: Search query
        limit: Maximum results to return

    Returns:
        List of matching tasks
    """
    try:
        query = _sanitize_fts_query(query)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT t.id, t.title, t.description, t.priority, t.due_date,
               t.due_time, t.project, t.tags, t.status, t.created_at,
               tasks_fts.rank
        FROM tasks t
        JOIN tasks_fts ON t.id = tasks_fts.rowid
        WHERE tasks_fts MATCH ?
        ORDER BY tasks_fts.rank DESC, t.priority DESC
        LIMIT ?
        """, (query, limit))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.error("Failed to search tasks: %s", e)
        return []


def create_note(
    content: str,
    title: Optional[str] = None,
    topic: Optional[str] = None,
    tags: Optional[str] = None
) -> int:
    """
    Create a new note.

    Args:
        content: Note content
        title: Optional title
        topic: Optional topic category
        tags: Comma-separated tags

    Returns:
        Note ID
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO notes (content, title, topic, tags)
        VALUES (?, ?, ?, ?)
        """, (content, title, topic, tags))

        note_id = cursor.lastrowid

        # Add to FTS5 index
        cursor.execute("""
        INSERT INTO notes_fts (rowid, content, title, topic, tags)
        VALUES (?, ?, ?, ?, ?)
        """, (note_id, content, title or "", topic or "", tags or ""))

        conn.commit()
        conn.close()
        logger.debug("Note created: id=%d, title=%s", note_id, title)
        return note_id
    except Exception as e:
        logger.error("Failed to create note: %s", e)
        return -1


def search_notes(query: str, limit: int = 10) -> list[dict]:
    """
    Search notes using FTS5.

    Args:
        query: Search query
        limit: Maximum results to return

    Returns:
        List of matching notes
    """
    try:
        query = _sanitize_fts_query(query)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT n.id, n.content, n.title, n.topic, n.tags,
               n.created_at, n.updated_at, notes_fts.rank
        FROM notes n
        JOIN notes_fts ON n.id = notes_fts.rowid
        WHERE notes_fts MATCH ?
        ORDER BY notes_fts.rank DESC, n.created_at DESC
        LIMIT ?
        """, (query, limit))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.error("Failed to search notes: %s", e)
        return []


def build_memory_context(user_message: str) -> str:
    """
    Build a context string for LLM injection from relevant memories.

    Args:
        user_message: The user's message to base context on

    Returns:
        Formatted context string for system prompt injection
    """
    try:
        # Get relevant memories
        memories = recall(user_message, limit=5)
        important = get_important_memories(limit=3)

        parts = []

        if memories:
            memory_lines = []
            for mem in memories:
                line = f"- [{mem['mem_type']}] {mem['content']}"
                if mem['source']:
                    line += f" (from {mem['source']})"
                memory_lines.append(line)
            parts.append("Recent relevant memories:\n" + "\n".join(memory_lines))

        if important:
            important_lines = [f"- {mem['content']}" for mem in important]
            parts.append("Important memories:\n" + "\n".join(important_lines))

        if parts:
            return "\n\n".join(parts)
        return ""
    except Exception as e:
        logger.error("Failed to build memory context: %s", e)
        return ""


async def extract_memories(
    user_text: str,
    jarvis_response: str,
    anthropic_client
) -> list[str]:
    """
    Use Claude Haiku to extract facts from an exchange.

    Args:
        user_text: User's message
        jarvis_response: JARVIS's response
        anthropic_client: Anthropic API client

    Returns:
        List of extracted fact strings
    """
    try:
        prompt = f"""Extract 1-3 key facts or preferences from this conversation exchange.
Focus on: user preferences, habits, facts about the user, important dates, project names, etc.
Return only the facts as a JSON array of strings. If no facts, return [].

User: {user_text}

JARVIS: {jarvis_response}

Return only valid JSON array."""

        message = await asyncio.to_thread(
            anthropic_client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text
        # Parse JSON from response
        import json
        try:
            facts = json.loads(response_text)
            if isinstance(facts, list):
                # Store each fact
                for fact in facts:
                    if isinstance(fact, str):
                        remember(fact, "extracted", "haiku_extraction", importance=6)
                logger.debug("Extracted %d facts from exchange", len(facts))
                return facts
        except json.JSONDecodeError:
            logger.debug("Could not parse facts JSON from Haiku response")
            return []
    except Exception as e:
        logger.error("Failed to extract memories: %s", e)
        return []


def _sanitize_fts_query(query: str) -> str:
    """
    Clean a query string for FTS5.

    Removes special characters and quotes for safe FTS5 matching.

    Args:
        query: Raw query string

    Returns:
        Sanitized query
    """
    # Remove dangerous FTS5 operators and special characters
    # Keep alphanumeric, spaces, and basic punctuation
    sanitized = ""
    for char in query:
        if char.isalnum() or char in " -_":
            sanitized += char

    # Remove multiple spaces
    sanitized = " ".join(sanitized.split())

    return sanitized if sanitized else "*"


# Initialize database at module load time
try:
    init_db()
except Exception as e:
    logger.warning("Database initialization deferred: %s", e)
