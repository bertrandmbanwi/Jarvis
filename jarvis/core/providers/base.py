"""Provider-neutral types shared by the cloud LLM backends."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

# (tool_name, tool_input) -> result. Results may be str, dict, or content blocks.
ToolExecutor = Callable[[str, dict], Awaitable[Any]]
UsageSink = Callable[["Usage"], None]
# Wraps one raw SDK call with retries: (call, context) -> result.
RetryFn = Callable[[Callable[[], Awaitable[Any]], str], Awaitable[Any]]

MAX_TOOL_RESULT_CHARS = 8000


@dataclass(frozen=True)
class SystemPrompt:
    """System instructions split for prompt caching.

    ``static`` never changes between requests and belongs in the cached
    prefix. ``dynamic`` (date, time, location) changes every request, so each
    provider places it after the cacheable content.
    """

    static: str
    dynamic: str = ""

    @property
    def full(self) -> str:
        return self.static + self.dynamic


@dataclass(frozen=True)
class TierSpec:
    """How one JARVIS tier (fast / brain / deep) calls its model."""

    model: str
    max_output_tokens: int
    effort: str | None = None  # reasoning effort; None = provider default
    temperature: float | None = None  # None = don't send (reasoning models reject it)


@dataclass(frozen=True)
class Usage:
    """Token usage for one API call, normalised across providers.

    ``input_tokens`` counts only uncached, non-cache-write input, so the
    four token buckets are disjoint and each is billed at exactly one rate.
    """

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def cost(self, pricing: dict[str, float]) -> float:
        if not pricing:
            return 0.0
        return (
            self.input_tokens * pricing["input"]
            + self.output_tokens * pricing["output"]
            + self.cache_write_tokens * pricing["cache_write"]
            + self.cache_read_tokens * pricing["cache_read"]
        ) / 1_000_000


@dataclass
class ToolLoopResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # False when the loop stopped early (iteration cap, output truncated).
    completed: bool = True


class ProviderError(RuntimeError):
    """A provider call failed after the SDK gave up (network, 4xx/5xx, refusal)."""


class CloudProvider(Protocol):
    """Interface every cloud backend implements. Messages are plain
    ``{"role": "user"|"assistant", "content": str}`` dicts."""

    name: str

    def is_configured(self) -> bool: ...

    async def health(self) -> bool: ...

    async def complete(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]: ...

    async def describe_image(
        self, *, image_b64: str, media_type: str, prompt: str, spec: TierSpec
    ) -> tuple[str, Usage]: ...

    def stream(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        on_usage: UsageSink,
    ) -> AsyncIterator[str]: ...

    async def run_tools(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        executor: ToolExecutor,
        spec: TierSpec,
        max_iterations: int,
        on_usage: UsageSink,
    ) -> ToolLoopResult: ...

    async def count_tokens(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None: ...


def tool_result_text(result: Any) -> str:
    """Render a tool result as bounded text for providers that take strings."""
    if isinstance(result, str):
        text = result
    elif isinstance(result, list):
        parts = []
        for block in result:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict) and block.get("type") == "image":
                parts.append("[image]")
            else:
                parts.append(str(block))
        text = "\n".join(parts)
    else:
        import json

        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(result)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
    return text
