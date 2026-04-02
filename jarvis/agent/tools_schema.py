"""
JARVIS Tool Schemas for Claude Tool Use

Defines all available tools as JSON schemas that Claude can call natively.
Each tool has a name, description, and input_schema following Claude's tool_use format.

The TOOL_REGISTRY maps tool names to their async callable implementations.
The TOOL_SCHEMAS list is passed directly to Claude's API.
"""
import logging
from jarvis.tools import mac_control, shell, filesystem, screen, web_search, web_browse
from jarvis.tools import browser_agent, claude_code, chrome_extension, calendar_email, weather, notes_access
from jarvis.core import profile
from jarvis.agent import planner as _planner_module
from jarvis.agent import learning as _learning_module
from jarvis.core import proactive as _proactive_module
from jarvis.agent import coordinator as _coordinator_module

logger = logging.getLogger("jarvis.agent.tools_schema")

async def _chrome_extension_status() -> str:
    """Check if the Chrome extension is connected."""
    connected = chrome_extension.is_extension_connected()
    if connected:
        return (
            "Chrome extension is CONNECTED. You can use chrome_* tools for fast, "
            "direct DOM interaction in the user's real Chrome browser."
        )
    return (
        "Chrome extension is NOT connected. Use the Playwright-based tools "
        "(browse_web, browser_navigate, etc.) as fallback, or ask the user "
        "to install and enable the JARVIS Browser Bridge extension in Chrome."
    )

_active_planner: _planner_module.TaskPlanner | None = None


def set_active_planner(planner: _planner_module.TaskPlanner):
    """Register the active planner instance."""
    global _active_planner
    _active_planner = planner


async def _get_plan_status() -> str:
    """Get the current task plan status."""
    if _active_planner is None:
        return "Task planning system is not initialized."
    return _active_planner.get_plan_status()


async def _get_plan_history() -> str:
    """Get recent completed task plans."""
    if _active_planner is None:
        return "Task planning system is not initialized."
    plans = _active_planner.tracker.load_recent_plans(limit=5)
    if not plans:
        return "No completed plans in history."
    lines = [f"Recent plans ({len(plans)}):"]
    for p in plans:
        status = p.get("status", "unknown")
        goal = p.get("goal_summary", "No summary")
        total = len(p.get("subtasks", []))
        completed = sum(
            1 for s in p.get("subtasks", [])
            if s.get("status") in ("completed", "skipped")
        )
        lines.append(f"  [{status}] {goal} ({completed}/{total} steps)")
    return "\n".join(lines)


async def _cancel_active_plan() -> str:
    """Cancel the currently active task plan."""
    if _active_planner is None:
        return "Task planning system is not initialized."
    if _active_planner.tracker.active_plan is None:
        return "No active plan to cancel."
    plan_id = _active_planner.tracker.active_plan.plan_id
    goal = _active_planner.tracker.active_plan.goal_summary
    _active_planner.tracker.cancel_plan()
    return f"Plan '{goal}' ({plan_id}) has been cancelled."

_active_learning: _learning_module.LearningLoop | None = None


def set_active_learning(loop: _learning_module.LearningLoop):
    global _active_learning
    _active_learning = loop


def _get_learning_insights() -> str:
    """Get a summary of JARVIS's learning insights."""
    if _active_learning is None:
        return "Learning loop is not initialized."
    insights = _active_learning.get_insights_summary()
    lines = ["Learning Loop Insights:"]
    ps = insights.get("plan_stats", {})
    lines.append(
        f"  Plans executed: {ps.get('total_plans', 0)} "
        f"(success rate: {int(ps.get('success_rate', 0) * 100)}%)"
    )
    lines.append(f"  Tool profiles tracked: {insights.get('tool_count', 0)}")
    lines.append(f"  Total tool calls recorded: {insights.get('total_tool_calls', 0)}")

    unreliable = insights.get("unreliable_tools", [])
    if unreliable:
        lines.append(f"  Unreliable tools: {', '.join(unreliable)}")

    failures = insights.get("common_failures", [])
    if failures:
        lines.append("  Common failure patterns:")
        for f in failures[:3]:
            lines.append(f"    - {f['pattern']} ({f['count']}x)")

    return "\n".join(lines)


def _get_tool_reliability() -> str:
    """Get tool reliability scores."""
    if _active_learning is None:
        return "Learning loop is not initialized."
    report = _active_learning.get_tool_reliability_report()
    if not report:
        return "No tool execution data recorded yet."
    lines = ["Tool Reliability Report:"]
    # Sort by total calls (most used first)
    sorted_tools = sorted(
        report.values(), key=lambda t: t.get("total_calls", 0), reverse=True
    )
    for tool in sorted_tools[:20]:
        name = tool["name"]
        rate = int(tool.get("success_rate", 1.0) * 100)
        calls = tool.get("total_calls", 0)
        avg_dur = tool.get("avg_duration_s", 0.0)
        reliable = "OK" if tool.get("is_reliable", True) else "UNRELIABLE"
        lines.append(f"  {name}: {rate}% success ({calls} calls, avg {avg_dur:.1f}s) [{reliable}]")
    return "\n".join(lines)

_active_proactive: _proactive_module.ProactiveEngine | None = None


def set_active_proactive(engine: _proactive_module.ProactiveEngine):
    global _active_proactive
    _active_proactive = engine


async def _get_proactive_status() -> str:
    """Get the proactive suggestions engine status."""
    if _active_proactive is None:
        return "Proactive engine is not initialized."
    status = _active_proactive.get_status()
    lines = ["Proactive Suggestions Engine:"]
    lines.append(f"  Enabled: {status['enabled']}")
    lines.append(f"  Running: {status['running']}")
    lines.append(f"  Conversation active: {status['conversation_active']}")
    lines.append(f"  Seconds since interaction: {status['seconds_since_interaction']}")
    lines.append("  Categories:")
    for cat_name, cat_info in status["categories"].items():
        enabled_str = "ON" if cat_info["enabled"] else "OFF"
        lines.append(
            f"    {cat_name}: {enabled_str} "
            f"(check every {cat_info['interval_s']}s)"
        )
    return "\n".join(lines)


