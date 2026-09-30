"""On non-macOS systems, macOS-only tools are hidden and refuse to run."""

from unittest.mock import MagicMock

import pytest

from jarvis.agent import platform_tools
from jarvis.agent.executor import AgentExecutor
from jarvis.agent.tools_schema import TOOL_SCHEMAS


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(platform_tools, "IS_MACOS", False)


def test_everything_is_available_on_macos(monkeypatch):
    monkeypatch.setattr(platform_tools, "IS_MACOS", True)
    assert platform_tools.available_schemas(TOOL_SCHEMAS) is TOOL_SCHEMAS


def test_macos_only_tools_are_hidden_elsewhere(linux):
    names = {s["name"] for s in platform_tools.available_schemas(TOOL_SCHEMAS)}
    for hidden in ("open_application", "analyze_screen", "send_email", "create_note", "set_volume"):
        assert hidden not in names
    for kept in ("get_weather", "search_web", "read_file", "run_command", "use_skill", "browse_web"):
        assert kept in names


def test_executor_offers_only_available_tools(linux):
    llm = MagicMock()
    llm.cloud_name = "openai"
    names = {t["name"] for t in AgentExecutor(llm=llm)._tools_for("open Safari", None, None)}
    assert "open_application" not in names and "get_weather" in names


@pytest.mark.asyncio
async def test_calling_a_macos_tool_elsewhere_explains_why(linux):
    result = await AgentExecutor(llm=MagicMock())._execute_tool("open_application", {"app_name": "Safari"})
    assert "only works on macOS" in result
