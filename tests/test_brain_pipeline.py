"""process() and process_stream() share one pipeline."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.config import settings
from jarvis.core import brain as brain_module
from jarvis.core.brain import JarvisBrain


@pytest.fixture
def brain(monkeypatch):
    b = JarvisBrain()
    b._initialized = True
    monkeypatch.setattr(settings, "LOCAL_FIRST_ENABLED", False)
    monkeypatch.setattr(settings, "MEMORY_ENABLED", False)
    monkeypatch.setattr(b, "_save_turn", lambda turn: None)
    b.memory = MagicMock()
    b.memory.recall_block.return_value = ""
    b.planner.should_decompose = AsyncMock(return_value=False)
    b.agent.execute = AsyncMock(return_value="agent answer")
    b.success_tracker = MagicMock()
    return b


@pytest.mark.asyncio
async def test_agent_replies_stream_in_the_ui_and_are_qa_verified_elsewhere(brain, monkeypatch):
    monkeypatch.setattr(brain_module, "_select_tier", lambda text: "brain")

    async def fake_stream(*args, **kwargs):
        for token in ("agent ", "answer"):
            yield token

    brain.agent.execute_stream = fake_stream
    # Chat UI: tokens as they are written.
    assert [t async for t in brain.process_stream("summarise my inbox")] == ["agent ", "answer"]
    brain.agent.execute.assert_not_awaited()
    # Voice / REST / jobs: whole reply through the QA-verified executor.
    assert await brain.process("summarise my inbox") == "agent answer"
    brain.agent.execute.assert_awaited_once()
    assert [t.content for t in brain.conversation if t.role == "assistant"] == ["agent answer"] * 2
    assert all(t.request_id for t in brain.conversation)


@pytest.mark.asyncio
async def test_chat_path_streams_tokens(brain, monkeypatch):
    monkeypatch.setattr(brain_module, "_select_tier", lambda text: "fast")
    monkeypatch.setattr(brain_module, "_is_chat_only", lambda text: True)

    async def fake_stream(*args, **kwargs):
        for token in ("Hel", "lo"):
            yield token

    brain.llm.chat_stream = fake_stream
    assert [t async for t in brain.process_stream("hi")] == ["Hel", "lo"]
    assert brain.conversation[-1].content == "Hello"


@pytest.mark.asyncio
async def test_shutdown_command_works_on_streaming_path(brain):
    out = [t async for t in brain.process_stream("shut down jarvis")]
    assert "Shutting down" in out[0]
    assert brain._shutdown_requested


@pytest.mark.asyncio
async def test_plan_outcome_is_tracked_on_streaming_path(brain, monkeypatch):
    monkeypatch.setattr(brain_module, "_select_tier", lambda text: "brain")
    brain.planner.should_decompose = AsyncMock(return_value=True)
    plan = SimpleNamespace(status="completed", failed_count=0)

    async def fake_plan(user_input, history, tier):
        brain._last_plan = plan
        return "plan done"

    brain._execute_plan = fake_plan
    monkeypatch.setattr(brain_module, "suggest_followup", lambda **kw: None)
    monkeypatch.setattr(brain_module, "suggest_task_followup", AsyncMock(return_value=None))
    out = [t async for t in brain.process_stream("research and email the results")]
    assert out == ["plan done"]
    brain.success_tracker.log_task.assert_called_once()
    assert brain._last_plan is None
