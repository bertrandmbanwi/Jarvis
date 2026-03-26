"""JARVIS File System Tools: safe file operations for managing files and folders."""
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tools.filesystem")

PROTECTED_DIRS = [
    "/System", "/usr", "/bin", "/sbin", "/private", "/Library/Apple",
]


def _is_path_safe(path: str) -> tuple[bool, str]:
    """Verify path is not a protected system directory."""
    resolved = str(Path(path).resolve())
    for protected in PROTECTED_DIRS:
        if resolved.startswith(protected):
            return False, f"Protected system path: {protected}"
    return True, "OK"


async def list_directory(path: str = ".", detailed: bool = True) -> str:
    """List contents of a directory."""
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return f"Directory not found: {path}"
        if not target.is_dir():
            return f"Not a directory: {path}"

        items = sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = [f"Contents of {target}:\n"]

        for item in items:
            if item.name.startswith("."):
                continue

            if detailed:
                stat = item.stat()
                size = stat.st_size
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                if item.is_dir():
                    lines.append(f"  [DIR]  {item.name}/  ({modified})")
                else:
                    size_str = _format_size(size)
                    lines.append(f"  [FILE] {item.name}  ({size_str}, {modified})")
            else:
                prefix = "[DIR] " if item.is_dir() else "      "
                lines.append(f"  {prefix}{item.name}")

        if len(lines) == 1:
            lines.append("  (empty directory)")

        return "\n".join(lines)
    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"


async def read_file(path: str, max_lines: int = 100) -> str:
    """Read the contents of a text file."""
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return f"File not found: {path}"
        if not target.is_file():
            return f"Not a file: {path}"

        size = target.stat().st_size
        if size > 1_000_000:
            return f"File too large to read ({_format_size(size)}). Use a specific tool or command."

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if len(lines) > max_lines:
            content = "".join(lines[:max_lines])
            return f"{content}\n... (showing {max_lines} of {len(lines)} lines)"

        return "".join(lines)
    except Exception as e:
        return f"Error reading file: {e}"


async def write_file(path: str, content: str) -> str:
    """Write content to a file (creates or overwrites)."""
    safe, reason = _is_path_safe(path)
    if not safe:
        return f"Cannot write: {reason}"

    try:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Wrote %d chars to %s", len(content), target)
        return f"Written {len(content)} characters to {target}."
    except Exception as e:
        return f"Error writing file: {e}"


async def create_directory(path: str) -> str:
    """Create a directory and parent directories if needed."""
    safe, reason = _is_path_safe(path)
    if not safe:
        return f"Cannot create: {reason}"

    try:
        target = Path(path).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return f"Created directory: {target}"
    except Exception as e:
        return f"Error creating directory: {e}"


async def move_file(source: str, destination: str) -> str:
    """Move or rename a file/directory."""
    safe_s, reason_s = _is_path_safe(source)
    safe_d, reason_d = _is_path_safe(destination)
    if not safe_s:
        return f"Cannot move source: {reason_s}"
    if not safe_d:
        return f"Cannot move to destination: {reason_d}"

    try:
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()

        if not src.exists():
            return f"Source not found: {source}"

        shutil.move(str(src), str(dst))
        return f"Moved {src.name} to {dst}."
    except Exception as e:
        return f"Error moving: {e}"


async def copy_file(source: str, destination: str) -> str:
    """Copy a file or directory."""
    safe_s, reason_s = _is_path_safe(source)
    safe_d, reason_d = _is_path_safe(destination)
    if not safe_s:
        return f"Cannot copy source: {reason_s}"
    if not safe_d:
        return f"Cannot copy to destination: {reason_d}"

    try:
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()

        if not src.exists():
            return f"Source not found: {source}"

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

        return f"Copied {src.name} to {dst}."
    except Exception as e:
        return f"Error copying: {e}"


async def search_files(
    directory: str = ".",
    pattern: str = "*",
    max_results: int = 20,
) -> str:
    """Search for files matching a glob pattern."""
    try:
        target = Path(directory).expanduser().resolve()
        if not target.exists():
            return f"Directory not found: {directory}"

        matches = list(target.rglob(pattern))[:max_results]

        if not matches:
            return f"No files matching '{pattern}' in {target}"

        lines = [f"Found {len(matches)} files matching '{pattern}':"]
        for m in matches:
            rel = m.relative_to(target) if m.is_relative_to(target) else m
            size = _format_size(m.stat().st_size) if m.is_file() else "DIR"
            lines.append(f"  {rel}  ({size})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching: {e}"


async def get_file_info(path: str) -> str:
    """Get detailed information about a file or directory."""
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return f"Not found: {path}"

        stat = target.stat()
        info = [
            f"Path: {target}",
            f"Type: {'Directory' if target.is_dir() else 'File'}",
            f"Size: {_format_size(stat.st_size)}",
            f"Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}",
            f"Created: {datetime.fromtimestamp(stat.st_birthtime).strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if target.is_dir():
            children = list(target.iterdir())
            info.append(f"Contains: {len(children)} items")

        return "\n".join(info)
    except Exception as e:
        return f"Error getting info: {e}"


def _format_size(size: int) -> str:
    """Convert bytes to human-readable format (B, KB, MB, GB, TB)."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
