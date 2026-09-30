"""OpenAI Responses provider and provider-neutral LLM routing."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis.config import settings
from jarvis.core.hardening import ErrorCategory, classify_error, cloud_circuit
from jarvis.core.llm import JarvisLLM, ToolLoopError
from jarvis.core.providers import ProviderError, SystemPrompt, TierSpec, Usage
from jarvis.core.providers.openai_provider import OpenAIProvider, _usage_from

SPEC = TierSpec("gpt-6.1-sol", 4096, effort="medium")
SYSTEM = SystemPrompt(static="STATIC", dynamic="DYNAMIC")


class Item(SimpleNamespace):
    def model_dump(self, **_):
        return {k: v for k, v in vars(self).items() if v is not None}


def usage(total=100, cached=0, written=0, out=10):
    return SimpleNamespace(
        input_tokens=total,
        output_tokens=out,
        input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=written),
    )


def response(output, text="", status="completed"):
    return SimpleNamespace(output=output, output_text=text, status=status, usage=usage())


def call(name, args, call_id):
    return Item(type="function_call", name=name, arguments=json.dumps(args), call_id=call_id)


def message(text):
    return Item(type="message", content=[Item(type="output_text", text=text)])


class FakeClient:
    def __init__(self, responses):
        self.requests = []
        self._responses = list(responses)
        self.responses = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        # Copy the input list: the provider keeps appending to the same object.
        self.requests.append({**kwargs, "input": list(kwargs.get("input", []))})
        return self._responses.pop(0)


def test_usage_splits_cached_and_cache_write_tokens():
    u = _usage_from(usage(total=1000, cached=800, written=100, out=50), "gpt-6.1-sol")
    assert (u.input_tokens, u.cache_read_tokens, u.cache_write_tokens, u.output_tokens) == (100, 800, 100, 50)
    price = settings.MODEL_PRICING["gpt-6.1-sol"]
    expected = (100 * 2.00 + 800 * 0.10 + 100 * 2.50 + 50 * 10.00) / 1e6
    assert u.cost(price) == pytest.approx(expected)


@pytest.mark.asyncio
async def test_complete_uses_instructions_developer_context_and_json_schema():
    client = FakeClient([response([message('{"verdict": "simple"}')], text='{"verdict": "simple"}')])
    provider = OpenAIProvider("key", client=client)
    schema = {"title": "verdict", "type": "object", "properties": {"verdict": {"type": "string"}},
              "required": ["verdict"], "additionalProperties": False}

    text, _ = await provider.complete(
        system=SYSTEM, messages=[{"role": "user", "content": "hi"}], spec=SPEC, json_schema=schema
    )

    req = client.requests[0]
    assert text == '{"verdict": "simple"}'
    assert req["instructions"] == "STATIC"
    assert req["store"] is False
    assert req["reasoning"] == {"effort": "medium"}
    assert "temperature" not in req
    # Dynamic context sits just before the latest user turn, after the cacheable prefix.
    assert req["input"] == [{"role": "developer", "content": "DYNAMIC"}, {"role": "user", "content": "hi"}]
    assert req["text"]["format"]["type"] == "json_schema"
    assert req["text"]["format"]["strict"] is True


@pytest.mark.asyncio
async def test_tool_loop_runs_parallel_calls_and_returns_outputs():
    client = FakeClient([
        response([call("get_weather", {"location": "Paris"}, "c1"), call("get_time", {}, "c2")]),
        response([message("Sunny, 3pm.")], text="Sunny, 3pm."),
    ])
    running = 0
    peak = 0

    async def executor(name, args):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return f"{name} ok"

    result = await OpenAIProvider("key", client=client).run_tools(
        system=SYSTEM, messages=[{"role": "user", "content": "weather?"}],
        tools=[{"name": "get_weather", "description": "", "input_schema": {"type": "object"}}],
        executor=executor, spec=SPEC, max_iterations=5, on_usage=lambda u: None,
    )

    assert result.text == "Sunny, 3pm." and result.completed
    assert peak == 2  # both tools ran concurrently
    assert [c["name"] for c in result.tool_calls] == ["get_weather", "get_time"]
    second_input = client.requests[1]["input"]
    outputs = [i for i in second_input if i.get("type") == "function_call_output"]
    assert [(o["call_id"], o["output"]) for o in outputs] == [("c1", "get_weather ok"), ("c2", "get_time ok")]
    assert client.requests[0]["tools"][0] == {
        "type": "function", "name": "get_weather", "description": "",
        "parameters": {"type": "object"}, "strict": False,
    }


@pytest.mark.asyncio
async def test_tool_loop_adds_tool_search_for_deferred_tools():
    client = FakeClient([response([message("done")], text="done")])
    await OpenAIProvider("key", client=client).run_tools(
        system=SYSTEM, messages=[{"role": "user", "content": "x"}],
        tools=[{"name": "core", "input_schema": {}}, {"name": "rare", "input_schema": {}, "defer_loading": True}],
        executor=AsyncMock(), spec=SPEC, max_iterations=2, on_usage=lambda u: None,
    )
    tools = client.requests[0]["tools"]
    assert tools[1]["defer_loading"] is True
    assert tools[-1] == {"type": "tool_search"}


@pytest.mark.asyncio
async def test_tool_loop_rejects_invalid_arguments_without_running_tool():
    bad = Item(type="function_call", name="send_email", arguments="{not json", call_id="c1")
    client = FakeClient([response([bad]), response([message("sorry")], text="sorry")])
    executor = AsyncMock()
    await OpenAIProvider("key", client=client).run_tools(
        system=SYSTEM, messages=[{"role": "user", "content": "x"}], tools=[],
        executor=executor, spec=SPEC, max_iterations=3, on_usage=lambda u: None,
    )
    executor.assert_not_awaited()
    output = next(i for i in client.requests[1]["input"] if i.get("type") == "function_call_output")
    assert "invalid arguments" in output["output"]


@pytest.mark.asyncio
async def test_tool_loop_sends_image_results_as_input_images():
    client = FakeClient([response([call("take_screenshot", {}, "c1")]), response([message("ok")], text="ok")])

    async def executor(name, args):
        return [{"type": "image", "source": {"media_type": "image/png", "data": "AAA"}},
                {"type": "text", "text": "screen"}]

    await OpenAIProvider("key", client=client).run_tools(
        system=SYSTEM, messages=[{"role": "user", "content": "x"}], tools=[],
        executor=executor, spec=SPEC, max_iterations=3, on_usage=lambda u: None,
    )
    output = next(i for i in client.requests[1]["input"] if i.get("type") == "function_call_output")
    assert output["output"][0] == {"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "auto"}


@pytest.mark.asyncio
async def test_tool_loop_reports_incomplete_at_iteration_cap():
    client = FakeClient([response([call("t", {}, f"c{i}")]) for i in range(2)])
    result = await OpenAIProvider("key", client=client).run_tools(
        system=SYSTEM, messages=[{"role": "user", "content": "x"}], tools=[],
        executor=AsyncMock(return_value="r"), spec=SPEC, max_iterations=2, on_usage=lambda u: None,
    )
    assert result.completed is False


@pytest.mark.asyncio
async def test_retry_hook_wraps_each_api_call():
    client = FakeClient([response([message("hi")], text="hi")])
    contexts = []

    async def retry(fn, context):
        contexts.append(context)
        return await fn()

    await OpenAIProvider("key", client=client, retry=retry).complete(
        system=SYSTEM, messages=[{"role": "user", "content": "x"}], spec=SPEC
    )
    assert contexts == ["openai.responses"]


def test_sdk_client_built_without_its_own_retries(monkeypatch):
    import openai

    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)
    OpenAIProvider("key")._get_client()
    assert captured["max_retries"] == 0


def test_classify_error_uses_http_status_of_wrapped_error():
    class APIError(Exception):
        status_code = 429

    try:
        try:
            raise APIError("boom")
        except APIError as inner:
            raise ProviderError("wrapped") from inner
    except ProviderError as err:
        assert classify_error(err) == ErrorCategory.RATE_LIMIT


class FlakyProvider:
    name = "openai"

    def __init__(self):
        self.calls = 0
        self.fail = True

    def is_configured(self):
        return True

    async def complete(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise ProviderError("503")
        return "cloud answer", Usage(model="gpt-6-luna")


@pytest.fixture
def llm(monkeypatch):
    provider = FlakyProvider()
    instance = JarvisLLM(provider=provider)
    monkeypatch.setattr(instance, "_check_ollama_health", AsyncMock(return_value=True))
    monkeypatch.setattr(instance, "_chat_ollama", AsyncMock(return_value="local answer"))
    monkeypatch.setattr(instance, "_track_usage", lambda *a, **k: None)
    monkeypatch.setattr(instance, "_paid_usage_blocked", lambda: (False, ""))
    cloud_circuit.record_success()
    yield instance, provider
    cloud_circuit.record_success()


@pytest.mark.asyncio
async def test_cloud_failure_falls_back_temporarily_then_recovers(llm, monkeypatch):
    instance, provider = llm
    clock = [1000.0]
    monkeypatch.setattr("jarvis.core.llm.time.monotonic", lambda: clock[0])

    assert await instance.chat("hi") == "local answer"
    assert provider.calls == 1

    # Within the cooldown the cloud is not retried.
    assert await instance.chat("hi") == "local answer"
    assert provider.calls == 1

    # After the cooldown the cloud is tried again and becomes active.
    provider.fail = False
    clock[0] += settings.CLOUD_RETRY_COOLDOWN_S + 1
    assert await instance.chat("hi") == "cloud answer"
    assert instance.active_backend == "openai"


@pytest.mark.asyncio
async def test_chat_json_returns_dict_or_none(llm):
    instance, provider = llm
    provider.fail = False
    provider.complete = AsyncMock(return_value=('{"verdict": "complex"}', Usage(model="gpt-6-luna")))
    assert await instance.chat_json("x", {"type": "object"}) == {"verdict": "complex"}
    provider.complete = AsyncMock(return_value=("not json", Usage(model="gpt-6-luna")))
    instance._chat_ollama.return_value = "also not json"
    assert await instance.chat_json("x", {"type": "object"}) is None


@pytest.mark.asyncio
async def test_tool_loop_failure_raises_when_requested(llm):
    instance, provider = llm
    provider.run_tools = AsyncMock(side_effect=ProviderError("down"))
    with pytest.raises(ToolLoopError):
        await instance.chat_with_tools("x", [], AsyncMock(), raise_on_failure=True)


def test_browser_agent_keeps_only_recent_screenshots():
    from jarvis.tools.browser_agent import KEEP_SCREENSHOTS, _PLACEHOLDER_IMAGE, _prune_openai_screenshots

    items = [
        {"type": "computer_call_output", "call_id": str(i), "output": {"type": "computer_screenshot", "image_url": f"img{i}"}}
        for i in range(5)
    ]
    _prune_openai_screenshots(items)
    kept = [i["output"]["image_url"] for i in items if i["output"]["image_url"] != _PLACEHOLDER_IMAGE]
    assert kept == [f"img{i}" for i in range(5 - (KEEP_SCREENSHOTS - 1), 5)]
