"""JARVIS Claude Code integration: spawns Claude Code CLI for coding, shell, scaffolding, git."""
import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tools.claude_code")

CLAUDE_CODE_TIMEOUT = 300
DEFAULT_WORKING_DIR = Path.home()
# Session file for persistent Claude Code context across interactions
_SESSION_DIR = Path.home() / ".jarvis" / "claude-sessions"
_SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _find_claude_binary() -> Optional[str]:
    """Locate the claude CLI binary on the system."""
    # Check common install locations
    candidates = [
        shutil.which("claude"),  # On PATH
        str(Path.home() / ".claude" / "bin" / "claude"),
        str(Path.home() / ".local" / "bin" / "claude"),
        "/usr/local/bin/claude",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


async def run_claude_code(
    task: str,
    working_directory: str = "",
    allowed_tools: str = "",
    continue_session: bool = False,
    session_name: str = "",
) -> str:
    """Run a coding task using Claude Code CLI.

    Args:
        task: The coding task to perform.
        working_directory: Directory to work in.
        allowed_tools: Comma-separated tools to allow (e.g. "Bash,Read,Write,Edit").
        continue_session: If True, continues the previous session in this working directory.
        session_name: Optional named session for persistent context across calls.
    """
    claude_bin = _find_claude_binary()
    if not claude_bin:
        return (
            "Error: Claude Code CLI not found. "
            "Install it with: npm install -g @anthropic-ai/claude-code "
            "or visit https://docs.anthropic.com/en/docs/claude-code"
        )

    cwd = working_directory.strip() if working_directory else str(DEFAULT_WORKING_DIR)
    cwd = str(Path(cwd).expanduser().resolve())
    if not Path(cwd).is_dir():
        return f"Error: working directory does not exist: {cwd}"

    cmd = [
        claude_bin,
        "--print",
        "--output-format", "text",
        "--dangerously-skip-permissions",
    ]

    # Session persistence: continue previous context
    if continue_session:
        cmd.append("--continue")
    elif session_name.strip():
        cmd.extend(["--resume", session_name.strip()])

    if allowed_tools.strip():
        for tool in allowed_tools.split(","):
            tool = tool.strip()
            if tool:
                cmd.extend(["--allowedTools", tool])

    cmd.extend(["--prompt", task])

    logger.info(
        "Claude Code: running task in %s (timeout: %ds)",
        cwd, CLAUDE_CODE_TIMEOUT,
    )
    logger.debug("Claude Code command: %s", " ".join(cmd[:6]) + " ...")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CLAUDE_CODE_HEADLESS": "1"},
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=CLAUDE_CODE_TIMEOUT,
        )

        output = stdout.decode("utf-8", errors="replace").strip()
        errors = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            error_detail = errors[:500] if errors else "Unknown error"
            logger.error("Claude Code exited with code %d: %s", process.returncode, error_detail)
            return f"Claude Code task failed (exit code {process.returncode}):\n{error_detail}"

        if not output:
            output = "(Claude Code completed the task but produced no text output.)"

        if len(output) > 8000:
            output = output[:7500] + "\n\n... [output truncated, total length: {} chars]".format(len(output))

        logger.info("Claude Code: task completed (%d chars output)", len(output))
        return output

    except asyncio.TimeoutError:
        logger.error("Claude Code: task timed out after %ds", CLAUDE_CODE_TIMEOUT)
        try:
            process.kill()
        except Exception:
            pass
        return f"Error: Claude Code task timed out after {CLAUDE_CODE_TIMEOUT} seconds."
    except FileNotFoundError:
        return "Error: Claude Code binary not found or not executable."
    except Exception as e:
        logger.error("Claude Code: unexpected error: %s", e)
        return f"Error running Claude Code: {str(e)[:300]}"


async def run_terminal_command(
    command: str,
    working_directory: str = "",
) -> str:
    """Run a terminal command via Claude Code with safety awareness."""
    task = (
        f"Run the following terminal command and show me the output. "
        f"If the command seems destructive or risky, warn before executing.\n\n"
        f"Command: {command}"
    )

    return await run_claude_code(
        task=task,
        working_directory=working_directory,
        allowed_tools="Bash,Read",
    )


async def scaffold_project(
    description: str,
    project_path: str = "",
    language: str = "",
) -> str:
    """Scaffold a new project using Claude Code."""
    task_parts = [f"Scaffold a new project: {description}"]

    if project_path.strip():
        resolved = str(Path(project_path).expanduser().resolve())
        task_parts.append(f"Create it at: {resolved}")

    if language.strip():
        task_parts.append(f"Primary language/framework: {language}")

    task_parts.append(
        "Create a complete, well-structured project with:\n"
        "- Proper directory structure\n"
        "- Configuration files (package.json, pyproject.toml, etc.)\n"
        "- A README.md with setup instructions\n"
        "- Basic starter code\n"
        "- Git initialized with .gitignore\n"
        "Show me a tree of the created files when done."
    )

    task = "\n".join(task_parts)

    working_dir = ""
    if project_path.strip():
        parent = str(Path(project_path).expanduser().resolve().parent)
        if Path(parent).is_dir():
            working_dir = parent

    return await run_claude_code(
        task=task,
        working_directory=working_dir or str(DEFAULT_WORKING_DIR),
        allowed_tools="Bash,Read,Write,Edit",
    )
