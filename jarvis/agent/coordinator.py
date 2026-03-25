"""
JARVIS Multi-Agent Coordinator

Manages specialized agent profiles and coordinates parallel or sequential
execution of subtasks across multiple agents. Each agent profile has a
focused system prompt and a curated tool subset, making it more effective
at its specialty than a single general-purpose agent.

Agent Types:
    - researcher: Web search, page reading, information synthesis
    - coder: Shell commands, file I/O, Claude Code, scaffolding
    - browser: Chrome extension, Playwright, web navigation
    - system: macOS control, volume, brightness, apps, clipboard
    - communicator: Email, calendar, notifications
    - analyst: Screen capture, file reading, summarization (no tools, pure reasoning)
    - generalist: Full tool access (default fallback)

The coordinator enhances the existing TaskPlanner by:
1. Tagging each subtask with the best agent type during planning
2. Running independent subtasks in parallel when safe
3. Providing agent-specific system prompts to improve tool selection
4. Tracking per-agent execution metrics for the learning loop
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("jarvis.agent.coordinator")


class AgentType(str, Enum):
    """Specialized agent profiles for task routing."""
    RESEARCHER = "researcher"
    CODER = "coder"
    BROWSER = "browser"
    SYSTEM = "system"
    COMMUNICATOR = "communicator"
    ANALYST = "analyst"
    GENERALIST = "generalist"


@dataclass
class AgentProfile:
    """Configuration for a specialized agent."""
    agent_type: AgentType
    display_name: str
    system_prompt: str
    tool_names: list[str]
    description: str = ""
    total_tasks: int = 0
    successful_tasks: int = 0
    total_duration_s: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 1.0
        return self.successful_tasks / self.total_tasks

    @property
    def avg_duration_s(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_duration_s / self.total_tasks

    def to_dict(self) -> dict:
        return {
            "agent_type": self.agent_type.value,
            "display_name": self.display_name,
            "description": self.description,
            "tool_count": len(self.tool_names),
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "success_rate": round(self.success_rate, 2),
            "avg_duration_s": round(self.avg_duration_s, 2),
        }


@dataclass
class AgentTask:
    """Task assigned to a specific agent."""
    subtask_id: str
    agent_type: AgentType
    description: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_s: float = 0.0


_RESEARCHER_PROMPT = """\
You are JARVIS's Research Agent. Your specialty is finding, reading, and
synthesizing information from the web and local files.

Focus on:
- Searching the web for accurate, current information
- Reading and extracting key facts from web pages
- Cross-referencing multiple sources for accuracy
- Providing well-sourced, concise summaries

Always cite your sources. Prefer official documentation and primary sources.
Be thorough but concise. If information is uncertain, say so explicitly.
Address the user as 'sir'.
"""

_CODER_PROMPT = """\
You are JARVIS's Coding Agent. Your specialty is writing code, running
commands, managing files, and software development tasks.

Focus on:
- Writing clean, production-quality code
- Running shell commands safely (always validate before destructive ops)
- Reading and modifying files accurately
- Using Claude Code for complex development workflows
- Scaffolding new projects with proper structure

Follow best practices: error handling, input validation, security-first defaults.
Test your logic mentally before presenting solutions.
Address the user as 'sir'.
"""

_BROWSER_PROMPT = """\
You are JARVIS's Browser Agent. Your specialty is navigating and interacting
with web pages in the user's real browser.

Focus on:
- Using the Chrome extension tools for fast, direct DOM interaction
- Navigating to URLs, clicking elements, filling forms
- Reading page content and extracting structured data
- Taking screenshots for visual verification
- Managing browser tabs

Prefer chrome_* tools when the extension is connected. Fall back to
Playwright-based tools (browse_web, browser_navigate) if not.
Address the user as 'sir'.
"""

_SYSTEM_PROMPT = """\
You are JARVIS's System Agent. Your specialty is controlling the macOS
operating system, managing applications, and system settings.

Focus on:
- Opening, closing, and managing macOS applications
- System controls: volume, brightness, notifications
- Clipboard operations: copy, paste, write to apps
- Battery and system info queries
- File management: listing, reading, writing, moving files

Be careful with destructive operations. Always confirm before deleting
files or force-quitting applications.
Address the user as 'sir'.
"""

_COMMUNICATOR_PROMPT = """\
You are JARVIS's Communications Agent. Your specialty is managing email,
calendar events, and notifications.

Focus on:
- Reading and searching emails in Mail.app
- Composing and sending emails (always confirm recipient and content first)
- Managing calendar events in Calendar.app
- Sending macOS notifications
- Scheduling and reminders

