"""Delegate coding work to a local coding agent CLI: OpenAI Codex or Claude Code.

JARVIS_CODING_AGENT picks the agent: "codex", "claude", or "auto" (default).
Auto prefers Codex when OpenAI is the LLM provider and Codex is installed,
otherwise whichever CLI is installed.
"""
import asyncio
import contextlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from jarvis.config import settings
from jarvis.tools import claude_code

logger = logging.getLogger("jarvis.tools.coding_agent")

CODEX_TIMEOUT = 300
MAX_OUTPUT_CHARS = 8000
DEFAULT_WORKING_DIR = Path.home()


def find_codex_binary() -> str | None:
    """Locate the codex CLI binary."""
    candidates = [
        shutil.which("codex"),
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
        str(Path.home() / ".local" / "bin" / "codex"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def choose_agent(requested: str = "") -> str:
    """Return "codex" or "claude" for this call."""
    choice = (requested or settings.CODING_AGENT).strip().lower()
    if settings.OFFLINE_MODE:
        return "codex"  # Claude Code needs the cloud; Codex can run on Ollama (--oss)
    if choice in ("codex", "claude"):
        return choice
    has_codex = find_codex_binary() is not None
    has_claude = claude_code._find_claude_binary() is not None
    if settings.LLM_PROVIDER == "openai" and has_codex:
        return "codex"
    if has_claude:
        return "claude"
    return "codex"


def _truncate(output: str) -> str:
    if len(output) > MAX_OUTPUT_CHARS:
        return output[: MAX_OUTPUT_CHARS - 500] + f"\n\n... [output truncated, total length: {len(output)} chars]"
    return output


def build_codex_command(
    codex_bin: str,
    task: str,
    cwd: str,
    output_file: str,
    *,
    read_only: bool = False,
    continue_session: bool = False,
) -> list[str]:
    cmd = [codex_bin, "exec"]
    if continue_session:
        cmd += ["resume", "--last"]
    cmd += [
        "--cd", cwd,
        "--sandbox", "read-only" if read_only else "workspace-write",
        "--skip-git-repo-check",
        "--output-last-message", output_file,
    ]
    if settings.OFFLINE_MODE:
        cmd += ["--oss", "--local-provider", "ollama"]  # Codex on a local model
    if settings.CODEX_MODEL:
        cmd += ["--model", settings.CODEX_MODEL]
    # "--" ends option parsing so a task starting with "-" isn't read as a flag.
    return [*cmd, "--", task]


async def run_codex(
    task: str,
    working_directory: str = "",
    continue_session: bool = False,
    read_only: bool = False,
) -> str:
    """Run a task with `codex exec` (sandboxed to the working directory)."""
    codex_bin = find_codex_binary()
    if not codex_bin:
        return "Error: Codex CLI not found. Install it with: npm install -g @openai/codex"

    cwd = str(Path(working_directory.strip() or DEFAULT_WORKING_DIR).expanduser().resolve())
    if not Path(cwd).is_dir():
        return f"Error: working directory does not exist: {cwd}"

    fd, output_file = tempfile.mkstemp(prefix="jarvis-codex-", suffix=".txt")
    os.close(fd)
    cmd = build_codex_command(
        codex_bin, task, cwd, output_file, read_only=read_only, continue_session=continue_session
    )
    logger.info("Codex: running task in %s (timeout: %ds)", cwd, CODEX_TIMEOUT)
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=CODEX_TIMEOUT)
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:500] or "Unknown error"
            logger.error("Codex exited with code %d: %s", process.returncode, detail)
            return f"Codex task failed (exit code {process.returncode}):\n{detail}"
        final = Path(output_file).read_text(encoding="utf-8", errors="replace").strip()
        output = final or stdout.decode("utf-8", errors="replace").strip()
        return _truncate(output or "(Codex completed the task but produced no text output.)")
    except TimeoutError:
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        return f"Error: Codex task timed out after {CODEX_TIMEOUT} seconds."
    except Exception as e:
        logger.error("Codex: unexpected error: %s", e)
        return f"Error running Codex: {str(e)[:300]}"
    finally:
        with contextlib.suppress(OSError):
            Path(output_file).unlink()


async def run_coding_agent(
    task: str,
    working_directory: str = "",
    allowed_tools: str = "",
    continue_session: bool = False,
    session_name: str = "",
    agent: str = "",
) -> str:
    """Run a coding task with the configured coding agent (Codex or Claude Code)."""
    if choose_agent(agent) == "claude":
        return await claude_code.run_claude_code(
            task, working_directory, allowed_tools, continue_session, session_name
        )
    return await run_codex(task, working_directory, continue_session=continue_session)


async def run_terminal_command(command: str, working_directory: str = "") -> str:
    """Run a terminal command through the coding agent, with safety awareness."""
    if choose_agent() == "claude":
        return await claude_code.run_terminal_command(command, working_directory)
    task = (
        "Run the following terminal command and show me the output. "
        "If the command seems destructive or risky, warn before executing.\n\n"
        f"Command: {command}"
    )
    return await run_codex(task, working_directory)


async def scaffold_project(description: str, project_path: str = "", language: str = "") -> str:
    """Scaffold a new project with the coding agent."""
    if choose_agent() == "claude":
        return await claude_code.scaffold_project(description, project_path, language)
    task_parts = [f"Scaffold a new project: {description}"]
    working_dir = ""
    if project_path.strip():
        resolved = Path(project_path).expanduser().resolve()
        task_parts.append(f"Create it at: {resolved}")
        if resolved.parent.is_dir():
            working_dir = str(resolved.parent)
    if language.strip():
        task_parts.append(f"Primary language/framework: {language}")
    task_parts.append(
        "Create a complete, well-structured project with a proper directory structure, "
        "configuration files, a README.md with setup instructions, basic starter code, "
        "and git initialized with .gitignore. Show a tree of the created files when done."
    )
    return await run_codex("\n".join(task_parts), working_dir or str(DEFAULT_WORKING_DIR))
