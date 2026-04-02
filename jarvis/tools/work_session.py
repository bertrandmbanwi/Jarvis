"""Persistent Claude Code work sessions tied to project directories.

Manages long-running claude -p sessions with context persistence across
JARVIS restarts. Sessions are tied to working directories and automatically
resume previous context using the --continue flag.
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.work_session")

SESSION_STATE_DIR = settings.DATA_DIR / "sessions"
SESSION_STATE_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_SESSION_FILE = SESSION_STATE_DIR / "active_session.json"

WORK_SESSION_TIMEOUT = 300


def _find_claude_binary() -> Optional[str]:
    """Locate the claude CLI binary on the system."""
    candidates = [
        shutil.which("claude"),
        str(Path.home() / ".claude" / "bin" / "claude"),
        str(Path.home() / ".local" / "bin" / "claude"),
        "/usr/local/bin/claude",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def is_casual_question(text: str) -> bool:
    """Detect if user input is casual chat vs work-related.

    Casual patterns go to Haiku for speed.
    Work-related requests use persistent Claude Code session.

    Args:
        text: User input text

    Returns:
        True if casual, False if work-related
    """
    if not text:
        return True

    text_lower = text.lower().strip()

    casual_patterns = [
        # Greetings
        r"^(hey|hello|hi|howdy|greetings)",
        r"(good morning|good afternoon|good evening|good night)$",
        # Time/weather/status checks
        r"^(what time|what's the time|current time)",
        r"^(weather|forecast)",
        r"^(how are you|what's up|what'?s new|how'?re you)",
        r"^(thanks|thank you|appreciate|thx|ty)$",
        r"^(ok|okay|got it|understood|sure|yep|nope|no)$",
        # Acknowledgments
        r"(sounds good|makes sense|perfect|makes sense|looks good)",
        # Small talk
        r"^(tell me a joke|funny|laugh)",
        r"^(hello there)",
    ]

    import re
    for pattern in casual_patterns:
        if re.search(pattern, text_lower):
            return True

    return False


class WorkSession:
    """Persistent claude -p session tied to a project directory.

    Manages the lifecycle of a long-running Claude Code session:
    - First message: fresh claude -p
    - Subsequent messages: claude -p --continue (resumes context)
    - Sessions persist across JARVIS restarts via disk state
    - Automatic session cleanup and restoration

    Attributes:
        working_dir: Directory where session runs
        project_name: Identifier for the project
        session_id: Unique session identifier
    """

    def __init__(self, working_dir: str, project_name: str):
        """Initialize a work session.

        Args:
            working_dir: Directory to execute commands in
            project_name: Project identifier for tracking
        """
        self.working_dir = str(Path(working_dir).expanduser().resolve())
        self.project_name = project_name
        self.session_id = f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._is_initialized = False
        self._process: Optional[subprocess.Popen] = None

        if not Path(self.working_dir).is_dir():
            raise ValueError(f"Working directory does not exist: {self.working_dir}")

        logger.info(
            "WorkSession initialized: session_id=%s, project=%s, dir=%s",
            self.session_id, project_name, self.working_dir,
        )

    async def start(self) -> bool:
        """Start a new work session.

        Creates fresh claude -p session. If a previous session exists
        for this working directory, it will be noted but a new session
        is started.

        Returns:
            True if session started successfully, False otherwise
        """
        claude_bin = _find_claude_binary()
        if not claude_bin:
            logger.error("Claude Code CLI not found")
            return False

        self._save_session()
        self._is_initialized = True
        logger.info("WorkSession started: %s", self.session_id)
        return True

    async def send(self, user_text: str) -> str:
        """Send a message to the work session.

        First call to send() starts fresh session. Subsequent calls
        resume previous context using --continue flag.

        Args:
            user_text: User's message/task

        Returns:
            Claude Code response as string
        """
        claude_bin = _find_claude_binary()
        if not claude_bin:
            return (
                "Error: Claude Code CLI not found. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            )

        if not Path(self.working_dir).is_dir():
            return f"Error: working directory does not exist: {self.working_dir}"

        cmd = [
            claude_bin,
            "--print",
            "--output-format", "text",
        ]

        if self._is_initialized:
            cmd.append("--continue")

        cmd.extend(["--prompt", user_text])

        logger.info(
            "WorkSession.send(): session_id=%s, continue=%s",
            self.session_id, self._is_initialized,
        )
        logger.debug("Claude Code command: %s", " ".join(cmd[:5]) + " ...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=WORK_SESSION_TIMEOUT,
            )

            output = stdout.decode("utf-8", errors="replace").strip()
            errors = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode != 0:
                error_detail = errors[:500] if errors else "Unknown error"
                logger.error(
                    "WorkSession.send() failed: exit_code=%d, session_id=%s",
                    process.returncode, self.session_id,
                )
                return f"Claude Code task failed (exit code {process.returncode}):\n{error_detail}"

            if not output:
                output = "(Claude Code completed the task but produced no text output.)"

            if len(output) > 8000:
                output = output[:7500] + f"\n\n... [output truncated, total length: {len(output)} chars]"

            self._is_initialized = True
            self._save_session()
            logger.info(
                "WorkSession.send() completed: session_id=%s, output_len=%d",
                self.session_id, len(output),
            )
            return output

        except asyncio.TimeoutError:
            logger.error(
                "WorkSession.send() timed out after %ds: session_id=%s",
                WORK_SESSION_TIMEOUT, self.session_id,
            )
            try:
                if process:
                    process.kill()
            except Exception:
                pass
            return f"Error: Claude Code task timed out after {WORK_SESSION_TIMEOUT} seconds."
        except FileNotFoundError:
            return "Error: Claude Code binary not found or not executable."
        except Exception as e:
            logger.error("WorkSession.send() unexpected error: %s", e)
            return f"Error running Claude Code: {str(e)[:300]}"

    def stop(self) -> None:
        """Stop the work session and clear state.

        Marks session as complete and removes disk persistence.
        """
        self._clear_session()
        self._is_initialized = False
        logger.info("WorkSession stopped: %s", self.session_id)

    @staticmethod
    def restore() -> Optional["WorkSession"]:
        """Restore a previous work session from disk state.

        Attempts to load the most recent active session from
        active_session.json. Returns None if no previous session found
        or state file corrupted.

        Returns:
            WorkSession instance if restored, None otherwise
        """
        if not ACTIVE_SESSION_FILE.exists():
            logger.debug("No previous work session found")
            return None

        try:
            with open(ACTIVE_SESSION_FILE, "r") as f:
                data = json.load(f)

            session = WorkSession(
                working_dir=data["working_dir"],
                project_name=data["project_name"],
            )
            session.session_id = data["session_id"]
            session._is_initialized = data.get("_is_initialized", True)

            logger.info("WorkSession restored from disk: %s", session.session_id)
            return session
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to restore work session: %s", e)
            return None
        except Exception as e:
            logger.error("Unexpected error restoring work session: %s", e)
            return None

    def _save_session(self) -> None:
        """Persist session state to disk.

        Writes current session metadata to active_session.json so it
        can be resumed after JARVIS restart.
        """
        try:
            data = {
                "session_id": self.session_id,
                "working_dir": self.working_dir,
                "project_name": self.project_name,
                "_is_initialized": self._is_initialized,
                "created_at": datetime.utcnow().isoformat(),
            }
            with open(ACTIVE_SESSION_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug("WorkSession state saved: %s", self.session_id)
        except Exception as e:
            logger.error("Failed to save work session state: %s", e)

    def _clear_session(self) -> None:
        """Clear session state from disk.

        Removes the active_session.json file to mark session as complete.
        """
        try:
            if ACTIVE_SESSION_FILE.exists():
                ACTIVE_SESSION_FILE.unlink()
            logger.debug("WorkSession state cleared: %s", self.session_id)
        except Exception as e:
            logger.error("Failed to clear work session state: %s", e)
