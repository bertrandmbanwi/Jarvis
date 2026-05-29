"""Deterministic local-first routing for cheap, common assistant actions."""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from jarvis.core import feedback, profile
from jarvis.core.cache import tool_cache
from jarvis.tools import mac_control, public_data, weather


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


async def _run_cached(
    action: str,
    tool_name: str,
    tool_input: dict,
    fn: Callable[..., Awaitable[str]],
    *args,
) -> LocalRouteResult:
    cached = await tool_cache.get(tool_name, tool_input)
    if cached is not None:
        return LocalRouteResult(response=str(cached), action=action)
    response = await fn(*args)
    await tool_cache.put(tool_name, tool_input, response)
    return LocalRouteResult(response=response, action=action)


def _extract_country_code(text: str) -> str:
    lowered = text.lower()
    direct_aliases = {
        "uk": "GB",
        "u.k.": "GB",
        "united kingdom": "GB",
        "england": "GB",
        "us": "US",
        "u.s.": "US",
        "usa": "US",
        "united states": "US",
        "america": "US",
    }
    for alias, code in direct_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return code

    match = re.search(r"\b(?:in|for)\s+([a-zA-Z]{2})(?:\b|$)", text)
    if match:
        return match.group(1).upper()
    return "US"


def _extract_currency_conversion(text: str) -> tuple[float, str, str] | None:
    match = re.search(
        r"\b(?:convert\s+)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*([A-Za-z$]{1,12})\s+(?:to|into|in)\s+([A-Za-z$]{1,12})\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return amount, match.group(2), match.group(3)


def _extract_crypto_asset(text: str) -> str:
    crypto_pattern = r"\b(bitcoin|btc|ethereum|eth|solana|sol|cardano|ada|dogecoin|doge|xrp|ripple|polygon|matic|bnb)\b"
    if not re.search(r"\b(?:price|worth|value|trading at)\b", text, re.IGNORECASE):
        return ""
    match = re.search(crypto_pattern, text, re.IGNORECASE)
    return match.group(1) if match else ""


def _extract_country_fact_target(text: str) -> str:
    match = re.search(
        r"\b(?:capital|currency|currencies|language|languages|population)\s+(?:of|in)\s+([A-Za-z][A-Za-z .'-]{1,50})[?!.]?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return _clean(match.group(1).strip(" ?!."))
    match = re.search(r"\bcountry info(?:rmation)?\s+(?:for|on|about)\s+([A-Za-z][A-Za-z .'-]{1,50})", text, re.IGNORECASE)
    if match:
        return _clean(match.group(1).strip(" ?!."))
    return ""


def _extract_sec_target(text: str) -> str:
    match = re.search(r"\b(?:sec|edgar|filings?|10-k|10-q)\b.*?\b(?:for|of|on)\s+([A-Za-z0-9 .&-]{1,60})[?!.]?$", text, re.IGNORECASE)
    if match:
        return _clean(match.group(1).strip(" ?!."))
    match = re.search(r"\b([A-Z]{1,6})\s+(?:sec\s+)?filings?\b", text)
    if match:
        return match.group(1)
    return ""


def _extract_ip_address(text: str) -> str:
    match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    if match:
        return match.group(0)
    match = re.search(r"\b[0-9a-fA-F]{0,4}:[0-9a-fA-F:]{2,}\b", text)
    return match.group(0) if match else ""


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
        return await _run_cached("weather", "get_weather", {"location": location}, weather.get_weather, location)

    conversion = _extract_currency_conversion(raw)
    if conversion and re.search(r"\b(?:convert|currency|exchange|rate|usd|eur|gbp|dollar|euro|pound|yen)\b", lowered):
        amount, base, target = conversion
        return await _run_cached(
            "currency_conversion",
            "convert_currency",
            {"amount": amount, "from_currency": base, "to_currency": target},
            public_data.convert_currency,
            amount,
            base,
            target,
        )

    crypto_asset = _extract_crypto_asset(raw)
    if crypto_asset:
        return await _run_cached(
            "crypto_price",
            "get_crypto_price",
            {"asset": crypto_asset, "vs_currency": "usd"},
            public_data.get_crypto_price,
            crypto_asset,
            "usd",
        )

    if "holiday" in lowered or "business day" in lowered:
        country_code = _extract_country_code(raw)
        if re.search(r"\b(?:next|upcoming|nearest)\b", lowered):
            return await _run_cached(
                "next_public_holiday",
                "get_next_public_holiday",
                {"country_code": country_code},
                public_data.get_next_public_holiday,
                country_code,
            )
        if re.search(r"\b(?:is|are)\s+(?:today|tomorrow|[0-9]{4}-[0-9]{2}-[0-9]{2})\b", lowered):
            date_match = re.search(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b", lowered)
            if date_match:
                check_date = date_match.group(1)
            elif "tomorrow" in lowered:
                check_date = (datetime.now().date() + timedelta(days=1)).isoformat()
            else:
                check_date = ""
            return await _run_cached(
                "public_holiday_check",
                "is_public_holiday",
                {"country_code": country_code, "check_date": check_date},
                public_data.is_public_holiday,
                country_code,
                check_date,
            )
        year_match = re.search(r"\b(20\d{2})\b", lowered)
        year = int(year_match.group(1)) if year_match else None
        return await _run_cached(
            "public_holidays",
            "get_public_holidays",
            {"country_code": country_code, "year": year},
            public_data.get_public_holidays,
            country_code,
            year,
        )

    country_target = _extract_country_fact_target(raw)
    if country_target:
        return await _run_cached(
            "country_info",
            "get_country_info",
            {"country": country_target},
            public_data.get_country_info,
            country_target,
        )

    sec_target = _extract_sec_target(raw)
    if sec_target:
        return await _run_cached(
            "sec_filings",
            "get_sec_company_filings",
            {"ticker_or_cik": sec_target, "limit": 5},
            public_data.get_sec_company_filings,
            sec_target,
            5,
        )

    ip_address = _extract_ip_address(raw)
    if ip_address and re.search(r"\b(?:ip|where|locat|geo|network)\b", lowered):
        return await _run_cached(
            "ip_lookup",
            "lookup_ip",
            {"ip_address": ip_address},
            public_data.lookup_ip,
            ip_address,
        )

    if re.search(r"\b(?:spaceflight|rocket launch|space news)\b", lowered):
        return await _run_cached(
            "spaceflight_news",
            "get_spaceflight_news",
            {"query": "", "limit": 5},
            public_data.get_spaceflight_news,
            "",
            5,
        )

    if re.search(r"\b(?:bike share|bike-share|citybike|city bike)\b", lowered):
        city_match = re.search(r"\b(?:in|for|near)\s+([A-Za-z][A-Za-z .'-]{1,40})[?!.]?$", raw, re.IGNORECASE)
        city = _clean(city_match.group(1).strip(" ?!.")) if city_match else ""
        return await _run_cached(
            "citybike_networks",
            "get_citybike_networks",
            {"city": city, "country": "", "limit": 10},
            public_data.get_citybike_networks,
            city,
            "",
            10,
        )

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
