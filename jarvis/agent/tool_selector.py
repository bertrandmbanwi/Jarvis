"""Tool schema preparation: native tool search (OpenAI) or keyword pruning (fallback)."""
from __future__ import annotations

import re

COMMON_TOOLS = {
    "get_weather",
    "get_battery_status",
    "get_system_info",
    "get_running_applications",
    "get_frontmost_application",
    "open_application",
    "open_url",
    "get_user_profile",
    "use_skill",
}

TOOL_GROUPS: dict[str, set[str]] = {
    "weather": {"get_weather", "get_user_profile"},
    "currency_data": {"convert_currency"},
    "crypto_data": {"get_crypto_price"},
    "holiday_data": {"get_public_holidays", "get_next_public_holiday", "is_public_holiday"},
    "country_data": {"get_country_info"},
    "sec_data": {"get_sec_company_filings"},
    "ip_lookup": {"lookup_ip"},
    "spaceflight_data": {"get_spaceflight_news"},
    "citybike_data": {"get_citybike_networks"},
    "public_api_status": {"check_public_api_status"},
    "time_status": {"get_battery_status", "get_system_info", "get_running_applications", "get_frontmost_application"},
    "mac": {
        "open_application", "close_application", "open_url", "open_url_in_browser",
        "search_in_browser", "set_volume", "set_brightness", "send_notification",
        "get_clipboard", "set_clipboard", "paste_to_app", "write_to_app",
    },
    "files": {
        "list_directory", "read_file", "write_file", "search_files", "move_file",
        "copy_file", "create_directory", "get_file_info", "open_file",
    },
    "shell": {"run_command", "run_terminal_command_smart"},
    "web": {"search_web", "search_news", "search_and_read", "fetch_page_text", "fetch_page_links"},
    "browser": {
        "browse_web", "browser_navigate", "browser_screenshot", "get_browser_state",
        "browser_switch_tab", "browser_upload_file", "sync_browser_sessions", "close_browser",
        "chrome_navigate", "chrome_click", "chrome_type", "chrome_read_page",
        "chrome_find_elements", "chrome_screenshot", "chrome_get_tabs",
        "chrome_execute_js", "chrome_fill_form", "chrome_scroll", "chrome_extension_status",
    },
    "calendar_email": {
        "get_upcoming_events", "create_calendar_event", "get_calendar_list",
        "search_calendar_events", "get_recent_emails", "get_unread_count",
        "send_email", "search_emails", "read_email",
    },
    "memory": {
        "get_user_profile", "update_user_profile", "get_user_preference",
        "add_user_note", "get_user_facts", "search_user_facts", "forget_fact",
        "get_user_patterns", "get_memory_stats",
    },
    "notes": {"get_recent_notes", "read_note", "search_notes", "create_note", "get_note_folders"},
    "planning": {
        "get_plan_status", "get_plan_history", "cancel_active_plan",
        "get_learning_insights", "get_tool_reliability", "get_agent_status",
        "get_active_agents", "get_system_health", "get_perf_stats",
        "get_cache_stats", "clear_cache",
    },
    "development": {
        "run_coding_agent", "run_terminal_command_smart", "scaffold_project",
        "run_command", "list_directory", "read_file", "write_file",
        "search_files", "get_file_info", "search_web", "fetch_page_text",
    },
    "screen": {"capture_screen", "read_screen_text", "analyze_screen"},
    "proactive": {"get_proactive_status", "set_proactive_setting"},
    "skills": {"use_skill", "read_skill_file"},
}

