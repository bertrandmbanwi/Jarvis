"""Batch API wrapper for non-urgent work (50% cheaper on both providers).

Uses the active provider: OpenAI Batch (JSONL file of ``/v1/responses``
requests) or Anthropic Message Batches.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from typing import Any

from jarvis.config import settings
from jarvis.core.providers import tier_specs

logger = logging.getLogger("jarvis.batch")

MAX_BATCH_PROMPTS = 1000
BATCH_DISCOUNT = 0.5  # both providers bill batch requests at half price
_FINISHED = {"completed", "failed", "expired", "cancelled", "canceled", "ended"}


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _custom_ids(prompts: list[str]) -> list[str]:
    stamp = int(time.time())
    return [f"jarvis-{stamp}-{idx}" for idx in range(len(prompts))]


def _openai_client() -> Any:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, max_retries=2)


def _anthropic_client() -> Any:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
    import anthropic

    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=2)


def openai_batch_jsonl(prompts: list[str], tier: str) -> bytes:
    """One Responses API request per line, as the OpenAI Batch API expects."""
    specs = tier_specs("openai")
    spec = specs.get(tier, specs["brain"])
    static, dynamic = settings.get_system_prompt_parts()
    lines = []
    for custom_id, prompt in zip(_custom_ids(prompts), prompts, strict=True):
        body: dict[str, Any] = {
            "model": spec.model,
            "instructions": static,
            "input": [
                {"role": "developer", "content": dynamic},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": spec.max_output_tokens,
            "store": False,
        }
        if spec.effort:
            body["reasoning"] = {"effort": spec.effort}
        lines.append(json.dumps({"custom_id": custom_id, "method": "POST", "url": "/v1/responses", "body": body}))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _describe(batch: Any, provider: str) -> dict[str, Any]:
    if provider == "openai":
        return {
            "provider": "openai",
            "id": getattr(batch, "id", ""),
            "processing_status": getattr(batch, "status", ""),
            "request_counts": _plain(getattr(batch, "request_counts", None)),
            "created_at": str(getattr(batch, "created_at", "")),
            "output_file_id": getattr(batch, "output_file_id", None),
        }
    return {
        "provider": "anthropic",
        "id": getattr(batch, "id", ""),
        "processing_status": getattr(batch, "processing_status", ""),
        "request_counts": _plain(getattr(batch, "request_counts", None)),
        "created_at": str(getattr(batch, "created_at", "")),
        "results_url": getattr(batch, "results_url", None),
    }


async def create_batch(prompts: list[str], tier: str = "brain") -> dict[str, Any]:
    """Create a batch on the active provider and return its metadata."""
    if not prompts:
        raise ValueError("At least one prompt is required.")
    prompts = prompts[:MAX_BATCH_PROMPTS]
    provider = settings.LLM_PROVIDER

    if provider == "anthropic":
        specs = tier_specs("anthropic")
        spec = specs.get(tier, specs["brain"])
        requests = [
            {
                "custom_id": custom_id,
                "params": {
                    "model": spec.model,
                    "max_tokens": spec.max_output_tokens,
                    "system": settings.get_system_prompt_blocks(cache_static=True),
                    "messages": [{"role": "user", "content": prompt}],
                },
            }
            for custom_id, prompt in zip(_custom_ids(prompts), prompts, strict=True)
        ]
        batch = await _anthropic_client().messages.batches.create(requests=requests)
        return _describe(batch, provider)

    client = _openai_client()
    upload = await client.files.create(
        file=("jarvis-batch.jsonl", io.BytesIO(openai_batch_jsonl(prompts, tier))),
        purpose="batch",
    )
    batch = await client.batches.create(
        input_file_id=upload.id, endpoint="/v1/responses", completion_window="24h"
    )
    return _describe(batch, "openai")


async def get_batch(batch_id: str) -> dict[str, Any]:
    """Retrieve batch status."""
    if settings.LLM_PROVIDER == "anthropic":
        return _describe(await _anthropic_client().messages.batches.retrieve(batch_id), "anthropic")
    return _describe(await _openai_client().batches.retrieve(batch_id), "openai")


async def cancel_batch(batch_id: str) -> dict[str, Any]:
    """Cancel a batch."""
    if settings.LLM_PROVIDER == "anthropic":
        return _describe(await _anthropic_client().messages.batches.cancel(batch_id), "anthropic")
    return _describe(await _openai_client().batches.cancel(batch_id), "openai")


def _log_batch_cost(usage: Any, elapsed: float) -> None:
    try:
        from jarvis.core.cost_tracker import log_request

        log_request(
            model=usage.model, tier="batch",
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens, cache_creation_tokens=usage.cache_write_tokens,
            cost_usd=usage.cost(settings.MODEL_PRICING.get(usage.model, {})) * BATCH_DISCOUNT,
            elapsed_seconds=elapsed, user_input_preview="",
        )
    except Exception as exc:
        logger.debug("Batch cost log failed: %s", exc)


def openai_result_text(jsonl: str) -> tuple[str, dict[str, Any]]:
    """Text and usage from the first line of an OpenAI batch output file."""
    line = next((ln for ln in jsonl.splitlines() if ln.strip()), "")
    if not line:
        return "", {}
    body = (json.loads(line).get("response") or {}).get("body") or {}
    parts = [
        part.get("text", "")
        for item in body.get("output", []) if item.get("type") == "message"
        for part in item.get("content", []) if part.get("type") == "output_text"
    ]
    return "".join(parts).strip(), body.get("usage") or {}


async def _fetch_result(batch_id: str, provider: str, elapsed: float) -> str:
    if provider == "anthropic":
        from jarvis.core.providers.anthropic_provider import _text_of, _usage_from

        async for entry in await _anthropic_client().messages.batches.results(batch_id):
            if entry.result.type != "succeeded":
                raise RuntimeError(f"Batch request {entry.result.type}")
            message = entry.result.message
            _log_batch_cost(_usage_from(message.usage, message.model), elapsed)
            return _text_of(message)
        raise RuntimeError("Batch returned no results")

    from jarvis.core.providers import Usage

    client = _openai_client()
    batch = await client.batches.retrieve(batch_id)
    if not batch.output_file_id:
        raise RuntimeError(f"Batch finished without output (status {batch.status})")
    content = await client.files.content(batch.output_file_id)
    text, usage = openai_result_text(content.text)
    details = usage.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens", 0) or 0)
    _log_batch_cost(
        Usage(
            model=tier_specs("openai")["brain"].model,
            input_tokens=max(0, int(usage.get("input_tokens", 0) or 0) - cached),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cache_read_tokens=cached,
        ),
        elapsed,
    )
    return text


async def run_prompt(prompt: str, tier: str = "brain", *, poll_s: float = 30.0, timeout_s: float = 86400.0) -> str:
    """Run one prompt through the Batch API and wait for its result.

    Half the price of a normal request, but no tools, and the result can
    take minutes to hours. Meant for scheduled, non-urgent workflow prompts.
    """
    provider = settings.LLM_PROVIDER
    start = time.time()
    batch_id = (await create_batch([prompt], tier=tier))["id"]
    while True:
        status = str((await get_batch(batch_id))["processing_status"])
        if status in _FINISHED:
            break
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Batch {batch_id} did not finish within {timeout_s:.0f}s")
        await asyncio.sleep(poll_s)
    if status not in ("completed", "ended"):
        raise RuntimeError(f"Batch {batch_id} {status}")
    return await _fetch_result(batch_id, provider, time.time() - start)