async def _set_proactive_setting(category: str = "", enabled: bool = True) -> str:
    """Enable or disable proactive suggestion categories."""
    if _active_proactive is None:
        return "Proactive engine is not initialized."
    if not category:
        # Toggle the entire engine
        _active_proactive.set_enabled(enabled)
        return f"Proactive engine {'enabled' if enabled else 'disabled'}."
    try:
        cat = _proactive_module.SuggestionCategory(category)
        _active_proactive.set_category_enabled(cat, enabled)
        return f"Proactive category '{category}' {'enabled' if enabled else 'disabled'}."
    except ValueError:
        valid = [c.value for c in _proactive_module.SuggestionCategory]
        return f"Unknown category: '{category}'. Valid categories: {valid}"

_active_coordinator: _coordinator_module.AgentCoordinator | None = None


def set_active_coordinator(coord: _coordinator_module.AgentCoordinator):
    global _active_coordinator
    _active_coordinator = coord


async def _get_agent_status() -> str:
    """Get multi-agent coordinator status and agent profiles."""
    if _active_coordinator is None:
        return "Multi-agent coordinator is not initialized."
    status = _active_coordinator.get_status()
    lines = ["Multi-Agent Coordinator:"]
    lines.append(f"  Parallel execution: {'ON' if status['parallel_enabled'] else 'OFF'}")
    lines.append(f"  Max parallel tasks: {status['max_parallel']}")
    lines.append(f"  Active tasks: {status['active_tasks']}")
    lines.append(f"  Total tasks executed: {status['total_executed']}")
    lines.append("  Agent profiles:")
    for name, agent in status["agents"].items():
        if agent["total_tasks"] > 0:
            lines.append(
                f"    {agent['display_name']}: "
                f"{agent['total_tasks']} tasks, "
                f"{int(agent['success_rate'] * 100)}% success, "
                f"avg {agent['avg_duration_s']}s"
            )
        else:
            lines.append(f"    {agent['display_name']}: no tasks yet")
    return "\n".join(lines)


async def _get_active_agents() -> str:
    """Get currently running agent tasks."""
    if _active_coordinator is None:
        return "Multi-agent coordinator is not initialized."
    active = _active_coordinator.get_active_agents()
    if not active:
        return "No agent tasks currently running."
    lines = [f"Active agent tasks ({len(active)}):"]
    for a in active:
        lines.append(
            f"  [{a['agent_type']}] {a['description']} "
            f"(running for {a['running_for_s']}s)"
        )
    return "\n".join(lines)


async def _get_system_health() -> str:
    """Get JARVIS system health report with circuit breaker status."""
    from jarvis.core.hardening import get_health_report
    report = get_health_report()
    lines = ["System Health Report:"]

    lines.append("  Circuit Breakers:")
    for name, cb in report["circuit_breakers"].items():
        state = cb["state"].upper()
        failures = cb["failure_count"]
        lines.append(f"    {name}: {state} ({failures} failures)")

    t = report["tool_timeouts"]
    lines.append(
        f"  Tool Timeouts: {t['custom_timeout_count']} custom, "
        f"default {t['default_timeout_s']}s"
    )

    il = report["input_limits"]
    lines.append(
        f"  Input Limits: user={il['max_user_input']}, "
        f"tool_arg={il['max_tool_arg']}, path={il['max_file_path']}"
    )

    return "\n".join(lines)


async def _get_perf_stats() -> str:
    """Get performance metrics and latency data."""
    from jarvis.core.perf import perf_tracker
    stats = perf_tracker.get_stats()
    lines = ["Performance Metrics:"]

    req = stats["requests"]
    lines.append(
        f"  Requests: {req['total']} total, "
        f"avg latency {req['avg_latency_s']}s"
    )

    if stats["tier_usage"]:
        lines.append("  Tier Usage:")
        for tier, data in stats["tier_usage"].items():
            lines.append(
                f"    {tier}: {data['count']} calls, "
                f"avg {data['avg_s']}s, {data['downgrades']} downgrades"
            )

    if stats["operations"]:
        lines.append("  Top Operations (by total time):")
        for name, data in list(stats["operations"].items())[:8]:
            lines.append(
                f"    {name}: {data['count']}x, "
                f"avg {data['avg_s']}s, p90 {data['p90_s']}s"
            )

    if stats["bottlenecks"]:
        lines.append("  Bottlenecks:")
        for b in stats["bottlenecks"]:
            lines.append(
                f"    {b['operation']}: avg {b['avg_s']}s "
                f"({b['suggestion']})"
            )

    return "\n".join(lines)


async def _get_cache_stats() -> str:
    """Get tool result cache statistics."""
    from jarvis.core.cache import tool_cache
    stats = tool_cache.get_stats()
    lines = ["Tool Cache Statistics:"]
    lines.append(
        f"  Entries: {stats['total_entries']}/{stats['max_size']}"
    )
    lines.append(
        f"  Hit Rate: {stats['hit_rate_pct']}% "
        f"({stats['hits']} hits, {stats['misses']} misses)"
    )
    lines.append(f"  Evictions: {stats['evictions']}")
    lines.append(f"  Bypasses: {stats['bypasses']}")

    if stats["per_tool"]:
        lines.append("  Cached Tools:")
        for tool, data in stats["per_tool"].items():
            lines.append(
                f"    {tool}: {data['entries']} entries, "
                f"{data['total_hits']} hits, TTL {data['ttl_s']}s"
            )

    return "\n".join(lines)


async def _clear_cache(tool_name: str = "") -> str:
    """Clear the tool result cache, all or specific tool."""
    from jarvis.core.cache import tool_cache
    if tool_name:
        await tool_cache.invalidate(tool_name)
        return f"Cache cleared for tool: {tool_name}"
    else:
        await tool_cache.invalidate()
        return "Entire tool cache cleared."


_active_memory = None


def set_active_memory(memory):
    """Register active memory store."""
    global _active_memory
    _active_memory = memory


async def _get_user_facts() -> str:
    """Get all known facts about the user."""
    if _active_memory is None:
        return "Memory system is not initialized."
    facts = _active_memory.facts.get_all(min_confidence=0.3)
    if not facts:
        return "No facts known about the user yet. Facts are extracted from conversations over time."
    lines = [f"Known facts about the user ({len(facts)} total):"]
    for f in facts:
        conf = f"[{f.effective_confidence:.0%}]"
        lines.append(f"  {conf} {f.category}/{f.subject}: {f.value}")
    return "\n".join(lines)


