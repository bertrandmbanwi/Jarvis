"""
Apple Notes integration for JARVIS via AppleScript.

POLICY: READ and CREATE only. No edit or delete operations for safety.

Provides async access to Apple Notes with:
- Reading recent notes and searching by title/content
- Creating new notes in specified folders
- Support for markdown-to-HTML conversion for checklists
- Proper timeouts and error handling for all AppleScript operations
"""
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger("jarvis.tools.notes")

DEFAULT_TIMEOUT = 10.0
READ_TIMEOUT = 15.0


async def _run_notes_script(script: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """
    Run an AppleScript for Notes.app.

    Args:
        script: AppleScript code to execute
        timeout: Timeout in seconds

    Returns:
        Script output as string

    Raises:
        TimeoutError: If script exceeds timeout
        RuntimeError: If script execution fails
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )

            if stderr:
                error_msg = stderr.decode("utf-8").strip()
                logger.warning("AppleScript error: %s", error_msg)
                raise RuntimeError(f"Notes.app script error: {error_msg}")

            return stdout.decode("utf-8").strip()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Notes.app script timed out after {timeout}s")
    except Exception as e:
        logger.error("Failed to run Notes script: %s", e)
        raise


def _body_to_html(body: str) -> str:
    """
    Convert markdown-style checklists to HTML for Apple Notes.

    Supports:
        - [ ] Unchecked item
        - [x] Checked item

    Args:
        body: Markdown-formatted body text

    Returns:
        HTML-formatted body for Notes.app
    """
    try:
        # Convert markdown checkboxes to HTML
        # [x] or [ ] patterns become HTML checklist items
        html = body

        # Match checked items [x]
        html = re.sub(
            r'- \[x\]\s+(.+?)(?=\n|$)',
            r'<li><input type="checkbox" checked> \1</li>',
            html,
            flags=re.MULTILINE | re.IGNORECASE
        )

        # Match unchecked items [ ]
        html = re.sub(
            r'- \[\s*\]\s+(.+?)(?=\n|$)',
            r'<li><input type="checkbox"> \1</li>',
            html,
            flags=re.MULTILINE
        )

        # Wrap consecutive list items in <ul>
        if '<li>' in html:
            html = re.sub(
                r'(<li>.*?</li>)',
                lambda m: '<ul>' + m.group(1) + '</ul>',
                html,
                flags=re.DOTALL
            )
            # Remove duplicate ul tags
            html = re.sub(r'</ul>\s*<ul>', '', html)

        return html if '<' in html else body
    except Exception as e:
        logger.warning("Failed to convert markdown to HTML: %s", e)
        return body


async def get_recent_notes(count: int = 10) -> list[dict]:
    """
    Get recently created notes from Notes.app.

    Args:
        count: Number of recent notes to fetch

    Returns:
        List of dicts with keys: title, date, folder, preview
    """
    try:
        script = f"""
tell application "Notes"
    set notesList to {{}}
    repeat with n from 1 to min({count}, (count of notes))
        set noteItem to note n
        set noteTitle to name of noteItem
        set noteDate to creation date of noteItem
        set noteFolder to container of noteItem
        set folderName to name of noteFolder

        set notePreview to body of noteItem
        if length of notePreview > 100 then
            set notePreview to (text 1 through 100 of notePreview) & "..."
        end if

        set noteEntry to noteTitle & "|" & noteDate & "|" & folderName & "|" & notePreview
        set end of notesList to noteEntry
    end repeat

    return notesList
end tell
"""
        output = await _run_notes_script(script, timeout=READ_TIMEOUT)

        results = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 3)
            if len(parts) >= 3:
                results.append({
                    "title": parts[0].strip(),
                    "date": parts[1].strip(),
                    "folder": parts[2].strip(),
                    "preview": parts[3].strip() if len(parts) > 3 else ""
                })

        logger.debug("Retrieved %d recent notes", len(results))
        return results
    except Exception as e:
        logger.error("Failed to get recent notes: %s", e)
        return []


async def read_note(title_match: str) -> Optional[dict]:
    """
    Read a single note by partial title match.

    Searches for a note whose title contains the search term.
    Returns the full content truncated to 3000 characters.

    Args:
        title_match: Partial title to search for

    Returns:
        Dict with keys: title, body, folder, created_date
        Returns None if not found or on error
    """
    try:
        script = f"""
tell application "Notes"
    set searchTerm to "{title_match}"
    set foundNote to missing value

    repeat with n from 1 to count of notes
        set noteItem to note n
        set noteTitle to name of noteItem
        if noteTitle contains searchTerm then
            set foundNote to noteItem
            exit repeat
        end if
    end repeat

    if foundNote is not missing value then
        set noteBody to body of foundNote
        if length of noteBody > 3000 then
            set noteBody to (text 1 through 3000 of noteBody) & "[...truncated]"
        end if

        set noteFolder to container of foundNote
        set folderName to name of noteFolder
        set noteDate to creation date of foundNote

        return name of foundNote & "||" & noteBody & "||" & folderName & "||" & noteDate
    else
        return "NOT_FOUND"
    end if
end tell
"""
        output = await _run_notes_script(script, timeout=READ_TIMEOUT)

        if output == "NOT_FOUND":
            logger.debug("Note not found: %s", title_match)
            return None

        parts = output.split("||", 3)
        if len(parts) >= 2:
            return {
                "title": parts[0].strip(),
                "body": parts[1].strip(),
                "folder": parts[2].strip() if len(parts) > 2 else "Notes",
                "created_date": parts[3].strip() if len(parts) > 3 else ""
            }
        return None
    except Exception as e:
        logger.error("Failed to read note: %s", e)
        return None


async def search_notes(query: str, count: int = 10) -> list[dict]:
    """
    Search notes by content or title.

    Args:
        query: Search term
        count: Maximum results to return

    Returns:
        List of matching notes with title, folder, preview
    """
    try:
        script = f"""
tell application "Notes"
    set searchTerm to "{query}"
    set resultsList to {{}}
    set matchCount to 0

    repeat with n from 1 to count of notes
        if matchCount >= {count} then exit repeat

        set noteItem to note n
        set noteTitle to name of noteItem
        set noteBody to body of noteItem

        if noteTitle contains searchTerm or noteBody contains searchTerm then
            set noteFolder to container of noteItem
            set folderName to name of noteFolder

            set notePreview to noteBody
            if length of notePreview > 150 then
                set notePreview to (text 1 through 150 of notePreview) & "..."
            end if

            set resultEntry to noteTitle & "|" & folderName & "|" & notePreview
            set end of resultsList to resultEntry
            set matchCount to matchCount + 1
        end if
    end repeat

    return resultsList
end tell
"""
        output = await _run_notes_script(script, timeout=READ_TIMEOUT)

        results = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) >= 2:
                results.append({
                    "title": parts[0].strip(),
                    "folder": parts[1].strip(),
                    "preview": parts[2].strip() if len(parts) > 2 else ""
                })

        logger.debug("Found %d notes matching query: %s", len(results), query)
        return results
    except Exception as e:
        logger.error("Failed to search notes: %s", e)
        return []


async def create_note(
    title: str,
    body: str,
    folder: str = "Notes"
) -> bool:
    """
    Create a new note in Notes.app.

    Supports markdown-to-HTML conversion for checklists.
    Note: folder parameter is case-sensitive and must match
    an existing folder in Notes.app.

    Args:
        title: Note title
        body: Note body (supports markdown checklists)
        folder: Destination folder name (default: "Notes")

    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert markdown checklists to HTML if present
        if "[" in body and "]" in body:
            converted_body = _body_to_html(body)
        else:
            converted_body = body

        # Escape quotes for AppleScript
        safe_title = title.replace('"', '\\"')
        safe_body = converted_body.replace('"', '\\"')
        safe_folder = folder.replace('"', '\\"')

        script = f"""
tell application "Notes"
    set newNote to create note with properties {{name:"{safe_title}", body:"{safe_body}"}}

    tell application "System Events"
        tell process "Notes"
            -- Move to folder if it exists
            try
                set targetFolder to folder "{safe_folder}"
                move newNote to targetFolder
            end try
        end tell
    end tell

    return "SUCCESS"
end tell
"""
        output = await _run_notes_script(script, timeout=DEFAULT_TIMEOUT)

        if output == "SUCCESS":
            logger.info("Note created: title=%s, folder=%s", title, folder)
            return True
        else:
            logger.warning("Note creation returned unexpected output: %s", output)
            return False
    except Exception as e:
        logger.error("Failed to create note: %s", e)
        return False


async def get_note_folders() -> list[str]:
    """
    Get list of all folders in Notes.app.

    Returns:
        List of folder names
    """
    try:
        script = """
tell application "Notes"
    set foldersList to {}
    repeat with f from 1 to count of folders
        set folderName to name of folder f
        set end of foldersList to folderName
    end repeat
    return foldersList
end tell
"""
        output = await _run_notes_script(script, timeout=DEFAULT_TIMEOUT)

        folders = [f.strip() for f in output.split("\n") if f.strip()]
        logger.debug("Retrieved %d folders from Notes.app", len(folders))
        return folders
    except Exception as e:
        logger.error("Failed to get note folders: %s", e)
        return ["Notes"]  # Return default folder if query fails
