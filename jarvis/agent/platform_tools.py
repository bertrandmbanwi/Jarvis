"""Which tools work on the current operating system.

JARVIS's backend also runs on Linux (e.g. in Docker), where the tools that
drive macOS through AppleScript, screencapture and the like can't work.
Those are hidden from the model there and refuse politely if called.
"""
from __future__ import annotations

import sys
from typing import Any

IS_MACOS = sys.platform == "darwin"

MACOS_ONLY_MODULES = frozenset({
    "jarvis.tools.mac_control",   # apps, volume, clipboard, notifications (AppleScript)
    "jarvis.tools.screen",        # screencapture + OCR
    "jarvis.tools.calendar_email",  # Calendar.app and Mail.app
    "jarvis.tools.notes_access",  # Notes.app
})


def is_available(tool_name: str) -> bool:
    """True if the tool can run on this OS."""
    if IS_MACOS:
        return True
    from jarvis.agent.tools_schema import TOOL_REGISTRY

    fn = TOOL_REGISTRY.get(tool_name)
    return getattr(fn, "__module__", "") not in MACOS_ONLY_MODULES


def available_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if IS_MACOS:
        return schemas
    return [s for s in schemas if is_available(str(s.get("name", "")))]
