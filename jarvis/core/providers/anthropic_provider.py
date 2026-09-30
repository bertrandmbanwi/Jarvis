"""Anthropic (Claude) backend on the Messages API. Optional since OpenAI became the default."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from jarvis.core.providers.base import (
    MAX_TOOL_RESULT_CHARS,
    ProviderError,
    RetryFn,
    SystemPrompt,
    TierSpec,
    ToolExecutor,
    ToolLoopResult,
    Usage,
    UsageSink,
    tool_result_text,
)

logger = logging.getLogger("jarvis.providers.anthropic")

_VALID_CONTENT_BLOCK_TYPES = {"text", "image", "document", "search_result"}


def accepts_sampling_params(model: str) -> bool:
    """Claude Sonnet 5 / Opus 5+ reject temperature with a 400; Haiku 4.5 and 4.x accept it."""
    return model.startswith("claude-haiku-4") or "-4-" in model


def _usage_from(resp_usage: Any, model: str) -> Usage:
    """Anthropic's input_tokens already excludes cache reads and writes."""
    if resp_usage is None:
        return Usage(model=model)
    return Usage(
        model=model,
        input_tokens=int(getattr(resp_usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(resp_usage, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(resp_usage, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(getattr(resp_usage, "cache_creation_input_tokens", 0) or 0),
    )


def _tool_result_content(result: Any) -> str | list:
    """Keep valid content-block lists (e.g. images); stringify everything else."""
    if (
        isinstance(result, list)
        and result
        and all(isinstance(b, dict) and b.get("type") in _VALID_CONTENT_BLOCK_TYPES for b in result)
    ):
        return result
    return tool_result_text(result)[: MAX_TOOL_RESULT_CHARS + 20]


def _text_of(resp: Any) -> str:
    return "\n".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()


class AnthropicProvider:
    """Cloud backend for Claude models."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        *,
        cache_ttl: str = "5m",
        cache_tools: bool = True,
        timeout: float = 120.0,
        client: Any = None,
        retry: RetryFn | None = None,
    ):
        self._api_key = api_key
        self._cache_ttl = cache_ttl
        self._cache_tools = cache_tools
        self._timeout = timeout
        self._client = client
        self._retry = retry

    def is_configured(self) -> bool:
        return bool(self._api_key) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise ProviderError("ANTHROPIC_API_KEY is not set.")
            try:
                import anthropic
            except ImportError as exc:
                raise ProviderError("anthropic package not installed. Run: pip install anthropic") from exc
            self._client = anthropic.AsyncAnthropic(
                api_key=self._api_key, timeout=self._timeout, max_retries=0
            )
        return self._client

    # ── request building ────────────────────────────────────────────────

    def _cache_control(self) -> dict[str, str]:
        control = {"type": "ephemeral"}
        if self._cache_ttl == "1h":
            control["ttl"] = "1h"
        return control

    def _system_blocks(self, system: SystemPrompt) -> list[dict[str, Any]]:
        static: dict[str, Any] = {"type": "text", "text": system.static}
        if len(system.static) >= 1024:
            static["cache_control"] = self._cache_control()
        blocks = [static]
        if system.dynamic:
            blocks.append({"type": "text", "text": system.dynamic})
        return blocks

    def _tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared = [
            {k: v for k, v in tool.items() if k in ("name", "description", "input_schema")}
            for tool in tools
        ]
        if prepared and self._cache_tools:
            prepared[-1] = {**prepared[-1], "cache_control": self._cache_control()}
        return prepared

    def _base_kwargs(self, system: SystemPrompt, spec: TierSpec) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "max_tokens": spec.max_output_tokens,
            "system": self._system_blocks(system),
        }
        if spec.temperature is not None and accepts_sampling_params(spec.model):
            kwargs["temperature"] = spec.temperature
        if spec.effort and not spec.model.startswith("claude-haiku-4"):
            kwargs["output_config"] = {"effort": spec.effort}
        return kwargs

    async def _create(self, **kwargs: Any) -> Any:
        client = self._get_client()

        async def call() -> Any:
            return await client.messages.create(**kwargs)

        try:
            if self._retry is not None:
                return await self._retry(call, "anthropic.messages")
            return await call()
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

    # ── public API ──────────────────────────────────────────────────────

    async def health(self) -> bool:
        if not self.is_configured():
            return False
        try:
            await self._get_client().models.list(limit=1)
            return True
        except Exception as exc:
            logger.warning("Anthropic health check failed: %s", exc)
            return False

    async def complete(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        kwargs = self._base_kwargs(system, spec)
        kwargs["messages"] = messages
        if json_schema is not None:
            kwargs.setdefault("output_config", {})["format"] = {"type": "json_schema", "schema": json_schema}
        resp = await self._create(**kwargs)
        if getattr(resp, "stop_reason", "") == "refusal":
            return "I can't help with that request.", _usage_from(resp.usage, spec.model)
        return _text_of(resp), _usage_from(resp.usage, spec.model)

    async def describe_image(
        self, *, image_b64: str, media_type: str, prompt: str, spec: TierSpec
    ) -> tuple[str, Usage]:
        kwargs = self._base_kwargs(SystemPrompt(static="You describe screenshots accurately and concisely."), spec)
        kwargs["messages"] = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }]
        resp = await self._create(**kwargs)
        return _text_of(resp), _usage_from(resp.usage, spec.model)

    async def stream(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        on_usage: UsageSink,
    ) -> AsyncIterator[str]:
        kwargs = self._base_kwargs(system, spec)
        kwargs["messages"] = messages
        try:
            async with self._get_client().messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        on_usage(_usage_from(getattr(final, "usage", None), spec.model))

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
    ) -> ToolLoopResult:
        kwargs = self._base_kwargs(system, spec)
        if tools:
            kwargs["tools"] = self._tools(tools)
        convo: list[dict[str, Any]] = list(messages)
        log: list[dict[str, Any]] = []

        for iteration in range(1, max_iterations + 1):
            resp = await self._create(messages=convo, **kwargs)
            on_usage(_usage_from(resp.usage, spec.model))
            logger.info(
                "Tool loop [iter %d, %s]: stop_reason=%s", iteration, spec.model, resp.stop_reason
            )
            if resp.stop_reason != "tool_use":
                completed = resp.stop_reason in ("end_turn", "stop_sequence")
                text = _text_of(resp)
                if not text:
                    text = (
                        "I can't help with that request."
                        if resp.stop_reason == "refusal"
                        else "I hit a processing limit. Could you simplify the request?"
                    )
                return ToolLoopResult(text=text, tool_calls=log, completed=completed)

            # Keep the full content (including thinking blocks) so the next
            # request can verify the model's reasoning chain.
            convo.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            results = await asyncio.gather(*(self._run_call(b, executor) for b in calls))
            tool_results = []
            for block, (result, failed) in zip(calls, results, strict=True):
                log.append({"name": block.name, "input": block.input, "result": tool_result_text(result)[:2000]})
                entry: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _tool_result_content(result),
                }
                if failed:
                    entry["is_error"] = True
                tool_results.append(entry)
            # All results in one user message, so parallel tool use keeps working.
            convo.append({"role": "user", "content": tool_results})

        return ToolLoopResult(
            text="I hit my processing limit. Let me know if you would like to continue.",
            tool_calls=log,
            completed=False,
        )

    @staticmethod
    async def _run_call(block: Any, executor: ToolExecutor) -> tuple[Any, bool]:
        logger.info("Tool call: %s(%s)", block.name, str(block.input)[:200])
        try:
            return await executor(block.name, block.input), False
        except Exception as exc:
            logger.error("Tool execution error (%s): %s", block.name, exc)
            return f"Error executing {block.name}: {exc}", True

    async def count_tokens(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None:
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "system": self._system_blocks(system),
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = self._tools(tools)
        try:
            result = await self._get_client().messages.count_tokens(**kwargs)
        except Exception as exc:
            logger.debug("Anthropic token counting failed: %s", exc)
            return None
        return int(getattr(result, "input_tokens", 0) or 0)