For email: always double-check the recipient address and email content
before sending. Never send without explicit user confirmation.
Address the user as 'sir'.
"""

_ANALYST_PROMPT = """\
You are JARVIS's Analysis Agent. Your specialty is deep reasoning,
data analysis, comparison, and synthesis.

Focus on:
- Analyzing information from prior steps in a multi-step plan
- Comparing and contrasting data from multiple sources
- Generating summaries, reports, and recommendations
- Identifying patterns, trends, and insights
- Reviewing screen captures for visual analysis

You have access to screen capture and file reading tools for gathering data,
but your primary value is in reasoning and synthesis, not tool execution.
Address the user as 'sir'.
"""

_GENERALIST_PROMPT = """\
You are JARVIS, a personal AI assistant with access to all available tools.
You can handle any task: browsing, coding, system control, communication,
research, and analysis.

Use your full tool set as needed. For complex tasks, pick the right tools
for each step. Be efficient, accurate, and conversational.
Address the user as 'sir'.
"""


_AGENT_TOOLS: dict[AgentType, list[str]] = {
    AgentType.RESEARCHER: [
        "search_web", "search_news", "search_and_read", "get_weather",
        "fetch_page_text", "fetch_page_links",
        "read_file", "search_files",
        "capture_screen", "read_screen_text",
    ],
    AgentType.CODER: [
        "run_command", "run_claude_code", "run_terminal_command_smart",
        "scaffold_project",
        "read_file", "write_file", "list_directory", "search_files",
        "move_file", "copy_file", "create_directory", "get_file_info",
        "open_file",
        "get_clipboard", "set_clipboard",
    ],
    AgentType.BROWSER: [
        "chrome_navigate", "chrome_click", "chrome_type",
        "chrome_read_page", "chrome_find_elements", "chrome_screenshot",
        "chrome_get_tabs", "chrome_execute_js", "chrome_fill_form",
        "chrome_scroll", "chrome_extension_status",
        "browse_web", "browser_navigate", "browser_screenshot",
        "get_browser_state", "browser_switch_tab", "browser_upload_file",
        "sync_browser_sessions", "close_browser",
        "open_url", "open_url_in_browser", "search_in_browser",
    ],
    AgentType.SYSTEM: [
        "open_application", "close_application",
        "get_running_applications", "get_frontmost_application",
        "open_url", "open_url_in_browser",
        "get_system_info", "get_battery_status",
        "set_volume", "set_brightness", "send_notification",
        "get_clipboard", "set_clipboard", "paste_to_app", "write_to_app",
        "list_directory", "read_file", "write_file", "search_files",
        "move_file", "copy_file", "create_directory", "get_file_info",
        "open_file",
        "capture_screen", "read_screen_text",
        "run_command",
    ],
    AgentType.COMMUNICATOR: [
        "get_upcoming_events", "create_calendar_event",
        "get_calendar_list", "search_calendar_events",
        "get_recent_emails", "get_unread_count",
        "send_email", "search_emails", "read_email",
        "send_notification",
    ],
    AgentType.ANALYST: [
        "capture_screen", "read_screen_text",
        "read_file", "search_files", "list_directory",
        "fetch_page_text",
        "search_web", "search_and_read",
    ],
    AgentType.GENERALIST: [],
}


def _build_profiles() -> dict[AgentType, AgentProfile]:
    """Build agent profiles from prompts and tool assignments."""
    prompts = {
        AgentType.RESEARCHER: (_RESEARCHER_PROMPT, "Research Agent"),
        AgentType.CODER: (_CODER_PROMPT, "Coding Agent"),
        AgentType.BROWSER: (_BROWSER_PROMPT, "Browser Agent"),
        AgentType.SYSTEM: (_SYSTEM_PROMPT, "System Agent"),
        AgentType.COMMUNICATOR: (_COMMUNICATOR_PROMPT, "Communications Agent"),
        AgentType.ANALYST: (_ANALYST_PROMPT, "Analysis Agent"),
        AgentType.GENERALIST: (_GENERALIST_PROMPT, "Generalist Agent"),
    }

    profiles = {}
    for agent_type, (prompt, name) in prompts.items():
        profiles[agent_type] = AgentProfile(
            agent_type=agent_type,
            display_name=name,
            system_prompt=prompt,
            tool_names=_AGENT_TOOLS[agent_type],
            description=f"Specialized {name.lower()} for JARVIS",
        )

    return profiles


_ROUTING_KEYWORDS: dict[AgentType, list[str]] = {
    AgentType.RESEARCHER: [
        "search", "research", "find information", "look up", "what is",
        "who is", "learn about", "find out", "gather data", "investigate",
        "weather", "forecast", "temperature", "climate",
    ],
    AgentType.CODER: [
        "write code", "create script", "run command", "execute",
        "compile", "build", "install", "npm", "pip", "git",
        "scaffold", "debug", "fix bug", "code", "implement",
        "programming", "develop", "function", "class",
    ],
    AgentType.BROWSER: [
        "browse", "navigate to", "open website", "click", "fill form",
        "web page", "login", "sign in", "download from", "screenshot",
        "tab", "chrome", "browser",
    ],
    AgentType.SYSTEM: [
        "open app", "close app", "volume", "brightness",
        "battery", "system", "finder", "terminal", "application",
        "clipboard", "paste", "notification",
    ],
    AgentType.COMMUNICATOR: [
        "email", "mail", "send message", "calendar", "schedule",
        "meeting", "event", "unread", "inbox", "compose",
        "invite", "reminder",
    ],
    AgentType.ANALYST: [
        "analyze", "compare", "summarize", "review", "evaluate",
        "assess", "report", "synthesize", "interpret", "conclude",
        "recommend", "pros and cons", "tradeoff",
    ],
}


def classify_subtask(description: str) -> AgentType:
    """Determine best agent type for a subtask using keyword scoring."""
    desc_lower = description.lower()
    scores: dict[AgentType, int] = {at: 0 for at in AgentType}

    for agent_type, keywords in _ROUTING_KEYWORDS.items():
        for keyword in keywords:
            if keyword in desc_lower:
                scores[agent_type] += 1

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return AgentType.GENERALIST

    if best_score >= 1:
        logger.debug(
            "Routed subtask to %s (score: %d): '%s'",
            best_type.value, best_score, description[:60],
        )
        return best_type

    return AgentType.GENERALIST


def classify_subtasks_batch(subtask_descriptions: list[str]) -> list[AgentType]:
    """Classify a batch of subtasks and return their agent assignments."""
    return [classify_subtask(desc) for desc in subtask_descriptions]


def find_parallel_groups(
    subtasks: list[dict],
) -> list[list[int]]:
    """Identify groups of subtasks that can run in parallel based on dependencies."""
    if not subtasks:
        return []

    id_to_idx = {}
    for i, st in enumerate(subtasks):
        st_id = st.get("id", str(i))
        id_to_idx[st_id] = i

    groups: list[list[int]] = []
    completed: set[str] = set()
    remaining = list(range(len(subtasks)))

    while remaining:
        ready = []
        still_waiting = []
        for idx in remaining:
            st = subtasks[idx]
            deps = st.get("depends_on", [])
            if all(dep in completed for dep in deps):
                ready.append(idx)
            else:
                still_waiting.append(idx)
        if not ready:
            logger.warning(
                "Dependency deadlock detected for %d subtask(s). "
                "Forcing sequential execution.",
                len(still_waiting),
            )
            for idx in still_waiting:
                groups.append([idx])
                st_id = subtasks[idx].get("id", str(idx))
                completed.add(st_id)
            break

        groups.append(ready)
        for idx in ready:
            st_id = subtasks[idx].get("id", str(idx))
            completed.add(st_id)
        remaining = still_waiting

    return groups


class AgentCoordinator:
    """Coordinates multiple specialized agents for complex task execution."""

    def __init__(self):
        self.profiles = _build_profiles()
        self._active_tasks: list[AgentTask] = []
        self._execution_history: list[AgentTask] = []
        self.max_parallel = 3
        self.parallel_enabled = True

    def initialize(self, all_tool_names: list[str]):
        """Initialize coordinator with full tool list for generalist profile."""
        self.profiles[AgentType.GENERALIST].tool_names = list(all_tool_names)
        logger.info(
            "Agent coordinator initialized with %d profiles. "
            "Generalist has %d tools.",
            len(self.profiles),
            len(all_tool_names),
        )

    def get_profile(self, agent_type: AgentType) -> AgentProfile:
        """Get the profile for a given agent type."""
        return self.profiles.get(agent_type, self.profiles[AgentType.GENERALIST])

    def get_tools_for_agent(
        self, agent_type: AgentType, all_schemas: list[dict],
    ) -> list[dict]:
        """
        Filter the full tool schema list to only include tools for a given agent.

        Args:
            agent_type: Which agent profile to use
            all_schemas: The complete TOOL_SCHEMAS list

        Returns:
            Filtered list of tool schemas for this agent
        """
        profile = self.get_profile(agent_type)

        # Generalist gets everything
        if agent_type == AgentType.GENERALIST or not profile.tool_names:
            return all_schemas

        allowed = set(profile.tool_names)
        return [s for s in all_schemas if s["name"] in allowed]

    def route_subtask(self, description: str) -> AgentType:
        """Route a subtask to the best agent type."""
        return classify_subtask(description)

    def route_subtasks(self, subtasks: list[dict]) -> list[dict]:
        """
        Route a list of subtasks, adding agent_type to each.

        Args:
            subtasks: List of subtask dicts from the planner

        Returns:
            Same list with 'agent_type' field added to each
        """
        for st in subtasks:
            desc = st.get("description", st.get("title", ""))
            st["agent_type"] = classify_subtask(desc).value
        return subtasks

    def get_parallel_groups(self, subtasks: list[dict]) -> list[list[int]]:
        """
        Get execution groups for parallel scheduling.

        Each group contains indices of subtasks that can run concurrently.
        Groups must be executed in order.
        """
        if not self.parallel_enabled:
            # Sequential fallback: each subtask is its own group
            return [[i] for i in range(len(subtasks))]
        return find_parallel_groups(subtasks)

    async def execute_parallel_group(
        self,
        group_indices: list[int],
        subtasks: list,
        execute_fn,
    ) -> list[tuple[int, str, Optional[str]]]:
        """Execute a group of subtasks in parallel."""
        sem = asyncio.Semaphore(self.max_parallel)

        async def run_one(idx: int):
            async with sem:
                st = subtasks[idx]
                agent_type_str = st.get("agent_type", "generalist")
                try:
                    agent_type = AgentType(agent_type_str)
                except ValueError:
                    agent_type = AgentType.GENERALIST

                task = AgentTask(
                    subtask_id=st.get("id", str(idx)),
                    agent_type=agent_type,
                    description=st.get("description", st.get("title", "")),
                    started_at=time.time(),
                    status="running",
                )
                self._active_tasks.append(task)

                try:
                    result = await execute_fn(st, agent_type)
                    task.status = "completed"
                    task.result = result
                    task.completed_at = time.time()
                    task.duration_s = task.completed_at - task.started_at
                    self._record_agent_stats(agent_type, True, task.duration_s)
                    return (idx, result, None)
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)[:300]
                    task.completed_at = time.time()
                    task.duration_s = task.completed_at - task.started_at
                    self._record_agent_stats(agent_type, False, task.duration_s)
                    return (idx, "", str(e)[:300])
                finally:
                    if task in self._active_tasks:
                        self._active_tasks.remove(task)
                    self._execution_history.append(task)

        results = await asyncio.gather(
            *[run_one(idx) for idx in group_indices],
            return_exceptions=False,
        )
        return results

    def _record_agent_stats(
        self, agent_type: AgentType, success: bool, duration_s: float,
    ):
        """Record execution stats for a specific agent."""
        profile = self.profiles.get(agent_type)
        if profile:
            profile.total_tasks += 1
            if success:
                profile.successful_tasks += 1
            profile.total_duration_s += duration_s

    def get_status(self) -> dict:
        """Get the coordinator status and agent profiles."""
        return {
            "parallel_enabled": self.parallel_enabled,
            "max_parallel": self.max_parallel,
            "active_tasks": len(self._active_tasks),
            "total_executed": sum(p.total_tasks for p in self.profiles.values()),
            "agents": {
                at.value: profile.to_dict()
                for at, profile in self.profiles.items()
            },
        }

    def get_active_agents(self) -> list[dict]:
        """Get currently running agent tasks."""
        return [
            {
                "subtask_id": t.subtask_id,
                "agent_type": t.agent_type.value,
                "description": t.description[:80],
                "status": t.status,
                "running_for_s": round(time.time() - t.started_at, 1)
                if t.started_at else 0,
            }
            for t in self._active_tasks
        ]

    def get_execution_history(self, limit: int = 20) -> list[dict]:
        """Get recent agent execution history."""
        recent = self._execution_history[-limit:]
        return [
            {
                "subtask_id": t.subtask_id,
                "agent_type": t.agent_type.value,
                "description": t.description[:60],
                "status": t.status,
                "duration_s": round(t.duration_s, 2),
                "error": t.error if t.error else None,
            }
            for t in reversed(recent)
        ]
