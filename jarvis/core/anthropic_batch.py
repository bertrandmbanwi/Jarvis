"""Thin wrapper around Anthropic Message Batches for non-urgent work."""
from __future__ import annotations

import time
import uuid
from typing import Any

from jarvis.config import settings
from jarvis.core.llm import TIER_CONFIG, _get_anthropic_client


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _batch_request(prompt: str, tier: str, custom_id: str | None = None) -> dict[str, Any]:
    config = TIER_CONFIG.get(tier, TIER_CONFIG["brain"])
    return {
        "custom_id": custom_id or f"jarvis-{uuid.uuid4().hex[:20]}",
        "params": {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "temperature": config["temperature"],
            "system": settings.get_system_prompt_blocks(cache_static=True),
            "messages": [{"role": "user", "content": prompt}],
        },
    }


async def create_batch(prompts: list[str], tier: str = "brain") -> dict[str, Any]:
    """Create an Anthropic Message Batch and return provider metadata."""
    client = _get_anthropic_client()
    if client is None:
        raise RuntimeError("Anthropic client is not configured.")
    if not prompts:
        raise ValueError("At least one prompt is required.")

    requests = [
        _batch_request(prompt, tier, custom_id=f"jarvis-{int(time.time())}-{idx}")
        for idx, prompt in enumerate(prompts[:1000])
    ]
    batch = await client.messages.batches.create(requests=requests)
    return {
        "id": getattr(batch, "id", ""),
        "type": getattr(batch, "type", "message_batch"),
        "processing_status": getattr(batch, "processing_status", ""),
        "request_counts": _plain(getattr(batch, "request_counts", None)),
        "created_at": str(getattr(batch, "created_at", "")),
        "expires_at": str(getattr(batch, "expires_at", "")),
    }


async def get_batch(batch_id: str) -> dict[str, Any]:
    """Retrieve Anthropic Message Batch status."""
    client = _get_anthropic_client()
    if client is None:
        raise RuntimeError("Anthropic client is not configured.")
    batch = await client.messages.batches.retrieve(batch_id)
    return {
        "id": getattr(batch, "id", ""),
        "type": getattr(batch, "type", "message_batch"),
        "processing_status": getattr(batch, "processing_status", ""),
        "request_counts": _plain(getattr(batch, "request_counts", None)),
        "created_at": str(getattr(batch, "created_at", "")),
        "ended_at": str(getattr(batch, "ended_at", "")),
        "results_url": getattr(batch, "results_url", None),
    }


async def cancel_batch(batch_id: str) -> dict[str, Any]:
    """Cancel an Anthropic Message Batch."""
    client = _get_anthropic_client()
    if client is None:
        raise RuntimeError("Anthropic client is not configured.")
    batch = await client.messages.batches.cancel(batch_id)
    return {
        "id": getattr(batch, "id", ""),
        "processing_status": getattr(batch, "processing_status", ""),
        "request_counts": _plain(getattr(batch, "request_counts", None)),
    }
