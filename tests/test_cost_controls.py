"""Tests for API cost controls and local-first routing."""
import pytest

from jarvis.agent.tool_selector import select_tools_for_request
from jarvis.agent.tools_schema import TOOL_SCHEMAS
from jarvis.config import settings
from jarvis.core.cache import tool_cache
from jarvis.core.llm import JarvisLLM
from jarvis.core.local_router import is_probable_noise, route_local
from jarvis.core.savings import SavingsTracker
from jarvis.tools import public_data, weather


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
    assert tool_cache.is_cacheable("convert_currency") is True
    assert tool_cache.is_cacheable("get_crypto_price") is True
    assert tool_cache.is_cacheable("get_country_info") is True


def test_tool_selector_prunes_public_data_request():
    selected = select_tools_for_request("Convert 100 USD to EUR", TOOL_SCHEMAS)
    names = {tool["name"] for tool in selected}

    assert "convert_currency" in names
    assert "get_sec_company_filings" not in names
    assert "run_command" not in names
    assert len(selected) < len(TOOL_SCHEMAS)


def test_savings_tracker_counts_local_and_free_api_routes():
    tracker = SavingsTracker()

    tracker.record_local_route("currency_conversion", tool_name="convert_currency", cache_hit=False)
    tracker.record_local_route("currency_conversion", tool_name="convert_currency", cache_hit=True)
    tracker.record_local_route("time")

    summary = tracker.get_summary()

    assert summary["local_routes"] == 3
    assert summary["paid_calls_avoided"] == 3
    assert summary["free_api_calls"] == 2
    assert summary["cache_hits"] == 1
    assert summary["by_provider"]["Frankfurter/Fawaz"] == 2


def test_anthropic_provider_adds_cache_breakpoint_to_last_tool():
    from jarvis.core.providers.anthropic_provider import AnthropicProvider

    tools = [{"name": "a"}, {"name": "b"}]
    prepared = AnthropicProvider("key")._tools(tools)

    assert "cache_control" not in prepared[0]
    assert prepared[1]["cache_control"]["type"] == "ephemeral"
    assert "cache_control" not in tools[1]


def test_probable_noise_filters_numeric_transcripts():
    assert is_probable_noise("Seven, five, one, two, six.") is True
    assert is_probable_noise("7, 5, 1, 2, 6") is True


@pytest.mark.asyncio
async def test_local_router_handles_weather_without_llm(monkeypatch):
    await tool_cache.invalidate()

    async def fake_weather(location: str = "") -> str:
        return f"weather called for {location or 'default'}"

    monkeypatch.setattr(weather, "get_weather", fake_weather)

    result = await route_local("How is the weather looking today?")

    assert result is not None
    assert result.action == "weather"
    assert result.tier == "local"
    assert result.response == "weather called for default"


@pytest.mark.asyncio
async def test_local_router_handles_currency_without_llm(monkeypatch):
    await tool_cache.invalidate()

    async def fake_convert(amount: float, from_currency: str, to_currency: str) -> str:
        return f"converted {amount:g} {from_currency} to {to_currency}"

    monkeypatch.setattr(public_data, "convert_currency", fake_convert)

    result = await route_local("convert 100 USD to EUR")

    assert result is not None
    assert result.action == "currency_conversion"
    assert result.tier == "local"
    assert result.response == "converted 100 USD to EUR"


@pytest.mark.asyncio
async def test_local_router_handles_public_holiday_without_llm(monkeypatch):
    await tool_cache.invalidate()

    async def fake_is_holiday(country_code: str = "US", check_date: str = "") -> str:
        return f"holiday check for {country_code} on {check_date or 'today'}"

    monkeypatch.setattr(public_data, "is_public_holiday", fake_is_holiday)

    result = await route_local("is today a holiday in the US?")

    assert result is not None
    assert result.action == "public_holiday_check"
    assert result.response == "holiday check for US on today"


