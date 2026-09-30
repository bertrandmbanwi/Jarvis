"""Multi-backend LLM engine: a cloud provider (OpenAI by default, Anthropic
optional) across three tiers, with Ollama as the local fallback.

Provider-specific request building lives in ``jarvis.core.providers``; this
module owns routing, fallback, cost guards and usage accounting.
"""
import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx

from jarvis.config import settings
from jarvis.core.hardening import (
    classify_error,
    cloud_circuit,
    sanitize_user_input,
    user_friendly_error,
)
from jarvis.core.ollama import list_ollama_models
from jarvis.core.perf import perf_tracker
from jarvis.core.providers import (
    CloudProvider,
    SystemPrompt,
    TierSpec,
    Usage,
    build_provider,
    provider_api_key,
    tier_specs,
)

logger = logging.getLogger("jarvis.llm")


class ToolLoopError(RuntimeError):
    """The tool-use loop could not complete (API failure, cost guard, or iteration cap).

    Raised only when ``chat_with_tools(raise_on_failure=True)``; otherwise the
    loop returns a user-facing message, which callers cannot tell apart from
    a successful answer.
    """


def _ollama_model_matches(installed_name: str) -> bool:
    """True if an installed Ollama model satisfies the configured OLLAMA_MODEL.

    Avoids the substring false-positive where configured "llama3" matched an
    unrelated "llama3.1:8b" — the health check passed but the exact-name chat
    request then 404'd. An untagged config name matches any tag of that exact
    base (Ollama resolves it to :latest); a tagged config must match exactly.
    """
    configured = settings.OLLAMA_MODEL
    if installed_name == configured:
        return True
    if ":" not in configured:
        return installed_name.split(":")[0] == configured
    return False


