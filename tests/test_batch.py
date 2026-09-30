"""Batch API runner for scheduled workflow prompts."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis.config import settings
from jarvis.core import batch


def test_openai_batch_jsonl_targets_responses_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    lines = batch.openai_batch_jsonl(["one", "two"], "brain").decode().strip().splitlines()
    first = json.loads(lines[0])
    assert len(lines) == 2 and first["url"] == "/v1/responses" and first["method"] == "POST"
    assert first["body"]["store"] is False and first["body"]["input"][-1] == {"role": "user", "content": "one"}


def test_openai_result_text_reads_output_message():
    line = json.dumps({"custom_id": "x", "response": {"status_code": 200, "body": {
        "output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "Done."}]}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }}})
    assert batch.openai_result_text(line + "\n") == ("Done.", {"input_tokens": 10, "output_tokens": 2})
    assert batch.openai_result_text("") == ("", {})


@pytest.mark.asyncio
async def test_run_prompt_polls_until_complete_and_logs_half_price(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(batch, "create_batch", AsyncMock(return_value={"id": "b1"}))
    statuses = iter(["validating", "in_progress", "completed"])
    monkeypatch.setattr(batch, "get_batch", AsyncMock(side_effect=lambda _id: {"processing_status": next(statuses)}))
    output = json.dumps({"response": {"body": {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "Summary."}]}],
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0, "input_tokens_details": {"cached_tokens": 0}},
    }}})
    client = SimpleNamespace(
        batches=SimpleNamespace(retrieve=AsyncMock(return_value=SimpleNamespace(output_file_id="f1", status="completed"))),
        files=SimpleNamespace(content=AsyncMock(return_value=SimpleNamespace(text=output))),
    )
    monkeypatch.setattr(batch, "_openai_client", lambda: client)
    logged = {}
    from jarvis.core import cost_tracker

    monkeypatch.setattr(cost_tracker, "log_request", lambda **kw: logged.update(kw))

    assert await batch.run_prompt("summarise", poll_s=0) == "Summary."
    assert batch.get_batch.await_count == 3
    full_price = settings.MODEL_PRICING[logged["model"]]["input"]
    assert logged["cost_usd"] == pytest.approx(full_price * 0.5) and logged["tier"] == "batch"


@pytest.mark.asyncio
async def test_run_prompt_raises_when_batch_fails(monkeypatch):
    monkeypatch.setattr(batch, "create_batch", AsyncMock(return_value={"id": "b1"}))
    monkeypatch.setattr(batch, "get_batch", AsyncMock(return_value={"processing_status": "failed"}))
    with pytest.raises(RuntimeError):
        await batch.run_prompt("x", poll_s=0)
