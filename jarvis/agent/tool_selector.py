"""Request-aware tool schema pruning to reduce Claude input tokens."""
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
}

TOOL_GROUPS: dict[str, set[str]] = {
    "weather": {"get_weather", "get_user_profile"},
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
        "run_claude_code", "run_terminal_command_smart", "scaffold_project",
        "run_command", "list_directory", "read_file", "write_file",
        "search_files", "get_file_info", "search_web", "fetch_page_text",
    },
    "screen": {"capture_screen", "read_screen_text", "analyze_screen"},
}

KEYWORD_GROUPS: list[tuple[set[str], str]] = [
    ({"weather", "forecast", "temperature", "rain", "humidity"}, "weather"),
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
]


def select_tools_for_request(text: str, all_schemas: list[dict]) -> list[dict]:
    """Return only likely-needed tool schemas for a request."""
    lowered = text.lower()

    if re.search(r"\b(?:all tools|full toolset|everything you can|any tool)\b", lowered):
        return all_schemas

    selected: set[str] = set(COMMON_TOOLS)
    for keywords, group in KEYWORD_GROUPS:
        if any(keyword in lowered for keyword in keywords):
            selected.update(TOOL_GROUPS[group])

    if len(selected) <= len(COMMON_TOOLS) and len(lowered) > 160:
        selected.update(TOOL_GROUPS["web"])
        selected.update(TOOL_GROUPS["files"])

    ordered = [schema for schema in all_schemas if schema.get("name") in selected]
    return ordered or all_schemas[: min(12, len(all_schemas))]
