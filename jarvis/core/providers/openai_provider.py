"""OpenAI backend on the Responses API.

Design notes:
- ``store=False`` plus ``include=["reasoning.encrypted_content"]``: OpenAI
  keeps no conversation state, and reasoning items are replayed encrypted
  between tool-loop iterations.
- The static system prompt goes in ``instructions`` and tool definitions
  keep a deterministic order, so the prefix stays cacheable. Per-request
  context (date, location) is a developer message placed just before the
  latest user turn.
- ``max_retries=0`` on the client: JARVIS's own retry layer handles retries.
  Stacking both multiplied attempts (up to 12 before this change).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from jarvis.core.providers.base import (
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

logger = logging.getLogger("jarvis.providers.openai")

_INCLUDE = ["reasoning.encrypted_content"]
_ITERATION_LIMIT_TEXT = "I hit my processing limit. Let me know if you would like to continue."


def _usage_from(resp_usage: Any, model: str) -> Usage:
    """OpenAI's input_tokens includes cached and cache-write tokens; split them out."""
    if resp_usage is None:
        return Usage(model=model)
    details = getattr(resp_usage, "input_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0)
    written = int(getattr(details, "cache_write_tokens", 0) or 0)
    total_in = int(getattr(resp_usage, "input_tokens", 0) or 0)
    return Usage(
        model=model,
        input_tokens=max(0, total_in - cached - written),
        output_tokens=int(getattr(resp_usage, "output_tokens", 0) or 0),
        cache_read_tokens=cached,
        cache_write_tokens=written,
    )


def to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert a JARVIS tool schema ({name, description, input_schema}) to a Responses function tool.

    ``strict`` stays off: the existing schemas use optional properties, which
    strict mode would force to be required.
    """
    converted: dict[str, Any] = {
        "type": "function",
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        "strict": False,
    }
    if tool.get("defer_loading"):
        converted["defer_loading"] = True
    return converted


def _refusal_text(resp: Any) -> str:
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", "") == "message":
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", "") == "refusal":
                    return str(getattr(part, "refusal", "") or "")
    return ""


def _response_text(resp: Any) -> str:
    return (getattr(resp, "output_text", "") or "").strip() or _refusal_text(resp)


def _as_input_item(item: Any) -> dict[str, Any]:
    """Replay a response output item as input for the next request."""
    if isinstance(item, dict):
        return item
    return cast(dict[str, Any], item.model_dump(mode="json", exclude_none=True))


def _tool_output(result: Any) -> str | list[dict[str, Any]]:
    """Function-call output: plain text, or text plus images for image results."""
    if isinstance(result, list) and any(
        isinstance(b, dict) and b.get("type") == "image" for b in result
    ):
        parts: list[dict[str, Any]] = []
        for block in result:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "image":
                source = block.get("source", {})
                data_url = f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
                parts.append({"type": "input_image", "image_url": data_url, "detail": "auto"})
            elif block.get("type") == "text":
                parts.append({"type": "input_text", "text": str(block.get("text", ""))})
        return parts
    return tool_result_text(result)


class OpenAIProvider:
    """Cloud backend for OpenAI models (GPT-6 family) via the Responses API."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 120.0,
        client: Any = None,
        retry: RetryFn | None = None,
    ):
        self._api_key = api_key
        self._timeout = timeout
        self._client = client
        self._retry = retry

    def is_configured(self) -> bool:
        return bool(self._api_key) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise ProviderError("OPENAI_API_KEY is not set.")
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise ProviderError("openai package not installed. Run: pip install openai") from exc
            self._client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout, max_retries=0)
        return self._client

    # ── request building ────────────────────────────────────────────────

    @staticmethod
    def _input(system: SystemPrompt, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = [
            {"role": m["role"], "content": m["content"]} for m in messages[:-1]
        ]
        if system.dynamic:
            items.append({"role": "developer", "content": system.dynamic})
        if messages:
            last = messages[-1]
            items.append({"role": last["role"], "content": last["content"]})
        return items

    @staticmethod
    def _base_kwargs(system: SystemPrompt, spec: TierSpec) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "instructions": system.static,
            "max_output_tokens": spec.max_output_tokens,
            "store": False,
            "include": _INCLUDE,
        }
        if spec.effort:
            kwargs["reasoning"] = {"effort": spec.effort}
        if spec.temperature is not None:
            kwargs["temperature"] = spec.temperature
        return kwargs

    async def _create(self, **kwargs: Any) -> Any:
        client = self._get_client()

        async def call() -> Any:
            return await client.responses.create(**kwargs)

        try:
            if self._retry is not None:
                return await self._retry(call, "openai.responses")
            return await call()
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

    # ── public API ──────────────────────────────────────────────────────

    async def health(self) -> bool:
        if not self.is_configured():
            return False
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except Exception as exc:
            logger.warning("OpenAI health check failed: %s", exc)
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
        kwargs["input"] = self._input(system, messages)
        if json_schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("title", "result"),
                    "schema": json_schema,
                    "strict": True,
                }
            }
        resp = await self._create(**kwargs)
        return _response_text(resp), _usage_from(getattr(resp, "usage", None), spec.model)

    async def describe_image(
        self, *, image_b64: str, media_type: str, prompt: str, spec: TierSpec
    ) -> tuple[str, Usage]:
        kwargs = self._base_kwargs(SystemPrompt(static="You describe screenshots accurately and concisely."), spec)
        kwargs["input"] = [{
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": f"data:{media_type};base64,{image_b64}", "detail": "auto"},
                {"type": "input_text", "text": prompt},
            ],
        }]
        resp = await self._create(**kwargs)
        return _response_text(resp), _usage_from(getattr(resp, "usage", None), spec.model)

    async def stream(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        on_usage: UsageSink,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        kwargs = self._base_kwargs(system, spec)
        kwargs["input"] = self._input(system, messages)
        try:
            async with client.responses.stream(**kwargs) as stream:
                async for event in stream:
                    if getattr(event, "type", "") == "response.output_text.delta":
                        yield event.delta
                final = await stream.get_final_response()
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        on_usage(_usage_from(getattr(final, "usage", None), spec.model))

    def _tool_kwargs(self, system: SystemPrompt, spec: TierSpec, tools: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs = self._base_kwargs(system, spec)
        openai_tools = [to_openai_tool(t) for t in tools]
        if any(t.get("defer_loading") for t in openai_tools):
            openai_tools.append({"type": "tool_search"})
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["parallel_tool_calls"] = True
        return kwargs

    async def _advance(
        self,
        resp: Any,
        input_items: list[dict[str, Any]],
        log: list[dict[str, Any]],
        executor: ToolExecutor,
        spec: TierSpec,
        on_usage: UsageSink,
    ) -> ToolLoopResult | None:
        """Process one response: run its tool calls, or return the final result."""
        on_usage(_usage_from(getattr(resp, "usage", None), spec.model))
        output = list(getattr(resp, "output", None) or [])
        calls = [item for item in output if getattr(item, "type", "") == "function_call"]
        input_items.extend(_as_input_item(item) for item in output)
        logger.info("Tool loop [%s]: %d call(s), status=%s", spec.model, len(calls), getattr(resp, "status", ""))

        if not calls:
            incomplete = getattr(resp, "status", "") == "incomplete"
            text = _response_text(resp)
            if not text and incomplete:
                text = "I hit a processing limit. Could you simplify the request?"
            return ToolLoopResult(text=text, tool_calls=log, completed=not incomplete)

        results = await asyncio.gather(*(self._run_call(call, executor) for call in calls))
        for call, (tool_input, result) in zip(calls, results, strict=True):
            log.append({"name": call.name, "input": tool_input, "result": tool_result_text(result)[:2000]})
            input_items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": _tool_output(result),
            })
        return None

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
        kwargs = self._tool_kwargs(system, spec, tools)
        input_items = self._input(system, messages)
        log: list[dict[str, Any]] = []

        for _ in range(max_iterations):
            resp = await self._create(input=input_items, **kwargs)
            result = await self._advance(resp, input_items, log, executor, spec, on_usage)
            if result is not None:
                return result

        return ToolLoopResult(text=_ITERATION_LIMIT_TEXT, tool_calls=log, completed=False)

    async def stream_tools(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        executor: ToolExecutor,
        spec: TierSpec,
        max_iterations: int,
        on_usage: UsageSink,
        on_result: Callable[[ToolLoopResult], None],
    ) -> AsyncIterator[str]:
        """Tool loop that yields answer text as it is generated.

        Tool calls still run between model turns; ``on_result`` receives the
        final ToolLoopResult. Not retried: text may already have been shown.
        """
        client = self._get_client()
        kwargs = self._tool_kwargs(system, spec, tools)
        input_items = self._input(system, messages)
        log: list[dict[str, Any]] = []

        for _ in range(max_iterations):
            try:
                async with client.responses.stream(input=input_items, **kwargs) as stream:
                    async for event in stream:
                        if getattr(event, "type", "") == "response.output_text.delta":
                            yield event.delta
                    resp = await stream.get_final_response()
            except Exception as exc:
                raise ProviderError(str(exc)) from exc
            result = await self._advance(resp, input_items, log, executor, spec, on_usage)
            if result is not None:
                on_result(result)
                return

        yield _ITERATION_LIMIT_TEXT
        on_result(ToolLoopResult(text=_ITERATION_LIMIT_TEXT, tool_calls=log, completed=False))

    @staticmethod
    async def _run_call(call: Any, executor: ToolExecutor) -> tuple[dict, Any]:
        try:
            tool_input = json.loads(call.arguments or "{}")
            if not isinstance(tool_input, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            return {}, f"Error: invalid arguments for {call.name}: {exc}"
        logger.info("Tool call: %s(%s)", call.name, str(tool_input)[:200])
        try:
            return tool_input, await executor(call.name, tool_input)
        except Exception as exc:
            logger.error("Tool execution error (%s): %s", call.name, exc)
            return tool_input, f"Error executing {call.name}: {exc}"

    async def count_tokens(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "instructions": system.static,
            "input": self._input(system, messages),
        }
        if tools:
            kwargs["tools"] = [to_openai_tool(t) for t in tools]
        try:
            result = await client.responses.input_tokens.count(**kwargs)
        except Exception as exc:
            logger.debug("OpenAI token counting failed: %s", exc)
            return None
        return int(getattr(result, "input_tokens", 0) or 0)
