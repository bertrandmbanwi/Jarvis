"""Tests for API cost controls and local-first routing."""
import pytest

from jarvis.agent.tool_selector import select_tools_for_request
from jarvis.agent.tools_schema import TOOL_SCHEMAS
from jarvis.config import settings
from jarvis.core.cache import tool_cache
from jarvis.core.llm import JarvisLLM
from jarvis.core.local_router import is_probable_noise, route_local
from jarvis.tools import weather


def test_system_prompt_blocks_keep_dynamic_context_uncached():
    blocks = settings.get_system_prompt_blocks()

    assert len(blocks) == 2
    assert blocks[0]["cache_control"]["type"] == "ephemeral"
    assert "dynamic_context" not in blocks[0]["text"]
    assert "dynamic_context" in blocks[1]["text"]
    assert "cache_control" not in blocks[1]


def test_tool_selector_prunes_weather_request():
    selected = select_tools_for_request("How is the weather looking today?", TOOL_SCHEMAS)
    names = {tool["name"] for tool in selected}

    assert "get_weather" in names
    assert "run_command" not in names
    assert len(selected) < len(TOOL_SCHEMAS)


def test_tool_cache_includes_weather_and_web_reads():
    assert tool_cache.is_cacheable("get_weather") is True
    assert tool_cache.is_cacheable("search_web") is True
    assert tool_cache.is_cacheable("fetch_page_text") is True


def test_llm_adds_cache_breakpoint_to_last_tool():
    llm = JarvisLLM()
    tools = [{"name": "a"}, {"name": "b"}]

    prepared = llm._tools_with_cache_breakpoint(tools)

    assert prepared is not None
    assert "cache_control" not in prepared[0]
    assert prepared[1]["cache_control"]["type"] == "ephemeral"
    assert "cache_control" not in tools[1]


def test_probable_noise_filters_numeric_transcripts():
    assert is_probable_noise("Seven, five, one, two, six.") is True
    assert is_probable_noise("7, 5, 1, 2, 6") is True


@pytest.mark.asyncio
async def test_local_router_handles_weather_without_llm(monkeypatch):
    async def fake_weather(location: str = "") -> str:
        return f"weather called for {location or 'default'}"

    monkeypatch.setattr(weather, "get_weather", fake_weather)

    result = await route_local("How is the weather looking today?")

    assert result is not None
    assert result.action == "weather"
    assert result.tier == "local"
    assert result.response == "weather called for default"


@pytest.mark.asyncio
async def test_local_router_privacy_command_is_not_remembered():
    result = await route_local("turn on privacy mode")

    assert result is not None
    assert result.action == "privacy_on"
    assert result.remember is False
