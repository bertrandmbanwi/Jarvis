"""QA retry must never repeat side-effect tools or fire on an inconclusive verdict."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.agent.executor import AgentExecutor
from jarvis.agent.qa_agent import QAAgent, QAResult
from jarvis.core.permissions import is_side_effect_free

TOOLS = [{"name": "create_note"}, {"name": "send_email"}, {"name": "get_weather"}, {"name": "get_upcoming_events"}]


def _executor(qa_result: QAResult) -> tuple[AgentExecutor, MagicMock]:
    llm = MagicMock()
    llm.chat_with_tools = AsyncMock(
        return_value=("Created the note.", [{"name": "create_note", "input": {}, "result": "ok"}])
    )
    executor = AgentExecutor(llm=llm)
    executor._qa_agent = MagicMock()
    executor._qa_agent.verify = AsyncMock(return_value=qa_result)
    return executor, llm


@pytest.mark.parametrize(
    ("name", "expected"),
    [("get_weather", True), ("get_upcoming_events", True), ("create_note", False), ("send_email", False)],
)
def test_is_side_effect_free(name, expected):
    assert is_side_effect_free(name) is expected


@pytest.mark.asyncio
async def test_inconclusive_qa_does_not_retry():
    executor, llm = _executor(QAResult(False, ["timeout"], "", 1, conclusive=False))
    result = await executor.execute("make a note", tools=TOOLS)
    assert result == "Created the note."
    assert llm.chat_with_tools.await_count == 1


@pytest.mark.asyncio
async def test_failed_qa_retry_only_offers_side_effect_free_tools(monkeypatch):
    # The tool list includes a macOS-only calendar tool; keep it visible on Linux CI.
    monkeypatch.setattr("jarvis.agent.platform_tools.IS_MACOS", True)
    executor, llm = _executor(QAResult(False, ["too vague"], "", 1))
    await executor.execute("make a note", tools=TOOLS)
    assert llm.chat_with_tools.await_count == 2
    retry_kwargs = llm.chat_with_tools.await_args_list[1].kwargs
    assert {t["name"] for t in retry_kwargs["tools"]} == {"get_weather", "get_upcoming_events"}
    assert "do NOT repeat" in retry_kwargs["user_message"]
    assert "create_note: ok" in retry_kwargs["user_message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("names", "qa_runs"),
    [
        (["get_weather"], False),
        (["get_weather", "get_upcoming_events"], False),
        (["get_weather", "get_weather", "get_weather"], True),
        (["get_weather", "create_note"], True),
    ],
)
async def test_qa_is_skipped_only_for_simple_read_only_lookups(monkeypatch, names, qa_runs):
    monkeypatch.setattr("jarvis.agent.platform_tools.IS_MACOS", True)
    executor, llm = _executor(QAResult(True, [], "", 1))
    llm.chat_with_tools.return_value = ("Done.", [{"name": n, "input": {}, "result": "ok"} for n in names])
    await executor.execute("what's the weather", tools=TOOLS)
    assert executor._qa_agent.verify.await_count == (1 if qa_runs else 0)


def test_missing_qa_verdict_is_inconclusive():
    assert QAAgent._result_from(None).conclusive is False
    result = QAAgent._result_from({"passed": False, "issues": ["x"], "summary": "bad"})
    assert result.conclusive is True and result.issues == ["x"]


@pytest.mark.asyncio
async def test_subtask_raises_when_tool_loop_fails():
    from jarvis.core.llm import ToolLoopError

    llm = MagicMock()
    llm.chat_with_tools = AsyncMock(side_effect=ToolLoopError("boom"))
    with pytest.raises(ToolLoopError):
        await AgentExecutor(llm=llm).execute_subtask("do a thing", tools=TOOLS)
    assert llm.chat_with_tools.await_args.kwargs["raise_on_failure"] is True


@pytest.mark.asyncio
async def test_last_plan_is_isolated_per_task():
    import asyncio

    from jarvis.core.brain import JarvisBrain

    brain = JarvisBrain()
    sentinel = object()

    async def set_plan():
        brain._last_plan = sentinel
        await asyncio.sleep(0)
        return brain._last_plan

    async def read_plan():
        await asyncio.sleep(0)
        return brain._last_plan

    set_result, other_result = await asyncio.gather(set_plan(), read_plan())
    assert set_result is sentinel
    assert other_result is None


@pytest.mark.asyncio
async def test_qa_verify_requests_structured_verdict():
    llm = MagicMock()
    llm.chat_json = AsyncMock(return_value={"passed": True, "issues": [], "summary": "ok"})
    result = await QAAgent().verify("task", "output", llm=llm)
    assert result.passed and result.conclusive
    assert llm.chat_json.await_args.args[1]["title"] == "qa_verdict"
