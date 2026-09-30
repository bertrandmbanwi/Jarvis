"""Batch API wrapper for non-urgent work (50% cheaper on both providers).

Uses the active provider: OpenAI Batch (JSONL file of ``/v1/responses``
requests) or Anthropic Message Batches.
"""
from __future__ import annotations

import io
import json
import time
from typing import Any

from jarvis.config import settings
from jarvis.core.providers import tier_specs

MAX_BATCH_PROMPTS = 1000


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