@pytest.mark.asyncio
async def test_local_router_handles_country_facts_without_llm(monkeypatch):
    await tool_cache.invalidate()

    async def fake_country_info(country: str) -> str:
        return f"country info for {country}"

    monkeypatch.setattr(public_data, "get_country_info", fake_country_info)

    result = await route_local("what is the capital of Cameroon?")

    assert result is not None
    assert result.action == "country_info"
    assert result.response == "country info for Cameroon"


@pytest.mark.asyncio
async def test_local_router_privacy_command_is_not_remembered():
    result = await route_local("turn on privacy mode")

    assert result is not None
    assert result.action == "privacy_on"
    assert result.remember is False


@pytest.mark.asyncio
async def test_local_router_does_not_swallow_requests_containing_incorrect():
    assert await route_local("The event time is incorrect, fix it to 3pm") is None


@pytest.mark.asyncio
async def test_local_router_logs_bare_correction(monkeypatch):
    from jarvis.core import local_router

    monkeypatch.setattr(local_router.feedback, "add_feedback", lambda raw, category: {"id": "abcdef123"})
    result = await route_local("That's incorrect.")
    assert result is not None and result.action == "feedback_correction"


def test_anthropic_usage_bills_input_tokens_fully():
    """Anthropic's input_tokens already excludes cached tokens; nothing is subtracted."""
    from types import SimpleNamespace

    from jarvis.core.providers.anthropic_provider import _usage_from

    price = settings.MODEL_PRICING["claude-sonnet-5"]
    usage = _usage_from(
        SimpleNamespace(input_tokens=500, output_tokens=0, cache_read_input_tokens=3000, cache_creation_input_tokens=0),
        "claude-sonnet-5",
    )
    expected = 500 / 1e6 * price["input"] + 3000 / 1e6 * price["cache_read"]
    assert usage.cost(price) == pytest.approx(expected)


def test_track_usage_redacts_preview_in_privacy_mode(monkeypatch):
    from jarvis.core import cost_tracker
    from jarvis.core.providers import Usage

    logged = {}
    monkeypatch.setattr(cost_tracker, "log_request", lambda **kw: logged.update(kw))
    llm = JarvisLLM()
    llm.privacy_mode = True
    llm._track_usage(Usage(model="gpt-6-luna", input_tokens=1, output_tokens=1), "brain", 0.1, "my secret prompt")
    assert logged["user_input_preview"] == ""


def test_tool_selector_uses_recent_history_for_follow_ups():
    history = [
        {"role": "user", "content": "Draft an email to Sam about Friday"},
        {"role": "assistant", "content": "Here is the draft email. Should I send it?"},
    ]
    names = {t["name"] for t in select_tools_for_request("yes, send it", TOOL_SCHEMAS, history)}
    assert "send_email" in names


def test_tool_selector_matches_whole_words_only():
    names = {t["name"] for t in select_tools_for_request("help me solve this method", TOOL_SCHEMAS)}
    assert "get_crypto_price" not in names


def test_deferred_loading_is_stable_and_keeps_core_tools_loaded():
    from jarvis.agent.tool_selector import COMMON_TOOLS, with_deferred_loading

    first = with_deferred_loading(TOOL_SCHEMAS)
    assert first == with_deferred_loading(TOOL_SCHEMAS)  # identical every request -> cacheable
    assert [t["name"] for t in first] == [t["name"] for t in TOOL_SCHEMAS]
    loaded = {t["name"] for t in first if not t.get("defer_loading")}
    assert loaded == COMMON_TOOLS & {t["name"] for t in TOOL_SCHEMAS}
    assert "defer_loading" not in TOOL_SCHEMAS[0]  # input not mutated

    subset = [t for t in TOOL_SCHEMAS if t["name"] not in COMMON_TOOLS][:5]
    assert any(not t.get("defer_loading") for t in with_deferred_loading(subset))
