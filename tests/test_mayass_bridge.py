"""Tests for the MayAss Hermes bridge text MVP.

Phase 3 scope: prove MayAss can call a text-only Hermes runner without
routing /chat, changing UI, voice, memory, or tool ownership.
"""

import pytest


@pytest.mark.asyncio
async def test_mayass_bridge_fake_runner_returns_structured_response():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def fake_runner(prompt: str, timeout: float) -> str:
        assert "Maymint" in prompt
        assert "มาย" in prompt
        assert "JARVIS" not in prompt
        assert timeout > 0
        return "มายพร้อมแล้วค่ะบอส"

    bridge = MayAssBridge(runner=fake_runner)
    response = await bridge.process(
        MayAssBridgeRequest(text="ทักทายบอสสั้น ๆ", mode="realtime", session_id="s1")
    )

    assert response.backend == "hermes"
    assert response.mode == "realtime"
    assert response.text == "มายพร้อมแล้วค่ะบอส"
    assert response.ok is True
    assert response.error == ""


@pytest.mark.asyncio
async def test_mayass_bridge_work_mode_prompt_is_maymint_not_jarvis():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    captured = {}

    async def fake_runner(prompt: str, timeout: float) -> str:
        captured["prompt"] = prompt
        return "สรุปแบบ work mode ให้แล้วค่ะบอส"

    bridge = MayAssBridge(runner=fake_runner)
    response = await bridge.process(
        MayAssBridgeRequest(
            text="สรุปงานต่อไป",
            source="test",
            mode="work",
            session_id="phase3",
            wants_voice=False,
            allow_tools=False,
            confirmation_policy="safe-only",
        )
    )

    prompt = captured["prompt"]
    assert response.mode == "work"
    assert "work" in prompt
    assert "Maymint" in prompt
    assert "มาย" in prompt
    assert "บอส" in prompt
    assert "สรุปงานต่อไป" in prompt
    assert "allow_tools=False" in prompt
    assert "confirmation_policy=safe-only" in prompt
    assert "JARVIS" not in prompt
    assert "Becs" not in prompt
    assert "sir" not in prompt


def test_mayass_prompt_includes_configured_hermes_runtime(monkeypatch, tmp_path):
    from jarvis.core import mayass_bridge
    from jarvis.core.mayass_bridge import MayAssBridgeRequest

    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    (hermes_dir / "config.yaml").write_text(
        "model:\n"
        "  provider: openai-codex\n"
        "  default: gpt-5.5\n"
        "  max_tokens: 16000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mayass_bridge.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(mayass_bridge.settings, "MAYASS_HERMES_COMMAND", "hermes -z")

    prompt = mayass_bridge.build_prompt_envelope(MayAssBridgeRequest(text="ใช้โมเดลอะไร"))

    assert "Hermes runtime:" in prompt
    assert "provider=openai-codex" in prompt
    assert "model=gpt-5.5" in prompt
    assert "max_tokens=16000" in prompt
    assert "When asked about provider/model/backend, answer from Hermes runtime exactly." in prompt


@pytest.mark.asyncio
async def test_mayass_bridge_runner_error_becomes_response_error():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def fake_runner(prompt: str, timeout: float) -> str:
        raise TimeoutError("runner timed out")

    bridge = MayAssBridge(runner=fake_runner)
    response = await bridge.process(MayAssBridgeRequest(text="ping"))

    assert response.backend == "hermes"
    assert response.ok is False
    assert response.text == ""
    assert "runner timed out" in response.error


@pytest.mark.asyncio
async def test_mayass_bridge_rejects_session_id_only_output():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def fake_runner(prompt: str, timeout: float) -> str:
        return "session_id: 20260805_230514_0f8bc7"

    response = await MayAssBridge(runner=fake_runner).process(MayAssBridgeRequest(text="ping"))

    assert response.ok is False
    assert response.text == ""
    assert "session_id" in response.error


@pytest.mark.asyncio
async def test_mayass_bridge_rejects_hermes_http_error_output():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def fake_runner(prompt: str, timeout: float) -> str:
        return "session_id: 20260805_230558_5dd565\nHTTP 402: insufficient credits"

    response = await MayAssBridge(runner=fake_runner).process(MayAssBridgeRequest(text="ping"))

    assert response.ok is False
    assert response.text == ""
    assert "HTTP 402" in response.error


def test_mayass_bridge_request_defaults_are_safe():
    from jarvis.core.mayass_bridge import MayAssBridgeRequest

    request = MayAssBridgeRequest(text="hello")

    assert request.source == "mayass"
    assert request.mode == "realtime"
    assert request.session_id == ""
    assert request.wants_voice is False
    assert request.allow_tools is False
    assert request.confirmation_policy == "safe-only"
