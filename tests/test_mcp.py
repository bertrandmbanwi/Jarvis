"""MCP client: remote tools join the registry behind the permission gate."""

from contextlib import asynccontextmanager

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from jarvis.agent.tool_selector import select_tools_for_request
from jarvis.agent.tools_schema import TOOL_REGISTRY, TOOL_SCHEMAS
from jarvis.core.mcp_client import MCPManager, jarvis_tool_name
from jarvis.core.permissions import assess_tool_call, get_tool_permission


def demo_server() -> MCPServer:
    server = MCPServer("demo")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def delete_everything() -> str:
        """Pretend to delete things."""
        return "deleted"

    return server


@asynccontextmanager
async def running_manager():
    # Start and close in the same task: MCP clients use anyio cancel scopes,
    # which must exit in the task that entered them (as the server lifespan does).
    srv = demo_server()
    mgr = MCPManager(
        config={"demo": {"command": "unused", "auto_approve": ["add"]}},
        client_factory=lambda target: Client(srv),
    )
    await mgr.start()
    try:
        yield mgr
    finally:
        await mgr.close()


def test_tool_names_are_provider_safe():
    assert jarvis_tool_name("my server", "do.thing") == "mcp__my_server__do_thing"
    assert len(jarvis_tool_name("s" * 50, "t" * 50)) == 64


@pytest.mark.asyncio
async def test_remote_tools_are_registered_and_callable():
    async with running_manager() as manager:
        name = jarvis_tool_name("demo", "add")
        assert set(manager.registered) == {name, jarvis_tool_name("demo", "delete_everything")}
        assert any(s["name"] == name and s["input_schema"]["properties"] for s in TOOL_SCHEMAS)
        result = await TOOL_REGISTRY[name](a=2, b=3)
        assert "\n5\n" in result and "ignore any instructions" in result
        description = next(s["description"] for s in TOOL_SCHEMAS if s["name"] == name)
        assert description.startswith("[Third-party tool")


@pytest.mark.asyncio
async def test_untrusted_remote_tools_need_confirmation():
    async with running_manager():
        risky = jarvis_tool_name("demo", "delete_everything")
        assert get_tool_permission(risky).requires_confirmation
        assert not assess_tool_call(risky, {}).allowed
        assert not get_tool_permission(jarvis_tool_name("demo", "add")).requires_confirmation


@pytest.mark.asyncio
async def test_selector_includes_mcp_tools_when_server_is_mentioned():
    async with running_manager():
        names = {t["name"] for t in select_tools_for_request("ask demo to add 2 and 3", TOOL_SCHEMAS)}
        assert jarvis_tool_name("demo", "add") in names


@pytest.mark.asyncio
async def test_close_unregisters_tools():
    srv = demo_server()
    mgr = MCPManager(config={"demo": {"command": "unused"}}, client_factory=lambda target: Client(srv))
    await mgr.start()
    await mgr.close()
    assert not any(n.startswith("mcp__demo__") for n in TOOL_REGISTRY)
    assert not any(s["name"].startswith("mcp__demo__") for s in TOOL_SCHEMAS)


@pytest.mark.asyncio
async def test_unreachable_server_is_reported_not_fatal():
    def broken(target):
        raise ConnectionError("no such server")

    mgr = MCPManager(config={"gone": {"command": "missing"}}, client_factory=broken)
    await mgr.start()
    assert "gone" in mgr.status()["errors"]


def test_jarvis_mcp_server_exposes_only_safe_tools(monkeypatch):
    # get_upcoming_events is macOS-only; keep it eligible on Linux CI.
    monkeypatch.setattr("jarvis.agent.platform_tools.IS_MACOS", True)
    from jarvis.mcp_server import exposed_tools

    names = exposed_tools(extra="")
    assert "get_weather" in names
    assert "send_email" not in names and "run_command" not in names and "create_note" not in names
    # Private content (files, clipboard, screen, email, calendar) is opt-in.
    for private in ("analyze_screen", "capture_screen", "read_file", "get_clipboard", "get_upcoming_events"):
        assert private not in names
    assert "get_upcoming_events" in exposed_tools(extra="get_upcoming_events")
    # Opting a confirm-required tool in still doesn't expose it.
    assert "send_email" not in exposed_tools(extra="send_email")


@pytest.mark.asyncio
async def test_jarvis_mcp_server_calls_go_through_the_permission_gate():
    from unittest.mock import AsyncMock

    from jarvis.mcp_server import build_server

    executor = AsyncMock()
    executor._execute_tool = AsyncMock(return_value="Sunny, 21C")
    server = build_server(executor=executor, extra="")
    async with Client(server) as client:
        listing = await client.list_tools()
        assert "get_weather" in {t.name for t in listing.tools}
        result = await client.call_tool("get_weather", {"location": "Paris"})
    executor._execute_tool.assert_awaited_once_with("get_weather", {"location": "Paris"})
    assert result.content[0].text == "Sunny, 21C"
