"""JARVIS macOS Control Tools: AppleScript-based automation for Mac apps and system."""
import asyncio
import logging
import subprocess
from typing import Optional

logger = logging.getLogger("jarvis.tools.mac_control")


_BLOCKED_APPLESCRIPT_PHRASES = [
    "shut down", "restart", "log out", "sleep", "power off",
]

_PROTECTED_APPS = [
    "finder", "system events", "loginwindow", "dock", "systempolicyd", "windowserver",
]


def _is_applescript_safe(script: str) -> tuple[bool, str]:
    """Check if an AppleScript is safe to execute."""
    script_lower = script.lower()

    for phrase in _BLOCKED_APPLESCRIPT_PHRASES:
        if phrase in script_lower:
            return False, (
                f"Blocked: script contains '{phrase}'. "
                "JARVIS cannot shut down, restart, sleep, or log out. "
                "To shut down JARVIS itself, say 'quit JARVIS' or 'exit JARVIS'."
            )

    for app in _PROTECTED_APPS:
        if app in script_lower and "quit" in script_lower:
            return False, f"Blocked: cannot quit protected system process '{app}'."

    return True, "OK"


async def run_applescript(script: str) -> str:
    """Execute an AppleScript and return the output."""
    is_safe, reason = _is_applescript_safe(script)
    if not is_safe:
        logger.warning("Blocked AppleScript: %s (reason: %s)", script[:200], reason)
        return f"Error: {reason}"

    try:
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error = stderr.decode().strip()
            logger.error("AppleScript error: %s", error)
            return f"Error: {error}"

        return stdout.decode().strip()
    except Exception as e:
        logger.error("AppleScript execution failed: %s", e)
        return f"Error: {e}"


async def open_application(app_name: str) -> str:
    """Open a macOS application by name."""
    logger.info("Opening application: %s", app_name)
    result = await run_applescript(f'tell application "{app_name}" to activate')
    if result.startswith("Error"):
        return f"Failed to open {app_name}: {result}"
    return f"Opened {app_name} successfully."


async def close_application(app_name: str) -> str:
    """Close a macOS application by name."""
    logger.info("Closing application: %s", app_name)
    result = await run_applescript(f'tell application "{app_name}" to quit')
    if result.startswith("Error"):
        return f"Failed to close {app_name}: {result}"
    return f"Closed {app_name}."


async def get_running_applications() -> str:
    """Get a list of currently running applications."""
    script = '''
    tell application "System Events"
        set appList to name of every process whose background only is false
        set AppleScript's text item delimiters to ", "
        return appList as text
    end tell
    '''
    result = await run_applescript(script)
    return f"Running applications: {result}"


async def get_frontmost_application() -> str:
    """Get the name of the currently focused application."""
    script = '''
    tell application "System Events"
        return name of first process whose frontmost is true
    end tell
    '''
    return await run_applescript(script)


async def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    logger.info("Opening URL: %s", url)
    result = await run_applescript(f'open location "{url}"')
    if result.startswith("Error"):
        return f"Failed to open URL: {result}"
    return f"Opened {url} in browser."


async def open_url_in_browser(url: str, browser: str = "Google Chrome") -> str:
    """Open a URL in a specific browser application."""
    logger.info("Opening URL '%s' in %s", url, browser)
    script = f'''
    tell application "{browser}"
        activate
        open location "{url}"
    end tell
    '''
    result = await run_applescript(script)
    if result.startswith("Error"):
        logger.warning("Direct URL open in %s failed, trying fallback.", browser)
        await run_applescript(f'tell application "{browser}" to activate')
        result = await run_applescript(f'open location "{url}"')
        if result.startswith("Error"):
            return f"Failed to open URL in {browser}: {result}"
    return f"Opened {url} in {browser}."


async def search_in_browser(query: str, browser: str = "Google Chrome") -> str:
    """Open a web search in a specific browser using DuckDuckGo."""
    import urllib.parse
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://duckduckgo.com/?q={encoded_query}"
    logger.info("Searching '%s' in %s", query, browser)
    return await open_url_in_browser(search_url, browser)