async def _search_user_facts(query: str, category: str = "") -> str:
    """Search for specific facts about the user."""
    if _active_memory is None:
        return "Memory system is not initialized."
    facts = _active_memory.facts.search(query, category=category or None, limit=10)
    if not facts:
        return f"No facts found matching '{query}'."
    lines = [f"Facts matching '{query}':"]
    for f in facts:
        lines.append(f"  [{f.category}] {f.subject}: {f.value} ({f.effective_confidence:.0%} confidence)")
    return "\n".join(lines)


async def _forget_fact(subject: str) -> str:
    """Delete a specific fact by subject name."""
    if _active_memory is None:
        return "Memory system is not initialized."
    if _active_memory.facts.delete_fact(subject):
        return f"Fact '{subject}' has been forgotten."
    return f"No fact found with subject '{subject}'."


async def _get_user_patterns() -> str:
    """Get learned user behavior patterns and preferences."""
    if _active_memory is None:
        return "Memory system is not initialized."
    stats = _active_memory.preferences.get_stats()
    lines = ["Learned user patterns:"]

    topics = stats.get("top_topics", [])
    if topics:
        lines.append("  Top topics: " + ", ".join(f"{t[0]} ({t[1]:.1f})" for t in topics))

    tools = stats.get("top_tools", [])
    if tools:
        lines.append("  Top tools: " + ", ".join(f"{t[0]} ({t[1]:.1f})" for t in tools))

    hours = stats.get("active_hours", [])
    if hours:
        lines.append(f"  Active hours: {', '.join(f'{h}:00' for h in hours)}")

    detail = stats.get("detail_preference", "balanced")
    lines.append(f"  Detail preference: {detail}")
    lines.append(f"  Total patterns tracked: {stats.get('total_patterns', 0)}")

    return "\n".join(lines)


async def _get_memory_stats() -> str:
    """Get comprehensive memory system statistics."""
    if _active_memory is None:
        return "Memory system is not initialized."
    stats = _active_memory.get_stats()
    lines = ["Memory System Statistics:"]

    vs = stats.get("vector_store", {})
    lines.append(f"  Vector Store: {vs.get('backend', 'unknown')} ({vs.get('count', 0)} entries)")

    fs = stats.get("facts", {})
    lines.append(f"  Facts: {fs.get('total_facts', 0)} total, {fs.get('high_confidence', 0)} high-confidence")
    by_cat = fs.get("by_category", {})
    if by_cat:
        lines.append("    By category: " + ", ".join(f"{k}={v}" for k, v in by_cat.items()))

    ps = stats.get("preferences", {})
    lines.append(f"  Preferences: {ps.get('total_patterns', 0)} patterns tracked")

    return "\n".join(lines)
