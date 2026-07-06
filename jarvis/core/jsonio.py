"""Shared JSON file persistence: safe reads with a default, atomic writes.

Centralizes the read-with-default / write-with-encoding pattern that was
copy-pasted across the memory, profile, and lifecycle modules. Writes go through
a temp file + os.replace so a crash mid-write cannot leave a truncated file.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.core.jsonio")


def read_json(path: Path, default: Any = None) -> Any:
    """Parse JSON from path, returning default if the file is missing or unreadable."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("Could not read JSON from %s: %s", path, e)
        return default


def write_json(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
) -> None:
    """Serialize data and write it to path atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)