KEYWORD_GROUPS: list[tuple[set[str], str]] = [
    ({"weather", "forecast", "temperature", "rain", "humidity"}, "weather"),
    ({"currency", "exchange rate", "convert", "usd", "eur", "gbp", "cad", "dollar", "euro", "pound", "yen"}, "currency_data"),
    ({"crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "dogecoin", "doge"}, "crypto_data"),
    ({"holiday", "business day"}, "holiday_data"),
    ({"country", "capital", "population", "language", "currency of"}, "country_data"),
    ({"sec", "edgar", "filing", "10-k", "10-q", "10k", "10q"}, "sec_data"),
    ({"ip address", "geolocate ip", "ip lookup"}, "ip_lookup"),
    ({"spaceflight", "space news", "rocket launch"}, "spaceflight_data"),
    ({"bike share", "bike-share", "citybike", "city bike"}, "citybike_data"),
    ({"public api", "free api status", "provider status"}, "public_api_status"),
    ({"battery", "system", "status", "running apps", "frontmost", "current app"}, "time_status"),
    ({"open", "launch", "close app", "volume", "brightness", "notification", "clipboard", "paste"}, "mac"),
    ({"file", "folder", "directory", "read", "write", "move", "copy", "project"}, "files"),
    ({"terminal", "command", "shell", "process", "script"}, "shell"),
    ({"search", "web", "website", "url", "news", "page", "read online", "lookup"}, "web"),
    ({"browser", "chrome", "tab", "click", "screenshot", "form"}, "browser"),
    ({"calendar", "meeting", "event", "email", "mail", "inbox"}, "calendar_email"),
    ({"remember", "profile", "preference", "memory", "fact", "forget"}, "memory"),
    ({"note", "notes"}, "notes"),
    ({"plan", "agent", "learning", "cache", "performance", "health"}, "planning"),
    ({"code", "build", "debug", "repo", "repository", "test", "implement", "fix"}, "development"),
    ({"screen", "display", "look at", "visible"}, "screen"),
    ({"proactive", "suggestion", "suggestions", "check-in", "check in", "nudge"}, "proactive"),
    ({"skill", "skills", "briefing", "prep"}, "skills"),
]


# How many recent conversation turns inform tool selection, so a follow-up like
# "yes, send it" still gets the email tools offered for the draft before it.
HISTORY_TURNS_FOR_SELECTION = 2


def _keyword_pattern(keywords: set[str]) -> re.Pattern[str]:
    # Whole words only: "sol" must not match "solve", nor "eth" match "method".
    alternatives = "|".join(sorted((re.escape(k) for k in keywords), key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\b")


_KEYWORD_PATTERNS = [(_keyword_pattern(keywords), group) for keywords, group in KEYWORD_GROUPS]


def _selection_text(text: str, history: list[dict] | None) -> str:
    recent = (history or [])[-HISTORY_TURNS_FOR_SELECTION * 2:]
    parts = [str(msg.get("content", "")) for msg in recent]
    parts.append(text)
    return " ".join(parts).lower()


def select_tools_for_request(
    text: str,
    all_schemas: list[dict],
    history: list[dict] | None = None,
) -> list[dict]:
    """Return only likely-needed tool schemas for a request (keyword-based)."""
    lowered = text.lower()

    if re.search(r"\b(?:all tools|full toolset|everything you can|any tool)\b", lowered):
        return all_schemas

    context = _selection_text(text, history)
    selected: set[str] = set(COMMON_TOOLS)
    for pattern, group in _KEYWORD_PATTERNS:
        if pattern.search(context):
            selected.update(TOOL_GROUPS[group])

    # MCP tools join when their server is mentioned ("search my notion for ...").
    for schema in all_schemas:
        server = schema.get("mcp_server")
        if server and re.search(rf"\b{re.escape(server.lower())}\b", context):
            selected.add(schema["name"])

    if len(selected) <= len(COMMON_TOOLS) and len(lowered) > 160:
        selected.update(TOOL_GROUPS["web"])
        selected.update(TOOL_GROUPS["files"])

    ordered = [schema for schema in all_schemas if schema.get("name") in selected]
    return ordered or all_schemas[: min(12, len(all_schemas))]


def with_deferred_loading(schemas: list[dict]) -> list[dict]:
    """Mark every non-core tool ``defer_loading`` for native tool search.

    The model sees each deferred tool's name and description and loads the
    full schema only when it needs it. The same schemas are sent in the same
    order on every request, which keeps the prompt cache valid (the keyword
    selector changed the tool set per request and invalidated it).
    """
    core = [s for s in schemas if s.get("name") in COMMON_TOOLS]
    # At least one tool must stay loaded or the API rejects the request.
    keep = {s["name"] for s in core} if core else {s["name"] for s in schemas[:3]}
    return [s if s.get("name") in keep else {**s, "defer_loading": True} for s in schemas]
