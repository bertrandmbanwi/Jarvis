"""JARVIS Shell Command Execution: runs shell commands safely on macOS with timeout."""
import asyncio
import logging
import shlex
from typing import Optional

logger = logging.getLogger("jarvis.tools.shell")

BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf ~", "rm -rf /*", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "sudo rm",
]

BLOCKED_POWER_PATTERNS = [
    "shutdown", "reboot", "restart", "halt", "poweroff", "power off",
    "log out", "logout", "pmset sleepnow", "systemsetup", "fdesetup",
    "shut down", "sleep", "osascript",
]

_APPLESCRIPT_POWER_PHRASES = [
    "shut down", "restart", "sleep", "log out", "power off",
]

SENSITIVE_PREFIXES = [
    "rm ", "sudo ", "kill ", "killall ", "diskutil",
]


def is_command_safe(command: str) -> tuple[bool, str]:
    """Verify command is not destructive or power-affecting."""
    cmd_lower = command.lower().strip()

    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Blocked: contains dangerous pattern '{blocked}'"

    for power_cmd in ["shutdown", "reboot", "halt", "poweroff", "pmset sleepnow"]:
        if power_cmd in cmd_lower:
            return False, (
                f"Blocked: '{power_cmd}' would affect the host computer. "
                "JARVIS cannot shut down, restart, or sleep the system."
            )

    if "osascript" in cmd_lower:
        for phrase in _APPLESCRIPT_POWER_PHRASES:
            if phrase in cmd_lower:
                return False, (
                    f"Blocked: AppleScript command contains '{phrase}'. "
                    "JARVIS cannot shut down, restart, or sleep the system."
                )

    for prefix in SENSITIVE_PREFIXES:
        if cmd_lower.startswith(prefix):
            return True, f"Warning: sensitive command ({prefix.strip()}). Proceeding with caution."

    return True, "OK"


async def run_command(
    command: str,
    timeout: float = 30.0,
    working_dir: Optional[str] = None,
) -> str:
    """Execute a shell command and return its output."""
    is_safe, reason = is_command_safe(command)
    if not is_safe:
        logger.warning("Blocked command: %s (%s)", command, reason)
        return f"Command blocked for safety: {reason}"

    if reason != "OK":
        logger.info("Sensitive command: %s (%s)", command, reason)

    logger.info("Executing: %s", command[:200])

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return f"Command timed out after {timeout}s: {command}"

        output_parts = []
        if stdout:
            output_parts.append(stdout.decode("utf-8", errors="replace").strip())
        if stderr:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if stderr_text:
                output_parts.append(f"[stderr] {stderr_text}")

        output = "\n".join(output_parts)

        if process.returncode != 0:
            output = f"[exit code {process.returncode}] {output}"

        # Truncate very long output
        if len(output) > 3000:
            output = output[:3000] + f"\n... (truncated, {len(output)} total chars)"

        logger.info("Command completed (exit %d, %d chars output)",
                     process.returncode, len(output))
        return output or "(no output)"

    except Exception as e:
        logger.error("Command execution error: %s", e)
        return f"Error executing command: {e}"


async def run_command_background(command: str) -> str:
    """Start a command in the background (non-blocking)."""
    is_safe, reason = is_command_safe(command)
    if not is_safe:
        return f"Command blocked for safety: {reason}"

    logger.info("Starting background command: %s", command[:200])

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return f"Started in background (PID: {process.pid})."
    except Exception as e:
        return f"Error starting background command: {e}"
