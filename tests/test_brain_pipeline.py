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
    b.memory.get_enriched_context.return_value = ""
    b.planner.should_decompose = AsyncMock(return_value=False)
    b.agent.execute = AsyncMock(return_value="agent answer")
    b.success_tracker = MagicMock()
    return b


@pytest.mark.asyncio
async def test_streaming_agent_path_runs_the_same_executor_as_process(brain, monkeypatch):
    monkeypatch.setattr(brain_module, "_select_tier", lambda text: "brain")
    streamed = [t async for t in brain.process_stream("summarise my inbox")]
    assert streamed == ["agent answer"]
    assert await brain.process("summarise my inbox") == "agent answer"
    assert brain.agent.execute.await_count == 2  # QA-verified path on both entry points
    assert [t.role for t in brain.conversation] == ["user", "assistant"] * 2
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
