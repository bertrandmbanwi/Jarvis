"""Lightweight structured tracing for JARVIS runtime operations.

The implementation intentionally stays dependency-free: traces are JSON Lines
written under data/logs so they work in local development, launchd, and CI
without requiring a collector.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from jarvis.config import settings

logger = logging.getLogger("jarvis.tracing")

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("jarvis_trace_id", default="")
_TRACE_LOG_PATH = settings.LOGS_DIR / "traces.jsonl"
_MAX_ATTR_LEN = 2000


def new_trace_id() -> str:
    """Create a compact, URL-safe trace identifier."""
    return uuid.uuid4().hex


def get_trace_id() -> str:
    """Return the current trace ID, creating one when absent."""
    trace_id = _trace_id_var.get()
    if trace_id:
        return trace_id
    trace_id = new_trace_id()
    _trace_id_var.set(trace_id)
    return trace_id


def set_trace_id(trace_id: str | None = None) -> contextvars.Token[str]:
    """Set the active trace ID and return the context token for reset."""
    return _trace_id_var.set(trace_id or new_trace_id())


def reset_trace_id(token: contextvars.Token[str]) -> None:
    """Restore the prior trace ID context."""
    _trace_id_var.reset(token)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > _MAX_ATTR_LEN:
            return value[:_MAX_ATTR_LEN] + "...[truncated]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(v) for v in list(value)[:50]]
    return repr(value)[:_MAX_ATTR_LEN]


def _write_event(event: dict[str, Any], path: Path = _TRACE_LOG_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    except Exception as exc:
        logger.debug("Trace write failed: %s", exc)


def record_event(name: str, **attrs: Any) -> None:
    """Record a structured point-in-time tracing event."""
    event = {
        "type": "event",
        "name": name,
        "trace_id": get_trace_id(),
        "timestamp": time.time(),
        "attrs": _sanitize_value(attrs),
    }
    _write_event(event)


@contextlib.contextmanager
def trace_span(name: str, **attrs: Any) -> Iterator[None]:
    """Record a structured duration span around a block of work."""
    trace_id = get_trace_id()
    start = time.time()
    error = ""
    try:
        yield
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        event = {
            "type": "span",
            "name": name,
            "trace_id": trace_id,
            "timestamp": start,
            "duration_s": round(time.time() - start, 6),
            "error": error,
            "attrs": _sanitize_value(attrs),
        }
        _write_event(event)
