"""Cloud LLM providers behind one interface (OpenAI default, Anthropic optional)."""
from __future__ import annotations

import os

from jarvis.config import settings
from jarvis.core.providers.base import (
    CloudProvider,
    ProviderError,
    SystemPrompt,
    TierSpec,
    ToolLoopResult,
    Usage,
)

__all__ = [
    "CloudProvider",
    "ProviderError",
    "SystemPrompt",
    "TierSpec",
    "ToolLoopResult",
    "Usage",
    "build_provider",
    "provider_api_key",
    "tier_specs",
    "vision_spec",
]


async def _retry(call, context: str):
    from jarvis.core.hardening import API_RETRY_POLICY, retry_with_backoff

    return await retry_with_backoff(call, policy=API_RETRY_POLICY, context=context)


def build_provider(name: str | None = None) -> CloudProvider:
    """Create the configured provider from current settings."""
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "local":
        from jarvis.core.providers.local_provider import LocalProvider

        return LocalProvider(settings.LOCAL_LLM_BASE_URL, tool_model=settings.LOCAL_LLM_MODEL, retry=_retry)
    if name == "anthropic":
        from jarvis.core.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            settings.ANTHROPIC_API_KEY,
            cache_ttl=settings.ANTHROPIC_PROMPT_CACHE_TTL,
            cache_tools=settings.ANTHROPIC_CACHE_TOOLS,
            retry=_retry,
        )
    from jarvis.core.providers.openai_provider import OpenAIProvider

    return OpenAIProvider(settings.OPENAI_API_KEY, retry=_retry)


def provider_api_key(name: str | None = None) -> str:
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "local":
        return settings.LOCAL_LLM_BASE_URL
    return settings.ANTHROPIC_API_KEY if name == "anthropic" else settings.OPENAI_API_KEY


def tier_specs(name: str | None = None) -> dict[str, TierSpec]:
    """Model, output budget and effort for each tier, read from settings at call time."""
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "local":
        return {
            "fast": TierSpec(settings.LOCAL_FAST_MODEL, settings.LOCAL_MAX_OUTPUT_TOKENS),
            "brain": TierSpec(settings.LOCAL_LLM_MODEL, settings.LOCAL_MAX_OUTPUT_TOKENS),
            "deep": TierSpec(settings.LOCAL_LLM_MODEL, settings.LOCAL_MAX_OUTPUT_TOKENS),
        }
    if name == "anthropic":
        return {
            "fast": TierSpec(settings.CLAUDE_FAST_MODEL, settings.CLAUDE_FAST_MAX_TOKENS,
                             temperature=settings.CLAUDE_FAST_TEMPERATURE),
            "brain": TierSpec(settings.CLAUDE_BRAIN_MODEL, settings.CLAUDE_BRAIN_MAX_TOKENS,
                              temperature=settings.CLAUDE_BRAIN_TEMPERATURE),
            "deep": TierSpec(settings.CLAUDE_DEEP_MODEL, settings.CLAUDE_DEEP_MAX_TOKENS,
                             effort="high", temperature=settings.CLAUDE_DEEP_TEMPERATURE),
        }
    return {
        "fast": TierSpec(settings.OPENAI_FAST_MODEL, settings.OPENAI_FAST_MAX_OUTPUT_TOKENS,
                         effort=settings.OPENAI_FAST_EFFORT),
        "brain": TierSpec(settings.OPENAI_BRAIN_MODEL, settings.OPENAI_BRAIN_MAX_OUTPUT_TOKENS,
                          effort=settings.OPENAI_BRAIN_EFFORT),
        "deep": TierSpec(settings.OPENAI_DEEP_MODEL, settings.OPENAI_DEEP_MAX_OUTPUT_TOKENS,
                         effort=settings.OPENAI_DEEP_EFFORT),
    }


def vision_spec(name: str | None = None) -> TierSpec:
    """Model settings for screenshot analysis."""
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "local":
        return TierSpec(os.getenv("LOCAL_VISION_MODEL", settings.LOCAL_LLM_MODEL), 1024)
    if name == "anthropic":
        return TierSpec(settings.CLAUDE_FAST_MODEL, 1024)
    return TierSpec(settings.OPENAI_VISION_MODEL, 2048, effort="low")