class JarvisLLM:
    """Routes requests to the cloud provider with Ollama as the fallback."""

    def __init__(
        self,
        system_prompt: str | None = None,
        provider: CloudProvider | None = None,
    ):
        self._static_system_prompt = system_prompt
        self.active_backend = "initializing"
        # Mirrors JarvisBrain's privacy mode: when on, no prompt text is written to cost logs.
        self.privacy_mode = False
        self._ollama_client = httpx.AsyncClient(timeout=120.0)
        self._ollama_base_url = settings.OLLAMA_BASE_URL.rstrip("/")

        # An injected provider is kept as-is (tests); otherwise the provider is
        # rebuilt whenever the provider name or its API key changes in Settings.
        self._provider_fixed = provider is not None
        self._provider: CloudProvider | None = provider
        self._provider_key: tuple[str, str] | None = None
        # After a cloud failure, requests go to Ollama until this time, then
        # the cloud is tried again (the old behaviour switched permanently).
        self._cloud_down_until = 0.0

        self._session_costs: dict[str, Any] = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_cost_usd": 0.0,
            "request_count": 0,
            "requests_by_tier": {"fast": 0, "brain": 0, "deep": 0, "ollama": 0},
        }

    # ── provider and prompt plumbing ────────────────────────────────────

    @property
    def provider(self) -> CloudProvider:
        if self._provider_fixed and self._provider is not None:
            return self._provider
        key = (settings.LLM_PROVIDER, provider_api_key())
        if self._provider is None or key != self._provider_key:
            self._provider = build_provider()
            self._provider_key = key
        return self._provider

    @property
    def cloud_name(self) -> str:
        return self.provider.name

    def tier_spec(self, tier: str) -> TierSpec:
        specs = tier_specs(self.cloud_name)
        return specs.get(tier, specs["brain"])

    @property
    def system_prompt(self) -> str:
        """Return the system prompt, rebuilding dynamically to keep date/time current."""
        if self._static_system_prompt:
            return self._static_system_prompt
        return settings.get_system_prompt()

    def _system(self, override: str | None = None) -> SystemPrompt:
        if override:
            return SystemPrompt(static=override)
        if self._static_system_prompt:
            return SystemPrompt(static=self._static_system_prompt)
        static, dynamic = settings.get_system_prompt_parts()
        return SystemPrompt(static=static, dynamic=dynamic)

    def _apply_cost_mode(self, tier: str) -> str:
        """Downgrade expensive tiers when the user chooses economy mode."""
        mode = settings.COST_MODE
        if mode in {"economy", "eco", "low"}:
            if tier == "deep":
                return "brain"
            if tier == "brain":
                return "fast"
        if mode in {"balanced", "standard"} and tier == "deep":
            return "brain"
        return tier

    def _paid_usage_blocked(self) -> tuple[bool, str]:
        """Return whether paid API calls should be blocked by hard budget limits."""
        try:
            from jarvis.core.cost_tracker import get_month_summary, get_today_summary
            today = get_today_summary()
            month = get_month_summary()
        except Exception as exc:
            logger.debug("Cost budget check skipped: %s", exc)
            return False, ""

        daily_limit = float(getattr(settings, "COST_DAILY_HARD_LIMIT", 0) or 0)
        monthly_limit = float(getattr(settings, "COST_MONTHLY_HARD_LIMIT", 0) or 0)
        if daily_limit > 0 and float(today.get("total_cost_usd", 0.0)) >= daily_limit:
            return True, f"daily hard limit of ${daily_limit:.2f}"
        if monthly_limit > 0 and float(month.get("total_cost_usd", 0.0)) >= monthly_limit:
            return True, f"monthly hard limit of ${monthly_limit:.2f}"
        return False, ""

    async def _budget_blocked(self) -> tuple[bool, str]:
        if self.cloud_name == "local":
            return False, ""  # local models cost nothing
        # Reads the day and month cost files; keep that disk I/O off the event loop.
        return await asyncio.to_thread(self._paid_usage_blocked)

    def _cloud_ready(self) -> bool:
        return (
            self.provider.is_configured()
            and time.monotonic() >= self._cloud_down_until
            and cloud_circuit.allow_request()
        )

    def _cloud_succeeded(self) -> None:
        cloud_circuit.record_success()
        self._cloud_down_until = 0.0
        self.active_backend = self.cloud_name

    def _cloud_failed(self, error: Exception) -> None:
        cloud_circuit.record_failure()
        self._cloud_down_until = time.monotonic() + settings.CLOUD_RETRY_COOLDOWN_S
        logger.error(
            "%s call failed (%s): %s. Using Ollama for %.0fs before retrying the cloud.",
            self.cloud_name, classify_error(error).value, error, settings.CLOUD_RETRY_COOLDOWN_S,
        )

    def _no_backend_message(self) -> str:
        if self.cloud_name == "local":
            return f"I can't reach the local model server at {settings.LOCAL_LLM_BASE_URL}. Is Ollama running?"
        key_name = "ANTHROPIC_API_KEY" if self.cloud_name == "anthropic" else "OPENAI_API_KEY"
        return f"I have no language model available. Please set {key_name} or start Ollama."

    # ── health ──────────────────────────────────────────────────────────

    async def check_health(self) -> bool:
        """Check available backends and set active_backend. Returns True if any available."""
        cloud_ok = await self._check_cloud_health()
        ollama_ok = await self._check_ollama_health()

        if cloud_ok and (settings.PREFER_CLAUDE or not ollama_ok):
            self.active_backend = self.cloud_name
            logger.info("Active backend: %s (primary)", self.cloud_name)
        elif ollama_ok:
            self.active_backend = "ollama"
            logger.info("Active backend: Ollama (fallback)")
        else:
            self.active_backend = "none"
            logger.error("No LLM backend available.")
            return False
        return True

    async def _check_cloud_health(self) -> bool:
        """Verify the cloud provider without spending tokens unless requested."""
        if not self.provider.is_configured():
            logger.warning("%s API key not set; cloud models unavailable.", self.cloud_name)
            return False
        if settings.ANTHROPIC_LAZY_HEALTHCHECK:
            logger.info("%s configured; skipping startup health request.", self.cloud_name)
            return True
        return await self.provider.health()

    async def _check_ollama_health(self) -> bool:
        """Check if Ollama is running and has the configured model."""
        try:
            model_names = await list_ollama_models(
                self._ollama_base_url, client=self._ollama_client
            )
        except httpx.ConnectError:
            logger.debug("Ollama not reachable at %s.", self._ollama_base_url)
            return False
        except Exception as e:
            logger.debug("Ollama health check error: %s", e)
            return False
        available = any(_ollama_model_matches(name) for name in model_names)
        if available:
            logger.info("Ollama health check passed (model: %s).", settings.OLLAMA_MODEL)
        return available

    # ── chat ────────────────────────────────────────────────────────────

    async def chat(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        system_prompt_override: str | None = None,
        max_tokens_override: int | None = None,
        temperature_override: float | None = None,
    ) -> str:
        """Send message and get complete response, falling back to Ollama."""
        tier = self._apply_cost_mode(tier)
        paid_blocked, block_reason = await self._budget_blocked()
        if paid_blocked:
            logger.warning("Cloud request blocked by %s.", block_reason)
            if await self._check_ollama_health():
                return await self._chat_ollama(user_message, conversation_history)
            return f"I am in cost guard mode because the {block_reason} has been reached. Local tools still work."

        error: Exception | None = None
        if self._cloud_ready():
            try:
                return await self._chat_cloud(
                    user_message, conversation_history, tier,
                    system_prompt_override, max_tokens_override, temperature_override,
                )
            except Exception as e:
                self._cloud_failed(e)
                error = e

        if await self._check_ollama_health():
            self.active_backend = "ollama"
            return await self._chat_ollama(user_message, conversation_history)
        if error is not None:
            return f"I encountered an error and my fallback is also unavailable: {error}"
        return self._no_backend_message()

    async def chat_json(
        self,
        user_message: str,
        schema: dict[str, Any],
        tier: str = "fast",
        system_prompt_override: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        """Get a response that conforms to ``schema`` (structured outputs).

        Returns None when no backend could produce valid JSON, so callers can
        fall back to a safe default instead of parsing free text.
        """
        tier = self._apply_cost_mode(tier)
        paid_blocked, _ = await self._budget_blocked()
        raw = ""
        if not paid_blocked and self._cloud_ready():
            spec = self.tier_spec(tier)
            start = time.time()
            try:
                raw, usage = await self.provider.complete(
                    system=self._system(system_prompt_override),
                    messages=self._build_messages(sanitize_user_input(user_message), conversation_history),
                    spec=spec,
                    json_schema=schema,
                )
                self._cloud_succeeded()
                self._track_usage(usage, tier, time.time() - start, user_message[:80])
            except Exception as e:
                self._cloud_failed(e)
                raw = ""
        if not raw and await self._check_ollama_health():
            raw = await self._chat_ollama(user_message, conversation_history, json_schema=schema)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Structured output was not valid JSON: %s", str(raw)[:200])
            return None
        return data if isinstance(data, dict) else None

    async def chat_stream(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time."""
        tier = self._apply_cost_mode(tier)
        paid_blocked, block_reason = await self._budget_blocked()
        use_cloud = not paid_blocked and self._cloud_ready()
        if paid_blocked and not await self._check_ollama_health():
            yield f"I am in cost guard mode because the {block_reason} has been reached. Local tools still work."
            return

        if use_cloud:
            spec = self.tier_spec(tier)
            start = time.time()
            streamed_any = False
            try:
                async for token in self.provider.stream(
                    system=self._system(),
                    messages=self._build_messages(user_message, conversation_history),
                    spec=spec,
                    on_usage=lambda usage: self._track_usage(usage, tier, time.time() - start),
                ):
                    streamed_any = True
                    yield token
                self._cloud_succeeded()
                return
            except Exception as e:
                self._cloud_failed(e)
                if streamed_any:
                    # Tokens were already emitted; replaying on Ollama would
                    # duplicate the partial answer the user has already seen.
                    yield "\n\n[Response interrupted — please retry.]"
                    return

        if await self._check_ollama_health():
            self.active_backend = "ollama"
            async for token in self._stream_ollama(user_message, conversation_history):
                yield token
        else:
            yield self._no_backend_message()

    async def chat_with_tools(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        max_iterations: int = 10,
        system_prompt_override: str | None = None,
        raise_on_failure: bool = False,
    ) -> tuple[str, list[dict]]:
        """Run agentic tool-use loop and return (final_response, tool_calls_log).

        With ``raise_on_failure``, failures raise ``ToolLoopError`` instead of
        returning an apology string, so plan subtasks can retry or be marked failed.
        """
        tier = self._apply_cost_mode(tier)
        paid_blocked, block_reason = await self._budget_blocked()
        if paid_blocked:
            logger.warning("Cloud tool-use request blocked by %s.", block_reason)
            if raise_on_failure:
                raise ToolLoopError(f"Paid usage blocked by {block_reason}")
            return f"I am in cost guard mode because the {block_reason} has been reached. Try a local command or switch cost mode.", []

        if not self._cloud_ready():
            if raise_on_failure:
                raise ToolLoopError(f"{self.cloud_name} is unavailable")
            return await self._chat_ollama(user_message, conversation_history), []

        spec = self.tier_spec(tier)
        start = time.time()
        try:
            result = await self.provider.run_tools(
                system=self._system(system_prompt_override),
                messages=self._build_messages(user_message, conversation_history),
                tools=tools,
                executor=tool_executor,
                spec=spec,
                max_iterations=max_iterations,
                on_usage=lambda usage: self._track_usage(usage, tier, time.time() - start, user_message[:80]),
            )
            self._cloud_succeeded()
        except Exception as e:
            self._cloud_failed(e)
            if raise_on_failure:
                raise ToolLoopError(f"Tool-use call failed ({classify_error(e).value}): {e}") from e
            if await self._check_ollama_health():
                return await self._chat_ollama(user_message, conversation_history), []
            return user_friendly_error(classify_error(e), context="processing your request"), []

        perf_tracker.record(f"llm.tool_loop.{tier}", time.time() - start)
        if not result.completed and raise_on_failure:
            raise ToolLoopError(f"Tool loop did not complete: {result.text}")
        logger.info("Agentic loop complete: %d tool calls", len(result.tool_calls))
        return result.text, result.tool_calls

    async def chat_with_tools_stream(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        max_iterations: int = 10,
        system_prompt_override: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Run the tool loop, yielding answer text as the model writes it.

        Providers without ``stream_tools`` (and any failure before the first
        token) fall back to the non-streaming loop, yielded in one piece.
        """
        tier = self._apply_cost_mode(tier)
        paid_blocked, _ = await self._budget_blocked()
        stream_tools = getattr(self.provider, "stream_tools", None)
        streamed_any = False
        if stream_tools is not None and not paid_blocked and self._cloud_ready():
            start = time.time()
            try:
                async for token in stream_tools(
                    system=self._system(system_prompt_override),
                    messages=self._build_messages(user_message, conversation_history),
                    tools=tools,
                    executor=tool_executor,
                    spec=self.tier_spec(tier),
                    max_iterations=max_iterations,
                    on_usage=lambda usage: self._track_usage(usage, tier, time.time() - start, user_message[:80]),
                    on_result=lambda result: None,
                ):
                    streamed_any = True
                    yield token
                self._cloud_succeeded()
                perf_tracker.record(f"llm.tool_loop.{tier}", time.time() - start)
                if streamed_any:
                    return
            except Exception as e:
                self._cloud_failed(e)
                if streamed_any:
                    yield "\n\n[Response interrupted — please retry.]"
                    return

        text, _ = await self.chat_with_tools(
            user_message, tools, tool_executor, conversation_history,
            tier=tier, max_iterations=max_iterations, system_prompt_override=system_prompt_override,
        )
        yield text or "I completed the tool work, but did not receive a final response."

    async def _chat_cloud(
        self,
        user_message: str,
        conversation_history: list[dict] | None,
        tier: str,
        system_prompt_override: str | None = None,
        max_tokens_override: int | None = None,
        temperature_override: float | None = None,
    ) -> str:
        spec = self.tier_spec(tier)
        if max_tokens_override is not None:
            # Reasoning tokens share the output budget on reasoning models, so
            # never shrink below the tier's own budget.
            spec = TierSpec(spec.model, max(max_tokens_override, spec.max_output_tokens),
                            spec.effort, spec.temperature)
        if temperature_override is not None and spec.temperature is not None:
            spec = TierSpec(spec.model, spec.max_output_tokens, spec.effort, temperature_override)

        user_message = sanitize_user_input(user_message)
        start = time.time()
        text, usage = await self.provider.complete(
            system=self._system(system_prompt_override),
            messages=self._build_messages(user_message, conversation_history),
            spec=spec,
        )
        self._cloud_succeeded()
        elapsed = time.time() - start
        self._track_usage(usage, tier, elapsed, user_message[:80])
        perf_tracker.record(f"llm.chat.{tier}", elapsed)
        logger.info(
            "%s [%s/%s] response: %d chars in %.2fs",
            self.cloud_name, tier, spec.model, len(text), elapsed,
        )
        return text.strip()

    # ── message building ────────────────────────────────────────────────

    def _build_messages(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
    ) -> list[dict[str, str]]:
        """Build a user/assistant message list, summarising older turns."""
        messages: list[dict[str, str]] = []
        if conversation_history:
            recent_count = max(2, min(settings.CONTEXT_RECENT_MESSAGES, settings.MAX_CONTEXT_MESSAGES))
            older = conversation_history[:-recent_count]
            recent = conversation_history[-recent_count:]

            if older:
                summary = self._summarize_history_for_context(older)
                if summary:
                    messages.append({
                        "role": "user",
                        "content": f"Earlier conversation summary for context:\n{summary}",
                    })

            for msg in recent:
                if messages and messages[-1]["role"] == msg["role"]:
                    messages[-1]["content"] += "\n" + msg["content"]
                else:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        if messages and messages[0]["role"] != "user":
            messages = messages[1:]

        messages.append({"role": "user", "content": user_message})
        return messages

    def _summarize_history_for_context(self, history: list[dict]) -> str:
        """Build a deterministic, bounded summary of older turns."""
        if not history:
            return ""

        snippets: list[str] = []
        budget = max(400, settings.CONTEXT_SUMMARY_MAX_CHARS)
        for msg in history[-20:]:
            role = str(msg.get("role", "user"))
            content = str(msg.get("content", "")).strip().replace("\n", " ")
            if not content:
                continue
            content = content[:180]
            snippets.append(f"- {role}: {content}")
            if sum(len(s) for s in snippets) >= budget:
                break

        summary = "\n".join(snippets)
        if len(summary) > budget:
            summary = summary[:budget].rsplit("\n", 1)[0]
        return summary

    # ── Ollama ──────────────────────────────────────────────────────────

    async def _chat_ollama(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Send message to Ollama and return response."""
        messages = self._build_ollama_messages(user_message, conversation_history)
        payload: dict[str, Any] = {
            "model": settings.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.7,
                "num_predict": 256 if json_schema is None else 1024,
                "num_ctx": 4096,
            },
        }
        if json_schema is not None:
            payload["format"] = json_schema
        try:
            resp = await self._ollama_client.post(f"{self._ollama_base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            message = data.get("message", {})
            content = message.get("content", "") if isinstance(message, dict) else ""
            self._session_costs["request_count"] += 1
            self._session_costs["requests_by_tier"]["ollama"] += 1
            logger.info("Ollama response: %d chars", len(content))
            return content.strip()
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama. Is it running?")
            return self._no_backend_message()
        except Exception as e:
            logger.error("Ollama chat error: %s", e)
            return f"I encountered an error: {e}"

    async def _stream_ollama(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens from Ollama."""
        messages = self._build_ollama_messages(user_message, conversation_history)
        try:
            async with self._ollama_client.stream(
                "POST",
                f"{self._ollama_base_url}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.7, "num_predict": 512},
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            yield "I cannot connect to Ollama. Is it running?"
        except Exception as e:
            logger.error("Ollama stream error: %s", e)
            yield f"I encountered an error: {e}"

    def _build_ollama_messages(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
    ) -> list[dict]:
        """Build message list for Ollama API."""
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        if conversation_history:
            recent = conversation_history[-max(2, min(settings.CONTEXT_RECENT_MESSAGES, settings.MAX_CONTEXT_MESSAGES)):]
            messages.extend(recent)
        messages.append({"role": "user", "content": user_message})
        return messages

    # ── tokens and cost ─────────────────────────────────────────────────

    async def count_input_tokens(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        tools: list[dict] | None = None,
        system_prompt_override: str | None = None,
    ) -> dict[str, Any]:
        """Count input tokens with the provider's free counting endpoint."""
        from jarvis.core.perf import estimate_tokens

        tier = self._apply_cost_mode(tier)
        spec = self.tier_spec(tier)
        count: int | None = None
        if self.provider.is_configured():
            count = await self.provider.count_tokens(
                system=self._system(system_prompt_override),
                messages=self._build_messages(user_message, conversation_history),
                spec=spec,
                tools=tools,
            )
        if count is None:
            return {
                "input_tokens": estimate_tokens(user_message),
                "model": spec.model,
                "tier": tier,
                "source": "local_estimate",
            }
        return {
            "input_tokens": count,
            "model": spec.model,
            "tier": tier,
            "source": f"{self.cloud_name}_count_tokens",
        }

    def _track_usage(self, usage: Usage, tier: str, elapsed: float, user_preview: str = ""):
        """Record token usage and cost."""
        cost = usage.cost(settings.MODEL_PRICING.get(usage.model, {}))

        self._session_costs["total_input_tokens"] += usage.input_tokens
        self._session_costs["total_output_tokens"] += usage.output_tokens
        self._session_costs["total_cache_read_tokens"] += usage.cache_read_tokens
        self._session_costs["total_cache_creation_tokens"] += usage.cache_write_tokens
        self._session_costs["total_cost_usd"] += cost
        self._session_costs["request_count"] += 1
        self._session_costs["requests_by_tier"][tier] = (
            self._session_costs["requests_by_tier"].get(tier, 0) + 1
        )

        try:
            from jarvis.core.cost_tracker import log_request
            log_request(
                model=usage.model, tier=tier,
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_creation_tokens=usage.cache_write_tokens,
                cost_usd=cost, elapsed_seconds=elapsed,
                user_input_preview="" if self.privacy_mode else user_preview,
            )
        except Exception as e:
            logger.debug("Cost log write failed (non-critical): %s", e)

        logger.info(
            "Cost: $%.4f (in:%d out:%d cache_r:%d cache_w:%d) | Session: $%.4f (%d reqs)",
            cost, usage.input_tokens, usage.output_tokens,
            usage.cache_read_tokens, usage.cache_write_tokens,
            self._session_costs["total_cost_usd"],
            self._session_costs["request_count"],
        )

        if self._session_costs["total_cost_usd"] > settings.COST_DAILY_ALERT:
            logger.warning(
                "COST ALERT: Session cost ($%.2f) exceeds daily alert ($%.2f).",
                self._session_costs["total_cost_usd"], settings.COST_DAILY_ALERT,
            )

    def get_cost_summary(self) -> dict:
        """Return current session cost summary."""
        return {
            "session_cost_usd": round(self._session_costs["total_cost_usd"], 4),
            "total_requests": self._session_costs["request_count"],
            "requests_by_tier": dict(self._session_costs["requests_by_tier"]),
            "total_input_tokens": self._session_costs["total_input_tokens"],
            "total_output_tokens": self._session_costs["total_output_tokens"],
            "cache_read_tokens": self._session_costs["total_cache_read_tokens"],
            "cache_creation_tokens": self._session_costs["total_cache_creation_tokens"],
            "active_backend": self.active_backend,
        }

    def get_active_model(self, tier: str = "brain") -> str:
        """Return the model name for the given tier or current backend."""
        if self.active_backend == "ollama":
            return settings.OLLAMA_MODEL
        if self.active_backend in ("none", "initializing"):
            return "none"
        return self.tier_spec(tier).model

    async def close(self):
        """Close HTTP clients and log final session cost."""
        await self._ollama_client.aclose()
        logger.info(
            "LLM engine shut down. Session cost: $%.4f across %d requests.",
            self._session_costs["total_cost_usd"],
            self._session_costs["request_count"],
        )


OllamaLLM = JarvisLLM
