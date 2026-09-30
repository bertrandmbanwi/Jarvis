"""Local (OpenAI-compatible) provider, Apple on-device routing, and offline mode."""

import json
from types import SimpleNamespace

import pytest

from jarvis.config import settings
from jarvis.core.providers import SystemPrompt, TierSpec, tier_specs
from jarvis.core.providers.apple_fm import flatten
from jarvis.core.providers.local_provider import LocalProvider

SYSTEM = SystemPrompt(static="S", dynamic="D")


def completion(content="", tool_calls=None, finish="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def tool_call(name, args, call_id="c1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeChat:
    def __init__(self, responses):
        self.requests, self._responses = [], list(responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        return self._responses.pop(0)


class FakeApple:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def available(self):
        return self.ok

    async def respond(self, instructions, messages, json_schema=None):
        self.calls.append(messages)
        return "Bonjour."


@pytest.mark.asyncio
async def test_tool_loop_uses_chat_completions_tools():
    client = FakeChat([completion(tool_calls=[tool_call("get_weather", {"location": "Paris"})]), completion("Sunny.")])
    seen = []

    async def executor(name, args):
        seen.append((name, args))
        return "72F"

    result = await LocalProvider("http://x", tool_model="llama3.1:8b", client=client).run_tools(
        system=SYSTEM, messages=[{"role": "user", "content": "weather?"}],
        tools=[{"name": "get_weather", "input_schema": {"type": "object"}}],
        executor=executor, spec=TierSpec("llama3.1:8b", 512), max_iterations=3, on_usage=lambda u: None,
    )
    assert result.text == "Sunny." and seen == [("get_weather", {"location": "Paris"})]
    first = client.requests[0]
    assert first["messages"][0] == {"role": "system", "content": "SD"}
    assert first["tools"][0]["function"]["name"] == "get_weather"
    tool_msg = client.requests[1]["messages"][-1]
    assert tool_msg == {"role": "tool", "tool_call_id": "c1", "content": "72F"}


@pytest.mark.asyncio
async def test_apple_model_serves_plain_replies_only():
    client = FakeChat([completion('{"verdict": "simple"}')])
    apple = FakeApple()
    provider = LocalProvider("http://x", tool_model="llama3.1:8b", client=client, apple=apple)

    text, usage = await provider.complete(system=SYSTEM, messages=[{"role": "user", "content": "hi"}], spec=TierSpec("apple", 128))
    assert text == "Bonjour." and usage.model == "apple" and client.requests == []

    schema = {"title": "v", "type": "object", "properties": {}, "required": [], "additionalProperties": False}
    text, _ = await provider.complete(system=SYSTEM, messages=[{"role": "user", "content": "x"}], spec=TierSpec("apple", 128), json_schema=schema)
    assert text == '{"verdict": "simple"}'
    assert client.requests[0]["model"] == "llama3.1:8b"
    assert client.requests[0]["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_apple_unavailable_falls_back_to_server_model():
    client = FakeChat([completion("hello")])
    provider = LocalProvider("http://x", tool_model="llama3.1:8b", client=client, apple=FakeApple(ok=False))
    text, _ = await provider.complete(system=SYSTEM, messages=[{"role": "user", "content": "hi"}], spec=TierSpec("apple", 64))
    assert text == "hello" and client.requests[0]["model"] == "llama3.1:8b"


def test_flatten_keeps_history_as_context():
    assert flatten([{"role": "user", "content": "hi"}]) == "hi"
    prompt = flatten([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}])
    assert "User: a" in prompt and "Assistant: b" in prompt and prompt.endswith("User: c")


def test_local_tiers_and_zero_cost(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_FAST_MODEL", "apple")
    monkeypatch.setattr(settings, "LOCAL_LLM_MODEL", "gpt-oss:20b")
    specs = tier_specs("local")
    assert specs["fast"].model == "apple" and specs["deep"].model == "gpt-oss:20b"


@pytest.mark.asyncio
async def test_local_provider_never_hits_budget_guard(monkeypatch):
    from jarvis.core.llm import JarvisLLM

    llm = JarvisLLM(provider=LocalProvider("http://x", tool_model="m", client=FakeChat([])))
    monkeypatch.setattr(llm, "_paid_usage_blocked", lambda: (True, "daily limit"))
    assert await llm._budget_blocked() == (False, "")


def test_offline_mode_forces_codex_with_local_model(monkeypatch):
    from jarvis.tools import coding_agent

    monkeypatch.setattr(settings, "OFFLINE_MODE", True)
    monkeypatch.setattr(settings, "CODING_AGENT", "claude")
    assert coding_agent.choose_agent() == "codex"
    assert "--oss" in coding_agent.build_codex_command("/bin/codex", "t", "/tmp", "/o")
