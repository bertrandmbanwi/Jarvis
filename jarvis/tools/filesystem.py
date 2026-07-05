"""JARVIS File System Tools: safe file operations for managing files and folders."""
import fnmatch
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("jarvis.tools.filesystem")

PROTECTED_DIRS = [
    "/System", "/usr", "/bin", "/sbin", "/private", "/Library/Apple",
]

# Temp roots stay usable even though they live under a protected prefix
# (on macOS /tmp -> /private/tmp, and gettempdir() is /private/var/folders/...).
_TEMP_ROOTS = tuple(sorted({
    str(Path(p).resolve()) for p in ("/tmp", tempfile.gettempdir())
}))

# Directory names that hold credentials/keys. Blocked anywhere in the path so
# both reads and writes are refused (e.g. ~/.ssh, ~/.aws, project .git/config).
SENSITIVE_DIR_NAMES = {
    ".ssh", ".aws", ".gnupg", ".gpg", ".kube", ".docker",
    ".config/gcloud", ".azure", ".password-store",
}

# Filename globs for secret material, matched case-insensitively on any file.
SENSITIVE_FILE_GLOBS = [
    ".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*",
    "id_ecdsa*", "id_dsa*", ".netrc", "credentials", "credentials.*",
    "*.keychain", "*.keychain-db", ".htpasswd", "*.pfx", "*.p12",
]


def _is_path_safe(path: str) -> tuple[bool, str]:
    """Verify a path is neither a protected system dir nor a credential file.

    Applied to every read and write entry point so the LLM (or a prompt-injected
    instruction) cannot use these tools to exfiltrate secrets such as
    ``~/.ssh/id_rsa`` or a project ``.env``.
    """
    resolved = Path(path).expanduser().resolve()
    resolved_str = str(resolved)

    # Credential checks run first so secrets are refused even inside a temp root.
    lowered_parts = {part.lower() for part in resolved.parts}
    for sensitive in SENSITIVE_DIR_NAMES:
        # Handle both single-segment (".ssh") and nested (".config/gcloud") names.
        if all(seg in lowered_parts for seg in sensitive.split("/")):
            return False, f"Sensitive credential path: {sensitive}"

    name = resolved.name.lower()
    for glob in SENSITIVE_FILE_GLOBS:
        if fnmatch.fnmatch(name, glob):
            return False, f"Sensitive credential file: {resolved.name}"

    if resolved_str.startswith(_TEMP_ROOTS):
        return True, "OK"

    for protected in PROTECTED_DIRS:
        if resolved_str.startswith(protected):
            return False, f"Protected system path: {protected}"

    return True, "OK"


async def list_directory(path: str = ".", detailed: bool = True) -> str:
    """List contents of a directory."""
    safe, reason = _is_path_safe(path)
    if not safe:
        return f"Cannot list: {reason}"
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
    safe, reason = _is_path_safe(path)
    if not safe:
        return f"Cannot read: {reason}"
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return f"File not found: {path}"
        if not target.is_file():
            return f"Not a file: {path}"

        size = target.stat().st_size
        if size > 1_000_000:
            return f"File too large to read ({_format_size(size)}). Use a specific tool or command."

        with open(target, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if len(lines) > max_lines:
            content = "".join(lines[:max_lines])
            return f"{content}\n... (showing {max_lines} of {len(lines)} lines)"

        return "".join(lines)
    except Exception as e:
        return f"Error reading file: {e}"


async def write_file(path: str, content: str, overwrite: bool = False) -> str:
    """Write content to a file (creates or overwrites)."""
    safe, reason = _is_path_safe(path)
    if not safe:
        return f"Cannot write: {reason}"

    try:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            return (
                f"File already exists: {target}. "
                "Pass overwrite=true only after reading the file or receiving explicit user confirmation."
            )

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
    safe, reason = _is_path_safe(directory)
    if not safe:
        return f"Cannot search: {reason}"
    try:
        target = Path(directory).expanduser().resolve()
        if not target.exists():
            return f"Directory not found: {directory}"

        matches = [
            m for m in target.rglob(pattern)
            if _is_path_safe(str(m))[0]
        ][:max_results]

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
    safe, reason = _is_path_safe(path)
    if not safe:
        return f"Cannot inspect: {reason}"
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
    size_float = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_float < 1024:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024
    return f"{size_float:.1f} TB"