async def open_file(file_path: str) -> str:
    """Open a file with its default application."""
    logger.info("Opening file: %s", file_path)
    try:
        process = await asyncio.create_subprocess_exec(
            "open", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            return f"Failed to open file: {stderr.decode().strip()}"
        return f"Opened {file_path}."
    except Exception as e:
        return f"Error opening file: {e}"


async def get_system_info() -> str:
    """Get basic system information."""
    script = '''
    set cpuInfo to do shell script "sysctl -n machdep.cpu.brand_string"
    set memInfo to do shell script "sysctl -n hw.memsize"
    set memGB to (memInfo as number) / 1073741824
    set memGB to (round (memGB * 10)) / 10
    set diskInfo to do shell script "df -H / | tail -1 | awk '{print $4}'"
    set batteryInfo to do shell script "pmset -g batt | grep -o '[0-9]*%' || echo 'N/A'"
    set uptimeInfo to do shell script "uptime | sed 's/.*up //' | sed 's/,.*//' "
    return "CPU: " & cpuInfo & "
Memory: " & memGB & " GB
Available disk: " & diskInfo & "
Battery: " & batteryInfo & "
Uptime: " & uptimeInfo
    '''
    return await run_applescript(script)


async def get_battery_status() -> str:
    """Get battery percentage and charging status."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pmset", "-g", "batt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode().strip()
        # Parse the output for useful info
        lines = output.split("\n")
        if len(lines) > 1:
            return lines[1].strip()
        return output
    except Exception as e:
        return f"Error getting battery: {e}"


async def set_volume(level: int) -> str:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    await run_applescript(f"set volume output volume {level}")
    return f"Volume set to {level}%."


async def set_brightness(level: int) -> str:
    """Set display brightness (0-100)."""
    level = max(0, min(100, level))
    fraction = level / 100.0
    try:
        import asyncio
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e",
            f'tell application "System Events" to set value of slider 1 '
            f'of group 1 of group 2 of window 1 of application process '
            f'"ControlCenter" to {fraction}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            process2 = await asyncio.create_subprocess_exec(
                "brightness", str(fraction),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process2.communicate()
            if process2.returncode != 0:
                return f"Brightness adjustment requires the 'brightness' CLI tool. Install with: brew install brightness"
        return f"Brightness set to {level}%."
    except Exception as e:
        return f"Error setting brightness: {e}"


async def toggle_do_not_disturb(enable: bool) -> str:
    """Toggle Do Not Disturb / Focus mode (requires Shortcut named 'Toggle DND')."""
    action = "turn on" if enable else "turn off"
    logger.info("Do Not Disturb: %s", action)

    try:
        import asyncio
        process = await asyncio.create_subprocess_exec(
            "shortcuts", "run", "Toggle DND",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0:
            return f"Do Not Disturb toggled ({action})."

        return (
            f"To {action} Do Not Disturb, I need a Shortcut named 'Toggle DND' "
            f"in your Shortcuts app. Create one that toggles the Focus mode, "
            f"and I can control it automatically."
        )
    except Exception as e:
        return f"Error toggling Do Not Disturb: {e}"


async def send_notification(title: str, message: str) -> str:
    """Send a macOS notification."""
    script = f'display notification "{message}" with title "{title}"'
    await run_applescript(script)
    return f"Notification sent: {title}"


async def get_clipboard() -> str:
    """Get the current clipboard contents."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pbpaste",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        content = stdout.decode().strip()
        if not content:
            return "Clipboard is empty."
        if len(content) > 500:
            return f"Clipboard ({len(content)} chars): {content[:500]}..."
        return f"Clipboard: {content}"
    except Exception as e:
        return f"Error reading clipboard: {e}"


async def set_clipboard(text: str) -> str:
    """Set the clipboard contents."""
    try:
        process = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
        )
        await process.communicate(input=text.encode())
        return f"Copied to clipboard ({len(text)} chars)."
    except Exception as e:
        return f"Error setting clipboard: {e}"


async def paste_to_app(text: str, app_name: str, new_document: bool = True) -> str:
    """Paste text into an application (requires macOS Accessibility permissions)."""
    logger.info("Pasting %d chars to %s (new_doc=%s)", len(text), app_name, new_document)

    try:
        process = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
        )
        await process.communicate(input=text.encode())
    except Exception as e:
        return f"Error setting clipboard: {e}"

    if new_document:
        script = f'''
        tell application "{app_name}" to activate
        delay 0.8
        tell application "System Events"
            keystroke "n" using command down
            delay 0.5
            keystroke "v" using command down
        end tell
        '''
    else:
        script = f'''
        tell application "{app_name}" to activate
        delay 0.5
        tell application "System Events"
            keystroke "v" using command down
        end tell
        '''

    result = await run_applescript(script)

    if result.startswith("Error"):
        if "not allowed" in result.lower() or "1002" in result:
            return (
                f"Failed to paste to {app_name}. macOS blocked the keystroke. "
                f"To fix: open System Settings > Privacy & Security > Accessibility, "
                f"then add Terminal (or your Python process) to the allowed list. "
                f"The text is still on your clipboard; you can paste manually with Cmd+V."
            )
        return f"Failed to paste to {app_name}: {result}. Text is on clipboard; try Cmd+V manually."

    return f"Pasted {len(text)} characters into {app_name} successfully."


async def write_to_app(text: str, app_name: str, new_document: bool = True) -> str:
    """Write text into an application using keystroke input (best for short text)."""
    if len(text) > 500:
        logger.info("Text too long for keystroke (%d chars), falling back to paste.", len(text))
        return await paste_to_app(text, app_name, new_document)

    logger.info("Typing %d chars into %s", len(text), app_name)

    escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')

    if new_document:
        script = f'''
        tell application "{app_name}" to activate
        delay 0.8
        tell application "System Events"
            keystroke "n" using command down
            delay 0.5
            keystroke "{escaped_text}"
        end tell
        '''
    else:
        script = f'''
        tell application "{app_name}" to activate
        delay 0.5
        tell application "System Events"
            keystroke "{escaped_text}"
        end tell
        '''

    result = await run_applescript(script)

    if result.startswith("Error"):
        if "not allowed" in result.lower() or "1002" in result:
            return (
                f"Failed to type in {app_name}. macOS blocked the keystroke. "
                f"To fix: open System Settings > Privacy & Security > Accessibility, "
                f"then add Terminal (or your Python process) to the allowed list."
            )
        return f"Failed to type in {app_name}: {result}"

    return f"Typed {len(text)} characters into {app_name} successfully."
