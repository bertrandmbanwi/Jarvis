"""Expose JARVIS tools to other AI clients over MCP (Claude Code, Cursor, Codex, ...).

Run over stdio:

    python -m jarvis.mcp_server

Claude Code:  claude mcp add jarvis -- /path/to/Jarvis/.venv/bin/python -m jarvis.mcp_server
Cursor/others: {"mcpServers": {"jarvis": {"command": "/path/to/Jarvis/.venv/bin/python",
                                          "args": ["-m", "jarvis.mcp_server"]}}}

Only read-only tools that don't reveal private content are exposed by default
(weather, web search, public data, ...). Tools that read files, the
clipboard, the screen, email or calendar, and anything that changes state,
need an explicit opt-in: JARVIS_MCP_TOOLS=read_file,get_upcoming_events,... Every call still goes through JARVIS's
permission gate, and tools that need human confirmation are never exposed:
an MCP client can't show JARVIS's approval prompt.
"""
from __future__ import annotations

import functools
import logging
import os
from typing import Any

from jarvis.agent.executor import AgentExecutor
from jarvis.agent.platform_tools import is_available
from jarvis.agent.tools_schema import TOOL_REGISTRY, TOOL_SCHEMAS
from jarvis.core.permissions import Capability, RiskLevel, get_tool_permission, is_side_effect_free

logger = logging.getLogger("jarvis.mcp.server")

_PRIVATE_CAPABILITIES = frozenset({Capability.READ_LOCAL, Capability.OBSERVATION, Capability.COMMUNICATION})

INSTRUCTIONS = (
    "Tools from JARVIS, a personal assistant running on the user's Mac: macOS status, "
    "weather, web search, public data and more (the user chooses which tools are shared)."
)


def exposed_tools(extra: str | None = None) -> list[str]:
    """Tool names to expose: side-effect-free ones plus JARVIS_MCP_TOOLS, minus confirm-required."""
    wanted = {name.strip() for name in (extra if extra is not None else os.getenv("JARVIS_MCP_TOOLS", "")).split(",")}
    names = []
    for schema in TOOL_SCHEMAS:
        name = str(schema["name"])
        if name.startswith("mcp__") or not is_available(name):
            continue  # skip tools borrowed from other MCP servers and ones this OS can't run
        permission = get_tool_permission(name)
        if permission.requires_confirmation:
            continue
        # By default: read-only tools that don't reveal private content. Files,
        # clipboard, screen, email and calendar need an explicit opt-in.
        private = permission.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) or bool(
            permission.capabilities & _PRIVATE_CAPABILITIES
        )
        default = is_side_effect_free(name) and not private
        if default or name in wanted:
            names.append(name)
    return names


def build_server(executor: AgentExecutor | None = None, extra: str | None = None) -> Any:
    from mcp.server.mcpserver import MCPServer

    executor = executor or AgentExecutor()
    server = MCPServer("jarvis", instructions=INSTRUCTIONS)
    descriptions = {str(s["name"]): str(s.get("description", "")) for s in TOOL_SCHEMAS}

    for name in exposed_tools(extra):
        fn = TOOL_REGISTRY[name]

        def make_gateway(tool_name: str, tool_fn: Any) -> Any:
            # functools.wraps keeps the tool's signature, so the MCP input
            # schema matches JARVIS's; the call itself goes through the gate.
            @functools.wraps(tool_fn)
            async def gateway(**kwargs: Any) -> str:
                result = await executor._execute_tool(tool_name, kwargs)
                return result if isinstance(result, str) else str(result)

            return gateway

        server.add_tool(make_gateway(name, fn), name=name, description=descriptions.get(name, ""))
    logger.info("JARVIS MCP server exposing %d tools.", len(exposed_tools(extra)))
    return server


def main() -> None:
    logging.basicConfig(level=logging.WARNING)  # stdout carries the protocol; logs go to stderr
    build_server().run("stdio")


if __name__ == "__main__":
    main()