TOOL_SCHEMAS = [
    # ---- macOS Application Control ----
    {
        "name": "open_application",
        "description": (
            "Open a macOS application by name. Use the exact macOS app name "
            "(e.g., 'Safari', 'Google Chrome', 'Firefox', 'Visual Studio Code', "
            "'Terminal', 'Finder', 'Slack', 'Spotify'). "
            "If the user says a shorthand like 'chrome', use 'Google Chrome'. "
            "If they say 'vscode' or 'code', use 'Visual Studio Code'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "The macOS application name (e.g., 'Safari', 'Google Chrome', 'Firefox')",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "close_application",
        "description": "Close (quit) a running macOS application by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "The macOS application name to close",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "get_running_applications",
        "description": "List all currently running (non-background) macOS applications.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_frontmost_application",
        "description": "Get the name of the currently focused/frontmost macOS application.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- URLs and Browser ----
    {
        "name": "open_url",
        "description": "Open a URL in the user's default web browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to open (include https://)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "open_url_in_browser",
        "description": (
            "Open a URL in a browser application. Defaults to Google Chrome. "
            "Use this when the user wants to open a URL visually in a browser window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to open (include https://)",
                },
                "browser": {
                    "type": "string",
                    "description": "Browser app name: 'Google Chrome', 'Safari', 'Firefox', 'Microsoft Edge', 'Brave Browser'",
                    "default": "Google Chrome",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "search_in_browser",
        "description": (
            "Open a DuckDuckGo search in a specific browser so the user can see results visually. "
            "Use this when the user wants to search AND see results in their browser. "
            "For background data retrieval (weather, facts), use search_web or search_and_read instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "browser": {
                    "type": "string",
                    "description": "Browser app name: 'Google Chrome', 'Safari', 'Firefox'",
                    "default": "Google Chrome",
                },
            },
            "required": ["query"],
        },
    },
    # ---- System Information ----
    {
        "name": "get_system_info",
        "description": "Get system information: CPU, memory, available disk space, battery, and uptime.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_battery_status",
        "description": "Get battery percentage and charging status.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- System Controls ----
    {
        "name": "set_volume",
        "description": "Set the system audio volume. Use 0 for mute, 100 for maximum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level from 0 (mute) to 100 (max)",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": ["level"],
        },
    },
    {
        "name": "set_brightness",
        "description": "Set the display brightness level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Brightness level from 0 (dark) to 100 (max)",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": ["level"],
        },
    },
    {
        "name": "send_notification",
        "description": "Send a macOS desktop notification with a title and message.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Notification title",
                },
                "message": {
                    "type": "string",
                    "description": "Notification body text",
                },
            },
            "required": ["title", "message"],
        },
    },
    # ---- Clipboard ----
    {
        "name": "get_clipboard",
        "description": "Read the current contents of the macOS clipboard (what was last copied).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "set_clipboard",
        "description": "Set the macOS clipboard to the specified text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to copy to the clipboard",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "paste_to_app",
        "description": (
            "Paste text into a macOS application. Sets the clipboard and sends Cmd+V "
            "via System Events. Optionally creates a new document first (Cmd+N). "
            "Use this when the user wants to put text into Sublime Text, TextEdit, "
            "Notes, VS Code, or any other text editor. Requires Accessibility permissions. "
            "Preferred over manually chaining set_clipboard + run_command with osascript."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text content to paste into the app",
                },
                "app_name": {
                    "type": "string",
                    "description": "Target application name (e.g., 'Sublime Text', 'TextEdit', 'Notes')",
                },
                "new_document": {
                    "type": "boolean",
                    "description": "Create a new document/tab first with Cmd+N (default: true)",
                    "default": True,
                },
            },
            "required": ["text", "app_name"],
        },
    },
    {
        "name": "write_to_app",
        "description": (
            "Type text into a macOS application keystroke by keystroke using System Events. "
            "Alternative to paste_to_app for apps where clipboard paste is unreliable. "
            "Best for short text under 500 characters. For longer text, use paste_to_app. "
            "Requires Accessibility permissions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to type (keep under 500 chars for reliability)",
                },
                "app_name": {
                    "type": "string",
                    "description": "Target application name",
                },
                "new_document": {
                    "type": "boolean",
                    "description": "Create a new document/tab first with Cmd+N (default: true)",
                    "default": True,
                },
            },
            "required": ["text", "app_name"],
        },
    },
    # ---- File System ----
    {
        "name": "list_directory",
        "description": (
            "List files and folders in a directory. Common paths: ~/Desktop, ~/Documents, "
            "~/Downloads, ~/Pictures, ~/Music. Use '~' for the home directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (e.g., '~/Desktop', '~/Downloads')",
                },
                "detailed": {
                    "type": "boolean",
                    "description": "Whether to show detailed file info (size, date) or just names",
                    "default": True,
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read and return the text content of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write text content to a file. Creates the file if it does not exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search for files by name pattern in a directory. "
            "Use glob patterns like '*.py' or '*report*'. "
            "Only use this for LOCAL file searches, not web searches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory to search in (e.g., '~/Documents')",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match (e.g., '*.pdf', '*report*')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 20,
                },
            },
            "required": ["directory", "pattern"],
        },
    },
    {
        "name": "move_file",
        "description": "Move or rename a file or folder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Current path of the file or folder",
                },
                "destination": {
                    "type": "string",
                    "description": "New path for the file or folder",
                },
            },
            "required": ["source", "destination"],
        },
    },
    {
        "name": "copy_file",
        "description": "Copy a file or folder to a new location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Path of the file or folder to copy",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path",
                },
            },
            "required": ["source", "destination"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a new directory (folder).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the directory to create",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_file_info",
        "description": "Get metadata about a file: size, modification date, type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "open_file",
        "description": "Open a file with its default macOS application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to open",
                },
            },
            "required": ["file_path"],
        },
    },
    # ---- Screen ----
    {
        "name": "capture_screen",
        "description": "Take a screenshot of the current screen. Returns the path to the saved image.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "read_screen_text",
        "description": "Read text visible on the current screen using OCR (optical character recognition).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "analyze_screen",
        "description": (
            "Capture a screenshot and analyze it with AI vision. "
            "Use when the user asks 'what am I looking at?', 'what's on my screen?', "
            "'can you see this?', or needs visual context about their current activity. "
            "Optionally pass a question to ask about the screen content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Optional question about the screen content. E.g. 'What app is in the foreground?' or 'Is there an error message visible?'",
                },
            },
        },
    },
    # ---- Shell ----
    {
        "name": "run_command",
        "description": (
            "Execute a shell command in the macOS terminal and return its output. "
            "Use for tasks like checking git status, running scripts, listing processes, etc. "
            "DANGEROUS: do not run destructive commands (rm -rf, sudo, etc.) without explicit user confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
            },
            "required": ["command"],
        },
    },
    # ---- Web Search ----
    {
        "name": "search_web",
        "description": (
            "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. "
            "Use this for general information lookup, finding websites, or answering factual questions. "
            "The user will NOT see these results visually; use search_in_browser if they want to browse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_news",
        "description": "Search for recent news articles using DuckDuckGo News.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "News search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_and_read",
        "description": (
            "Search the web and automatically fetch content from the top result. "
            "Best for questions where you need actual data (weather, facts, stats, scores) "
            "rather than just links. Returns both search results and page content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        },
    },
    # ---- Weather ----
    {
        "name": "get_weather",
        "description": (
            "Get current weather and tomorrow's forecast for any location. "
            "Uses Open-Meteo API (free, no API key needed). "
            "Provide a city name or zip code. Returns temperature, conditions, "
            "humidity, wind speed, and precipitation chance in a speech-friendly format."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name (e.g., 'New York', 'San Francisco') or zip code (e.g., '90210')",
                },
            },
            "required": ["location"],
        },
    },
    # ---- Web Page Reading ----
    {
        "name": "fetch_page_text",
        "description": (
            "Fetch and extract readable text from a specific web page URL. "
            "Use when you already have a URL and want to read its content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch and read",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to extract",
                    "default": 5000,
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "fetch_page_links",
        "description": "Fetch and list all links found on a web page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch links from",
                },
                "max_links": {
                    "type": "integer",
                    "description": "Maximum number of links to return",
                    "default": 20,
                },
            },
            "required": ["url"],
        },
    },
    # ---- Browser Automation (Claude Computer Use) ----
    {
        "name": "browse_web",
        "description": (
            "Open a real browser and complete a multi-step web task autonomously using AI vision. "
            "The browser is visible to the user. Use this for tasks that require interacting with "
            "web pages: filling forms, clicking buttons, navigating multi-page flows, applying to "
            "jobs, downloading files, logging into websites, or any task that needs a real browser. "
            "Provide a clear task description and optionally a starting URL. "
            "Do NOT use this for simple searches or reading pages; use search_web or fetch_page_text instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Natural language description of what to accomplish in the browser. "
                        "Be specific about steps, e.g., 'Go to linkedin.com, search for "
                        "software engineer jobs in NYC, and apply to the first 3 results'"
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "Optional starting URL to navigate to before beginning the task",
                    "default": "",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "browser_navigate",
        "description": (
            "Navigate the automation browser to a specific URL and return a screenshot of the "
            "loaded page. You will SEE the actual page content, so you can verify whether it "
            "loaded correctly (catch 404 errors, login walls, CAPTCHAs, etc.). "
            "For complex multi-step tasks (filling forms, clicking buttons), use browse_web instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to (include https://)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": (
            "Take a screenshot of the current browser page and return the actual image. "
            "You will SEE what is on the screen. Use this to visually inspect the browser, "
            "verify page content, check for errors, or see the result of previous actions. "
            "This gives you eyes on the browser."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_browser_state",
        "description": (
            "Get a full overview of the browser: all open tabs (with URLs), which tab is active, "
            "the page title, and a screenshot of the current view. Use this when you need to see "
            "what is open in the browser, check on previously opened pages, or decide which tab "
            "to work with."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "browser_switch_tab",
        "description": (
            "Switch to a different browser tab by number (1-based). Use get_browser_state first "
            "to see which tabs are open and their numbers. Returns a screenshot of the new active tab."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tab_number": {
                    "type": "integer",
                    "description": "Tab number to switch to (1-based, as shown by get_browser_state)",
                },
            },
            "required": ["tab_number"],
        },
    },
    {
        "name": "browser_upload_file",
        "description": (
            "Upload a file to a file input on the current page. Use this for uploading resumes, "
            "cover letters, documents, images, or any file that a web form requires. Navigate to "
            "the page with the upload form first, then call this with the file path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to upload (e.g., ~/Documents/resume.pdf)",
                },
                "selector": {
                    "type": "string",
                    "description": (
                        "CSS selector of the file input element. Leave empty to automatically "
                        "find the first file input on the page."
                    ),
                    "default": "",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "sync_browser_sessions",
        "description": (
            "Sync login sessions from the user's real Chrome browser into JARVIS's "
            "automation browser. This imports cookies so Playwright inherits existing "
            "login sessions (Google, GitHub, LinkedIn, etc.) without the user needing "
            "to log in again. Call this before browse_web if the user mentions needing "
            "to be logged in, or if a site requires authentication."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domains": {
                    "type": "string",
                    "description": (
                        "Optional comma-separated list of domains to sync "
                        "(e.g., 'github.com,google.com'). If empty, syncs all "
                        "common domains automatically."
                    ),
                    "default": "",
                },
            },
        },
    },
    {
        "name": "close_browser",
        "description": "Close the automation browser when done with web tasks to free resources.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- Claude Code (Development Tasks) ----
    {
        "name": "run_claude_code",
        "description": (
            "Delegate a coding task to Claude Code, an AI coding agent that can read, write, "
            "and edit files, run commands, and reason about code. Use this for complex development "
            "tasks like: writing new code, debugging, refactoring, code review, creating scripts, "
            "setting up configurations, or any multi-step programming work. "
            "Claude Code has full filesystem and shell access in its working directory. "
            "Use continue_session=true to maintain context from the previous coding interaction. "
            "For simple one-off shell commands, use run_command instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Natural language description of the coding task. Be specific. "
                        "Examples: 'Create a Python Flask API with /health and /users endpoints', "
                        "'Find and fix the bug in src/auth.py where login fails for OAuth users'"
                    ),
                },
                "working_directory": {
                    "type": "string",
                    "description": "Directory to work in (e.g., '~/projects/my-app'). Defaults to home.",
                    "default": "",
                },
                "allowed_tools": {
                    "type": "string",
                    "description": "Comma-separated Claude Code tools to allow (e.g., 'Bash,Read,Write,Edit'). Leave empty for defaults.",
                    "default": "",
                },
                "continue_session": {
                    "type": "boolean",
                    "description": "Continue the previous Claude Code session for multi-turn coding work. Maintains full context.",
                    "default": False,
                },
                "session_name": {
                    "type": "string",
                    "description": "Named session to resume (e.g., 'my-api-project'). For persistent context across separate interactions.",
                    "default": "",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "run_terminal_command_smart",
        "description": (
            "Run a terminal command via Claude Code with intelligent safety checks. "
            "Unlike run_command (which executes directly), this routes through Claude Code "
            "so it can warn about destructive operations and chain follow-up steps. "
            "Use for commands that might need judgment or multi-step reasoning."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "Shell command or natural language description. "
                        "Can be exact ('git status') or descriptive ('check which ports are in use')."
                    ),
                },
                "working_directory": {
                    "type": "string",
                    "description": "Directory to run in",
                    "default": "",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "scaffold_project",
        "description": (
            "Create a new software project from scratch using Claude Code. "
            "Generates directory structure, boilerplate, config files, README, "
            "and starter code. Use when the user asks to create or scaffold a new project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "What kind of project to create. "
                        "Examples: 'Next.js app with TypeScript and Tailwind', "
                        "'Python FastAPI microservice with Docker and tests'"
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": "Where to create it (e.g., '~/projects/my-app'). Optional.",
                    "default": "",
                },
                "language": {
                    "type": "string",
                    "description": "Primary language/framework hint (e.g., 'python', 'typescript'). Optional.",
                    "default": "",
                },
            },
            "required": ["description"],
        },
    },
    # ---- Chrome Extension (Direct DOM Browser Control) ----
    # These tools use the JARVIS Chrome Extension for direct DOM access in the
    # user's real Chrome browser. They are faster, cheaper, and more reliable
    # than the Playwright + Computer Use tools above, because they interact with
    # the DOM directly instead of using vision-based screenshot analysis.
    #
    # PREFER these chrome_* tools over browse_web/browser_* when the Chrome
    # extension is connected. Fall back to Playwright tools if it is not.
    {
        "name": "chrome_navigate",
        "description": (
            "Navigate a tab in the user's real Chrome browser to a URL. "
            "Uses the Chrome extension for direct control (no Playwright). "
            "The user's actual login sessions are available automatically. "
            "Prefer this over browser_navigate when the Chrome extension is connected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to navigate to (include https://)",
                },
                "tab_id": {
                    "type": "integer",
                    "description": "Optional tab ID. If omitted, uses the active tab.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "chrome_click",
        "description": (
            "Click an element in the user's Chrome browser by CSS selector or visible text. "
            "Finds the element, scrolls it into view, and clicks it. Much faster and more "
            "reliable than vision-based clicking. Use selector for precise targeting or text "
            "for human-readable targeting (e.g., text='Sign In')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector (e.g., 'button.submit', '#login-btn', 'a[href=\"/about\"]')",
                    "default": "",
                },
                "text": {
                    "type": "string",
                    "description": "Visible text to find and click (e.g., 'Sign In', 'Next', 'Submit')",
                    "default": "",
                },
                "index": {
                    "type": "integer",
                    "description": "If multiple elements match, click the Nth one (0-based). Default: 0",
                    "default": 0,
                },
            },
        },
    },
    {
        "name": "chrome_type",
        "description": (
            "Type text into an input field in Chrome. Finds the element by CSS selector, "
            "focuses it, and types the text. Set clear=true to clear existing content first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the input element (e.g., '#email', 'input[name=\"search\"]')",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type into the field",
                },
                "clear": {
                    "type": "boolean",
                    "description": "Clear the field before typing. Default: false",
                    "default": False,
                },
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "chrome_read_page",
        "description": (
            "Read the text content and links from the active Chrome tab. "
            "Extracts visible text from the DOM directly (no OCR needed). "
            "Much faster and more complete than screenshot + OCR. "
            "Use this to understand what is on a page before interacting with it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Output format: 'text' for readable text + links, 'html' for raw HTML",
                    "default": "text",
                },
            },
        },
    },
    {
        "name": "chrome_find_elements",
        "description": (
            "Find elements on the active Chrome page matching a CSS selector or text. "
            "Returns a list of matching elements with their tag, text, href, and visibility. "
            "Use this to discover interactive elements before clicking or typing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector to search for (e.g., 'a', 'button', '.menu-item')",
                    "default": "",
                },
                "text": {
                    "type": "string",
                    "description": "Visible text to search for",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return. Default: 10",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "chrome_screenshot",
        "description": (
            "Take a screenshot of the active Chrome tab using Chrome's native capture API. "
            "Returns the actual image so you can SEE what is on the page. "
            "This captures the user's real Chrome window (with all their extensions, themes, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "chrome_get_tabs",
        "description": (
            "List all open tabs in the user's Chrome browser with their IDs, URLs, and titles. "
            "Use this to find specific tabs or get an overview of what the user has open."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "chrome_execute_js",
        "description": (
            "Execute JavaScript code in the active Chrome tab. Runs in the page's context "
            "with full access to the page's DOM and JavaScript. Use for advanced interactions "
            "that are not covered by other chrome_* tools. Returns the stringified result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "JavaScript code to execute (e.g., 'document.title', 'document.querySelector(\"#app\").textContent')",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "chrome_fill_form",
        "description": (
            "Fill multiple form fields at once in Chrome. Takes a mapping of CSS selectors "
            "to values and fills them all. Handles text inputs, selects, checkboxes, and radio buttons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": (
                        "Object mapping CSS selectors to values. "
                        "Example: {\"#email\": \"user@example.com\", \"#password\": \"secret\", \"#remember\": true}"
                    ),
                },
            },
            "required": ["fields"],
        },
    },
    {
        "name": "chrome_scroll",
        "description": (
            "Scroll the active Chrome tab in a direction. "
            "Use when you need to see more content on the page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "Scroll direction: 'up', 'down', 'left', or 'right'",
                    "default": "down",
                },
                "amount": {
                    "type": "integer",
                    "description": "Scroll amount (1=small, 3=medium, 5=large). Default: 3",
                    "default": 3,
                },
            },
        },
    },
    {
        "name": "chrome_extension_status",
        "description": (
            "Check whether the JARVIS Chrome Extension is currently connected. "
            "Call this before using any chrome_* tools to verify the extension is available. "
            "If not connected, fall back to the browse_web/browser_* tools (Playwright)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- User Profile ----
    {
        "name": "get_user_profile",
        "description": (
            "Get the user's full profile including name, preferred browser, "
            "timezone, custom preferences, shortcuts, and saved notes. "
            "Use this to recall user preferences before taking actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "update_user_profile",
        "description": (
            "Update a user profile field or preference. Use this when the user says "
            "'remember that...', 'my preferred X is Y', 'set my default...', etc. "
            "Known fields: name, preferred_address, preferred_browser, "
            "preferred_search_engine, timezone. Any other key is stored as a custom preference."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The profile field or preference name to update",
                },
                "value": {
                    "type": "string",
                    "description": "The new value",
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "get_user_preference",
        "description": (
            "Look up a single user preference by key. "
            "Use this to check a specific setting before acting on it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The preference key to look up",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "add_user_note",
        "description": (
            "Save a note to the user's profile. Use when the user says "
            "'remind me that...', 'note that...', 'save this...', or "
            "wants to store a piece of information for later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The text to save as a note",
                },
            },
            "required": ["note"],
        },
    },

    # ---- Task Plan Management ----
    {
        "name": "get_plan_status",
        "description": (
            "Check the status of the active task plan. Shows which subtasks "
            "are completed, in progress, pending, or failed. Use when the user "
            "asks 'what's the progress?', 'how's the plan going?', or "
            "'what step are you on?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_plan_history",
        "description": (
            "View recent completed task plans. Shows past multi-step tasks "
            "that JARVIS has executed, their outcomes, and step counts. "
            "Use when the user asks about past tasks or wants to review "
            "what JARVIS has done recently."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "cancel_active_plan",
        "description": (
            "Cancel the currently running task plan. Use ONLY when the user "
            "explicitly asks to stop, cancel, or abort the current multi-step "
            "task. Do not use for simple task cancellation or conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- Learning Loop ----
    {
        "name": "get_learning_insights",
        "description": (
            "Get a summary of JARVIS's learning loop insights, including plan "
            "success rates, tool reliability, and common failure patterns. Use "
            "when the user asks about how well JARVIS is performing, what it "
            "has learned, or to diagnose recurring issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_tool_reliability",
        "description": (
            "Get reliability scores for all tools JARVIS has used, including "
            "success rates, average durations, and flags for unreliable tools. "
            "Use when diagnosing tool failures or when asked about tool performance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- Calendar.app ----
    {
        "name": "get_upcoming_events",
        "description": (
            "Get upcoming calendar events from macOS Calendar.app. "
            "Returns event titles, times, locations, and calendars. "
            "Use when the user asks about their schedule, upcoming meetings, "
            "or what they have planned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead (1-14, default 1)",
                },
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Create a new event in macOS Calendar.app. "
            "Use when the user asks to schedule, add, or create a meeting, "
            "appointment, or event. Date format: 'March 25, 2026 2:00 PM'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title/summary",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date and time (e.g., 'March 25, 2026 2:00 PM')",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date and time (optional, defaults to 1 hour after start)",
                },
                "location": {
                    "type": "string",
                    "description": "Event location (optional)",
                },
                "notes": {
                    "type": "string",
                    "description": "Event notes/description (optional)",
                },
                "calendar_name": {
                    "type": "string",
                    "description": "Calendar name to add to (optional, uses default)",
                },
                "all_day": {
                    "type": "boolean",
                    "description": "Whether this is an all-day event (default false)",
                },
            },
            "required": ["title", "start_date"],
        },
    },
    {
        "name": "get_calendar_list",
        "description": (
            "List all calendars configured in macOS Calendar.app. "
            "Use to find which calendars are available before creating events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_calendar_events",
        "description": (
            "Search for calendar events by title within a date range. "
            "Use when the user asks to find a specific meeting or event."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text to match against event titles",
                },
                "days": {
                    "type": "integer",
                    "description": "Days to search ahead (1-90, default 30)",
                },
            },
            "required": ["query"],
        },
    },
    # ---- Mail.app ----
    {
        "name": "get_recent_emails",
        "description": (
            "Get recent emails from macOS Mail.app. Returns sender, subject, "
            "date, and a preview. Use when the user asks to check their email, "
            "inbox, or recent messages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent emails (1-25, default 10)",
                },
                "mailbox": {
                    "type": "string",
                    "description": "Mailbox name (default 'INBOX')",
                },
            },
        },
    },
    {
        "name": "get_unread_count",
        "description": (
            "Get the count of unread emails across all accounts in Mail.app. "
            "Use when the user asks 'do I have new mail?' or 'any unread emails?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "send_email",
        "description": (
            "Send an email via macOS Mail.app. Composes and sends immediately. "
            "IMPORTANT: Always confirm the recipient and content with the user "
            "before sending. Use when the user explicitly asks to send an email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address(es), comma-separated",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text",
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients (optional, comma-separated)",
                },
                "bcc": {
                    "type": "string",
                    "description": "BCC recipients (optional, comma-separated)",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "search_emails",
        "description": (
            "Search for emails by subject or sender in Mail.app. "
            "Use when the user asks to find a specific email or messages "
            "from a particular person."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text to match against subjects and senders",
                },
                "count": {
                    "type": "integer",
                    "description": "Max results (1-25, default 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_email",
        "description": (
            "Read the full content of a specific email by searching for its "
            "subject. Returns the complete email body, headers, and metadata. "
            "Use when the user wants to read or see a specific email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject_search": {
                    "type": "string",
                    "description": "Text to match against the email subject",
                },
            },
            "required": ["subject_search"],
        },
    },
    # ---- Proactive Suggestions Engine ----
    {
        "name": "get_proactive_status",
        "description": (
            "Get the status of the proactive suggestions engine, including "
            "which categories (calendar, email, greeting, reminder) are enabled, "
            "check intervals, and whether the engine is currently active. "
            "Use when the user asks about proactive suggestions or notifications."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "set_proactive_setting",
        "description": (
            "Enable or disable the proactive suggestions engine or specific "
            "categories. Categories: 'calendar' (meeting alerts), 'email' "
            "(unread notifications), 'greeting' (morning briefings), "
            "'reminder' (periodic reminders). Leave category empty to toggle "
            "the entire engine on or off."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Suggestion category to toggle: 'calendar', 'email', "
                        "'greeting', 'reminder'. Empty string to toggle the whole engine."
                    ),
                },
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable, False to disable",
                },
            },
            "required": ["enabled"],
        },
    },
    # ---- Multi-Agent Coordinator ----
    {
        "name": "get_agent_status",
        "description": (
            "Get the status of the multi-agent coordinator, including all "
            "specialized agent profiles (researcher, coder, browser, system, "
            "communicator, analyst), their task counts, success rates, and "
            "whether parallel execution is enabled. Use when the user asks "
            "about agents, multi-agent status, or parallel execution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_active_agents",
        "description": (
            "Get the list of currently running agent tasks. Shows which "
            "specialized agents are actively executing subtasks, including "
            "agent type, description, and how long they have been running. "
            "Use when the user asks what agents are currently doing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- System Health (Phase 6.1) ----
    {
        "name": "get_system_health",
        "description": (
            "Get the JARVIS system health report, including circuit breaker "
            "status for the Claude API and individual tools, timeout "
            "configuration, and input validation limits. Use when the user "
            "asks about system health, error rates, or reliability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # ---- Performance Metrics (Phase 6.2) ----
    {
        "name": "get_perf_stats",
        "description": (
            "Get JARVIS performance metrics: request latency, tier usage, "
            "per-operation timing, and bottleneck analysis. Use when the user "
            "asks about response times, performance, or speed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_cache_stats",
        "description": (
            "Get tool result cache statistics: hit rate, cached tools, "
            "entries, and eviction counts. Use when the user asks about "
            "caching, cache performance, or repeated tool calls."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "clear_cache",
        "description": (
            "Clear the tool result cache. Optionally clear only a specific "
            "tool's cached results. Use when the user asks to refresh data "
            "or reports stale results from a specific tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": (
                        "Optional: name of a specific tool to clear cache for. "
                        "If empty, clears all cached results."
                    ),
                },
            },
        },
    },
    # ---- Memory Management (Phase 6.3) ----
    {
        "name": "get_user_facts",
        "description": (
            "Get all known facts about the user (name, location, job, preferences, "
            "relationships, habits). Facts are automatically extracted from conversations "
            "over time. Use when the user asks what you know about them, or to check "
            "context before personalizing a response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_user_facts",
        "description": (
            "Search for specific facts about the user by keyword or category. "
            "Categories include: personal, work, preference, location, relationship, "
            "habit, explicit. Use when looking for specific user context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search for in facts.",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category filter: personal, work, preference, "
                        "location, relationship, habit, explicit."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "forget_fact",
        "description": (
            "Delete a specific fact from memory by its subject name. Use when "
            "the user asks you to forget something or when a fact is outdated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "The subject name of the fact to forget.",
                },
            },
            "required": ["subject"],
        },
    },
    {
        "name": "get_user_patterns",
        "description": (
            "Get learned behavior patterns: top topics, most-used tools, active "
            "hours, and detail preferences. Use when the user asks about their "
            "usage patterns or when tuning proactive suggestions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_memory_stats",
        "description": (
            "Get comprehensive memory system statistics: vector store size, "
            "fact counts by category, and preference patterns tracked. Use "
            "when the user asks about memory usage or system status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # Apple Notes tools
    {
        "name": "get_recent_notes",
        "description": "Get recent notes from Apple Notes. Returns a list of notes with title, folder, snippet, and modification date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent notes to return (default 10).",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_note",
        "description": "Read the full content of a specific note from Apple Notes by title (partial match supported).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title_match": {
                    "type": "string",
                    "description": "Title or partial title of the note to read.",
                },
            },
            "required": ["title_match"],
        },
    },
    {
        "name": "search_notes",
        "description": "Search Apple Notes by keyword. Searches across note titles and bodies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find in notes.",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 10).",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new note in Apple Notes. Supports plain text and markdown checklists (lines starting with '- [ ]' or '- [x]').",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title for the new note.",
                },
                "body": {
                    "type": "string",
                    "description": "Body content of the note. Supports markdown checklist format.",
                },
                "folder": {
                    "type": "string",
                    "description": "Folder to create the note in (default: 'Notes').",
                    "default": "Notes",
                },
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "get_note_folders",
        "description": "List all folders in Apple Notes.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


TOOL_REGISTRY = {
    "open_application": mac_control.open_application,
    "close_application": mac_control.close_application,
    "get_running_applications": mac_control.get_running_applications,
    "get_frontmost_application": mac_control.get_frontmost_application,
    "open_url": mac_control.open_url,
    "open_url_in_browser": mac_control.open_url_in_browser,
    "search_in_browser": mac_control.search_in_browser,
    "get_system_info": mac_control.get_system_info,
    "get_battery_status": mac_control.get_battery_status,
    "set_volume": mac_control.set_volume,
    "set_brightness": mac_control.set_brightness,
    "send_notification": mac_control.send_notification,
    "get_clipboard": mac_control.get_clipboard,
    "set_clipboard": mac_control.set_clipboard,
    "paste_to_app": mac_control.paste_to_app,
    "write_to_app": mac_control.write_to_app,
    # File system
    "list_directory": filesystem.list_directory,
    "read_file": filesystem.read_file,
    "write_file": filesystem.write_file,
    "search_files": filesystem.search_files,
    "move_file": filesystem.move_file,
    "copy_file": filesystem.copy_file,
    "create_directory": filesystem.create_directory,
    "get_file_info": filesystem.get_file_info,
    "open_file": mac_control.open_file,
    # Screen
    "capture_screen": screen.capture_screen,
    "read_screen_text": screen.read_screen_text,
    "analyze_screen": screen.analyze_screen,
    # Shell
    "run_command": shell.run_command,
    # Web search
    "search_web": web_search.search_web,
    "search_news": web_search.search_news,
    "search_and_read": web_search.search_and_read,
    # Weather
    "get_weather": weather.get_weather,
    # Web page reading
    "fetch_page_text": web_browse.fetch_page_text,
    "fetch_page_links": web_browse.fetch_page_links,
    # Browser automation (Claude Computer Use + Playwright)
    "browse_web": browser_agent.browse_web,
    "browser_navigate": browser_agent.browser_navigate,
    "browser_screenshot": browser_agent.browser_screenshot,
    "get_browser_state": browser_agent.get_browser_state,
    "browser_switch_tab": browser_agent.browser_switch_tab,
    "browser_upload_file": browser_agent.browser_upload_file,
    "sync_browser_sessions": browser_agent.sync_browser_sessions,
    "close_browser": browser_agent.close_browser,
    # Claude Code (development tasks)
    "run_claude_code": claude_code.run_claude_code,
    "run_terminal_command_smart": claude_code.run_terminal_command,
    "scaffold_project": claude_code.scaffold_project,
    # Chrome Extension (direct DOM browser control)
    "chrome_navigate": chrome_extension.chrome_navigate,
    "chrome_click": chrome_extension.chrome_click,
    "chrome_type": chrome_extension.chrome_type,
    "chrome_read_page": chrome_extension.chrome_read_page,
    "chrome_find_elements": chrome_extension.chrome_find_elements,
    "chrome_screenshot": chrome_extension.chrome_screenshot,
    "chrome_get_tabs": chrome_extension.chrome_get_tabs,
    "chrome_execute_js": chrome_extension.chrome_execute_js,
    "chrome_fill_form": chrome_extension.chrome_fill_form,
    "chrome_scroll": chrome_extension.chrome_scroll,
    "chrome_extension_status": _chrome_extension_status,
    # User Profile
    "get_user_profile": profile.get_user_profile,
    "update_user_profile": profile.update_user_profile,
    "get_user_preference": profile.get_user_preference,
    "add_user_note": profile.add_user_note,
    # Task Plan Management
    "get_plan_status": _get_plan_status,
    "get_plan_history": _get_plan_history,
    "cancel_active_plan": _cancel_active_plan,
    # Learning Loop
    "get_learning_insights": _get_learning_insights,
    "get_tool_reliability": _get_tool_reliability,
    # Calendar.app
    "get_upcoming_events": calendar_email.get_upcoming_events,
    "create_calendar_event": calendar_email.create_calendar_event,
    "get_calendar_list": calendar_email.get_calendar_list,
    "search_calendar_events": calendar_email.search_calendar_events,
    # Mail.app
    "get_recent_emails": calendar_email.get_recent_emails,
    "get_unread_count": calendar_email.get_unread_count,
    "send_email": calendar_email.send_email,
    "search_emails": calendar_email.search_emails,
    "read_email": calendar_email.read_email,
    # Proactive Suggestions
    "get_proactive_status": _get_proactive_status,
    "set_proactive_setting": _set_proactive_setting,
    # Multi-Agent Coordinator
    "get_agent_status": _get_agent_status,
    "get_active_agents": _get_active_agents,
    # System Health
    "get_system_health": _get_system_health,
    # Performance (Phase 6.2)
    "get_perf_stats": _get_perf_stats,
    "get_cache_stats": _get_cache_stats,
    "clear_cache": _clear_cache,
    # Memory Management (Phase 6.3)
    "get_user_facts": _get_user_facts,
    "search_user_facts": _search_user_facts,
    "forget_fact": _forget_fact,
    "get_user_patterns": _get_user_patterns,
    "get_memory_stats": _get_memory_stats,
    # Apple Notes (Phase 7: Notes Access)
    "get_recent_notes": notes_access.get_recent_notes,
    "read_note": notes_access.read_note,
    "search_notes": notes_access.search_notes,
    "create_note": notes_access.create_note,
    "get_note_folders": notes_access.get_note_folders,
}


def get_tool_names() -> list[str]:
    """Return all available tool names."""
    return list(TOOL_REGISTRY.keys())
