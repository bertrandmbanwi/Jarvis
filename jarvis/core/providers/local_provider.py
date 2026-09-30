"""Local backend: any OpenAI-compatible Chat Completions server, with tool calling.

Defaults to Ollama (``http://localhost:11434/v1``); also works with
``mlx_lm.server`` (MLX on Apple silicon), LM Studio and llama.cpp. Unlike the
plain Ollama fallback in llm.py, this supports tools, so JARVIS keeps its
abilities fully offline. Use a tool-capable model (gpt-oss, qwen3, llama3.1).

The fast tier can run on Apple's on-device Foundation Model (model id
``apple``) through a small Swift helper; see apple_fm.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

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

logger = logging.getLogger("jarvis.providers.local")

APPLE_MODEL = "apple"


def _usage(resp_usage: Any, model: str) -> Usage:
    if resp_usage is None:
        return Usage(model=model)
    return Usage(
        model=model,
        input_tokens=int(getattr(resp_usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(resp_usage, "completion_tokens", 0) or 0),
    )


def to_chat_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        },
    }


class LocalProvider:
    """OpenAI-compatible local server (Ollama, MLX, LM Studio) as a full provider."""

    name = "local"

    def __init__(
        self,
        base_url: str,
        *,
        tool_model: str,
        timeout: float = 300.0,
        client: Any = None,
        retry: RetryFn | None = None,
        apple: Any = None,
    ):
        self._base_url = base_url
        self._tool_model = tool_model  # used whenever the tier asks for the Apple model but needs tools
        self._timeout = timeout
        self._client = client
        self._retry = retry
        self._apple = apple

    def is_configured(self) -> bool:
        return bool(self._base_url) or self._client is not None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            # Local servers ignore the key, but the SDK requires one.
            self._client = AsyncOpenAI(base_url=self._base_url, api_key="local", timeout=self._timeout, max_retries=0)
        return self._client

    def _apple_helper(self) -> Any:
        if self._apple is None:
            from jarvis.core.providers.apple_fm import AppleFoundationModel

            self._apple = AppleFoundationModel()
        return self._apple

    @staticmethod
    def _messages(system: SystemPrompt, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        return [{"role": "system", "content": system.full}, *messages]

    async def _create(self, **kwargs: Any) -> Any:
        client = self._get_client()

        async def call() -> Any:
            return await client.chat.completions.create(**kwargs)

        try:
            if self._retry is not None:
                return await self._retry(call, "local.chat")
            return await call()
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

    async def health(self) -> bool:
        try:
            await self._get_client().models.list()
            return True
        except Exception as exc:
            logger.warning("Local model server unreachable at %s: %s", self._base_url, exc)
            return False

    async def complete(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, Usage]:
        # Apple's model handles plain replies; structured decisions go to the local
        # server model, which enforces the JSON schema (the on-device model
        # misclassified simple requests in testing).
        if spec.model == APPLE_MODEL and json_schema is None:
            apple = self._apple_helper()
            # First use may compile the helper; keep that off the event loop.
            if await asyncio.to_thread(apple.available):
                text = await apple.respond(system.full, messages)
                if text:
                    return text, Usage(model=APPLE_MODEL)
        if spec.model == APPLE_MODEL:
            spec = TierSpec(self._tool_model, spec.max_output_tokens)
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "messages": self._messages(system, messages),
            "max_tokens": spec.max_output_tokens,
        }
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": json_schema.get("title", "result"), "schema": json_schema, "strict": True},
            }
        resp = await self._create(**kwargs)
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        return text.strip(), _usage(getattr(resp, "usage", None), spec.model)

    async def stream(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        on_usage: UsageSink,
    ) -> AsyncIterator[str]:
        if spec.model == APPLE_MODEL and await asyncio.to_thread(self._apple_helper().available):
            async for piece in self._apple_helper().stream(system.full, messages):
                yield piece
            on_usage(Usage(model=APPLE_MODEL))
            return
        model = self._tool_model if spec.model == APPLE_MODEL else spec.model
        try:
            stream = await self._get_client().chat.completions.create(
                model=model, messages=self._messages(system, messages),
                max_tokens=spec.max_output_tokens, stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        on_usage(Usage(model=model))

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
        model = self._tool_model if spec.model == APPLE_MODEL else spec.model
        convo: list[dict[str, Any]] = self._messages(system, messages)
        kwargs: dict[str, Any] = {"model": model, "max_tokens": spec.max_output_tokens}
        if tools:
            kwargs["tools"] = [to_chat_tool(t) for t in tools]
        log: list[dict[str, Any]] = []

        for iteration in range(1, max_iterations + 1):
            resp = await self._create(messages=convo, **kwargs)
            on_usage(_usage(getattr(resp, "usage", None), model))
            message = resp.choices[0].message
            calls = list(message.tool_calls or [])
            logger.info("Local tool loop [iter %d, %s]: %d call(s)", iteration, model, len(calls))
            if not calls:
                truncated = resp.choices[0].finish_reason == "length"
                return ToolLoopResult(text=(message.content or "").strip(), tool_calls=log, completed=not truncated)

            convo.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            })
            results = await asyncio.gather(*(self._run_call(c, executor) for c in calls))
            for call, (tool_input, result) in zip(calls, results, strict=True):
                text = tool_result_text(result)
                log.append({"name": call.function.name, "input": tool_input, "result": text[:2000]})
                convo.append({"role": "tool", "tool_call_id": call.id, "content": text})

        return ToolLoopResult(
            text="I hit my processing limit. Let me know if you would like to continue.",
            tool_calls=log,
            completed=False,
        )

    @staticmethod
    async def _run_call(call: Any, executor: ToolExecutor) -> tuple[dict, Any]:
        name = call.function.name
        try:
            tool_input = json.loads(call.function.arguments or "{}")
            if not isinstance(tool_input, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            return {}, f"Error: invalid arguments for {name}: {exc}"
        try:
            return tool_input, await executor(name, tool_input)
        except Exception as exc:
            logger.error("Tool execution error (%s): %s", name, exc)
            return tool_input, f"Error executing {name}: {exc}"

    async def describe_image(
        self, *, image_b64: str, media_type: str, prompt: str, spec: TierSpec
    ) -> tuple[str, Usage]:
        model = self._tool_model if spec.model == APPLE_MODEL else spec.model
        resp = await self._create(
            model=model,
            max_tokens=spec.max_output_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                ],
            }],
        )
        return (resp.choices[0].message.content or "").strip(), _usage(getattr(resp, "usage", None), model)

    async def count_tokens(
        self,
        *,
        system: SystemPrompt,
        messages: list[dict[str, str]],
        spec: TierSpec,
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None:
        return None
