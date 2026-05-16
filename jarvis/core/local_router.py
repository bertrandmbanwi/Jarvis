"""Deterministic local-first routing for cheap, common assistant actions."""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from jarvis.core import feedback, profile
from jarvis.tools import mac_control, weather


@dataclass(frozen=True)
class LocalRouteResult:
    response: str
    action: str
    tier: str = "local"
    remember: bool = True


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def is_probable_noise(text: str) -> bool:
    """Reject common STT noise before it reaches a paid model."""
    cleaned = _clean(text).lower().strip(".,!? ")
    if not cleaned:
        return True
    if len(cleaned) <= 2 and cleaned not in {"hi", "ok", "no"}:
        return True
    if re.fullmatch(r"(?:\d+[\s,.-]*){3,}", cleaned):
        return True
    number_words = {
        "zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten",
    }
    tokens = [token for token in re.split(r"[\s,.-]+", cleaned) if token]
    if len(tokens) >= 4 and all(token in number_words for token in tokens):
        return True
    words = cleaned.split()
    if len(words) >= 4 and len(set(words)) <= 2:
        return True
    return len(cleaned) < 8 and not re.search(r"[a-z]{3,}", cleaned)


def _extract_weather_location(text: str) -> str:
    lowered = text.lower()
    match = re.search(r"\b(?:weather|forecast|temperature)\b.*?\b(?:in|for|at)\s+(.+)$", lowered)
    if not match:
        match = re.search(r"\b(?:in|for|at)\s+(.+?)\s+(?:weather|forecast|temperature)\b", lowered)
    if not match:
        return ""
    location = match.group(1)
    location = re.sub(r"\b(?:today|tomorrow|right now|this morning|this afternoon|this evening)\b", "", location)
    return _clean(location.strip(" ?!."))


async def _run(action: str, fn: Callable[..., Awaitable[str]], *args) -> LocalRouteResult:
    return LocalRouteResult(response=await fn(*args), action=action)


async def route_local(text: str, *, privacy_mode: bool = False) -> LocalRouteResult | None:
    """Handle high-confidence local commands without an LLM call."""
    raw = _clean(text)
    lowered = raw.lower()

    if is_probable_noise(raw):
        return LocalRouteResult(
            response="I heard noise, but not a clear request.",
            action="noise_guard",
            remember=False,
        )

    if re.search(r"\b(?:privacy mode|private mode|do not remember|don't remember)\b", lowered):
        if re.search(r"\b(?:off|disable|stop|turn off)\b", lowered):
            return LocalRouteResult("Privacy mode is off. I will resume normal memory handling.", "privacy_off", remember=False)
        return LocalRouteResult("Privacy mode is on. I will avoid storing this session's conversation and memories.", "privacy_on", remember=False)

    if re.search(r"\b(?:that was wrong|that's wrong|you were wrong|incorrect|bad answer)\b", lowered):
        item = feedback.add_feedback(raw, category="correction")
        return LocalRouteResult(
            response=f"Noted. I logged that correction so I can adapt next time. Feedback id: {item['id'][:8]}.",
            action="feedback_correction",
            remember=not privacy_mode,
        )

    if lowered.startswith(("remember this:", "remember that ")):
        item = feedback.add_feedback(raw, category="memory_instruction")
        return LocalRouteResult(
            response=f"Remembered. I saved that as a user instruction. Feedback id: {item['id'][:8]}.",
            action="feedback_memory_instruction",
            remember=not privacy_mode,
        )

    if re.search(r"\b(weather|forecast|temperature)\b", lowered):
        location = _extract_weather_location(raw)
        return await _run("weather", weather.get_weather, location)

    if re.search(r"\b(?:what time is it|current time|time right now)\b", lowered):
        return LocalRouteResult(
            response=f"It is {datetime.now().strftime('%I:%M %p').lstrip('0')}.",
            action="time",
        )

    if re.search(r"\b(?:what(?:'s| is) today|today's date|current date|what date is it)\b", lowered):
        return LocalRouteResult(
            response=f"Today is {datetime.now().strftime('%A, %B %d, %Y')}.",
            action="date",
        )

    if "battery" in lowered:
        return await _run("battery", mac_control.get_battery_status)

    if re.search(r"\b(?:system info|system status|computer status)\b", lowered):
        return await _run("system_info", mac_control.get_system_info)

    if re.search(r"\b(?:running apps|running applications|what apps are open|open apps)\b", lowered):
        return await _run("running_apps", mac_control.get_running_applications)

    if re.search(r"\b(?:frontmost app|current app|active app|focused app)\b", lowered):
        return await _run("frontmost_app", mac_control.get_frontmost_application)

    volume_match = re.search(r"\b(?:set|turn)\s+(?:the\s+)?volume\s+(?:to\s+)?(\d{1,3})\b", lowered)
    if volume_match:
        return await _run("set_volume", mac_control.set_volume, int(volume_match.group(1)))

    if re.search(r"\b(?:read|what(?:'s| is) on|show)\s+(?:the\s+)?clipboard\b", lowered):
        return await _run("clipboard_read", mac_control.get_clipboard)

    if re.search(r"\bwhere am i\b|\bmy location\b|\bdefault location\b", lowered):
        location = profile.get_default_location()
        if location:
            return LocalRouteResult(f"Your default local location is {location}.", "default_location")
        return LocalRouteResult("I do not have a default location saved yet.", "default_location")

    url_match = re.search(r"\bopen\s+(https?://\S+|www\.\S+|[a-z0-9.-]+\.[a-z]{2,}(?:/\S*)?)\b", raw, re.IGNORECASE)
    if url_match:
        url = url_match.group(1)
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return await _run("open_url", mac_control.open_url, url)

    app_match = re.fullmatch(r"(?:open|launch|start)\s+([a-zA-Z][\w .+-]{1,50})", raw, re.IGNORECASE)
    if app_match and not re.search(r"\b(?:file|folder|project|repo|website|url)\b", lowered):
        return await _run("open_application", mac_control.open_application, app_match.group(1).strip())

    return None
