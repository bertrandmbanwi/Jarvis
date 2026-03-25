"""Multi-backend LLM engine with three-tier Claude API and Ollama fallback."""
import httpx
import json
import logging
import time
from typing import AsyncGenerator, Optional

from jarvis.config import settings
from jarvis.core.hardening import (
    retry_with_backoff, API_RETRY_POLICY,
    claude_circuit, ollama_circuit,
    classify_error, user_friendly_error, sanitize_user_input,
)
from jarvis.core.perf import perf_tracker

logger = logging.getLogger("jarvis.llm")

_anthropic_client = None
_anthropic_available = False

TIER_CONFIG = {
    "fast": {
        "model": settings.CLAUDE_FAST_MODEL,
        "max_tokens": settings.CLAUDE_FAST_MAX_TOKENS,
        "temperature": settings.CLAUDE_FAST_TEMPERATURE,
    },
    "brain": {
        "model": settings.CLAUDE_BRAIN_MODEL,
        "max_tokens": settings.CLAUDE_BRAIN_MAX_TOKENS,
        "temperature": settings.CLAUDE_BRAIN_TEMPERATURE,
    },
    "deep": {
        "model": settings.CLAUDE_DEEP_MODEL,
        "max_tokens": settings.CLAUDE_DEEP_MAX_TOKENS,
        "temperature": settings.CLAUDE_DEEP_TEMPERATURE,
    },
}


def _get_anthropic_client():
    """Lazy-initialize the Anthropic async client."""
    global _anthropic_client, _anthropic_available
    if _anthropic_client is not None:
        return _anthropic_client

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set. Claude API unavailable.")
        _anthropic_available = False
        return None

    try:
        import anthropic
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=120.0,
        )
        _anthropic_available = True
        logger.info("Anthropic client initialized.")
        return _anthropic_client
    except ImportError:
        logger.warning("anthropic package not installed. Run: pip install anthropic")
        _anthropic_available = False
        return None
    except Exception as e:
        logger.error("Failed to initialize Anthropic client: %s", e)
        _anthropic_available = False
        return None


class JarvisLLM:
    """Multi-backend LLM engine with Claude API primary and Ollama fallback."""

    def __init__(
        self,
        system_prompt: str = None,
    ):
        self._static_system_prompt = system_prompt
        self.active_backend = "initializing"
        self._ollama_client = httpx.AsyncClient(timeout=120.0)
        self._ollama_base_url = settings.OLLAMA_BASE_URL.rstrip("/")

        self._session_costs = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_cost_usd": 0.0,
            "request_count": 0,
            "requests_by_tier": {"fast": 0, "brain": 0, "deep": 0, "ollama": 0},
        }

    @property
    def system_prompt(self) -> str:
        """Return the system prompt, rebuilding dynamically to keep date/time current."""
        if self._static_system_prompt:
            return self._static_system_prompt
        return settings.get_system_prompt()

    async def check_health(self) -> bool:
        """Check available backends and set active_backend. Returns True if any available."""
        claude_ok = await self._check_claude_health()
        ollama_ok = await self._check_ollama_health()

        if settings.PREFER_CLAUDE and claude_ok:
            self.active_backend = "claude"
            logger.info("Active backend: Claude API (primary)")
        elif ollama_ok:
            self.active_backend = "ollama"
            logger.info("Active backend: Ollama (fallback)")
        elif claude_ok:
            self.active_backend = "claude"
            logger.info("Active backend: Claude API")
        else:
            self.active_backend = "none"
            logger.error("No LLM backend available.")
            return False

        return True

    async def _check_claude_health(self) -> bool:
        """Verify the Anthropic API key works by making a minimal request."""
        client = _get_anthropic_client()
        if client is None:
            return False

        try:
            resp = await client.messages.create(
                model=settings.CLAUDE_FAST_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            logger.info("Claude API health check passed (model: %s).", settings.CLAUDE_FAST_MODEL)
            return True
        except Exception as e:
            logger.warning("Claude API health check failed: %s", e)
            return False

    async def _check_ollama_health(self) -> bool:
        """Check if Ollama is running and has the configured model."""
        try:
            resp = await self._ollama_client.get(f"{self._ollama_base_url}/api/tags")
            if resp.status_code != 200:
                return False
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            base_model = settings.OLLAMA_MODEL.split(":")[0]
            available = any(base_model in name for name in model_names)
            if available:
                logger.info("Ollama health check passed (model: %s).", settings.OLLAMA_MODEL)
            return available
        except httpx.ConnectError:
            logger.debug("Ollama not reachable at %s.", self._ollama_base_url)
            return False
        except Exception as e:
            logger.debug("Ollama health check error: %s", e)
            return False

    async def chat(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
        system_prompt_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        temperature_override: Optional[float] = None,
    ) -> str:
        """Send message and get complete response. Routes to Claude or Ollama with fallback."""
        if self.active_backend == "claude":
            try:
                return await self._chat_claude(
                    user_message, conversation_history, tier,
                    system_prompt_override, max_tokens_override, temperature_override,
                )
            except Exception as e:
                logger.error("Claude chat failed: %s. Trying Ollama fallback.", e)
                if await self._check_ollama_health():
                    self.active_backend = "ollama"
                    return await self._chat_ollama(user_message, conversation_history)
                return f"I encountered an error and my fallback is also unavailable: {e}"

        elif self.active_backend == "ollama":
            return await self._chat_ollama(user_message, conversation_history)

        else:
            return "I have no language model available. Please check that either your Anthropic API key is set or Ollama is running."

    async def chat_stream(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time."""
        if self.active_backend == "claude":
            try:
                async for token in self._stream_claude(user_message, conversation_history, tier):
                    yield token
                return
            except Exception as e:
                logger.error("Claude stream failed: %s. Trying Ollama fallback.", e)
                if await self._check_ollama_health():
                    self.active_backend = "ollama"

        if self.active_backend == "ollama":
            async for token in self._stream_ollama(user_message, conversation_history):
                yield token
        else:
            yield "I have no language model available."

    async def chat_with_tools(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
        max_iterations: int = 10,
        system_prompt_override: Optional[str] = None,
    ) -> tuple[str, list[dict]]:
        """Run agentic tool-use loop and return (final_response, tool_calls_log)."""
        client = _get_anthropic_client()
        if client is None:
            response = await self._chat_ollama(user_message, conversation_history)
            return response, []

        config = TIER_CONFIG.get(tier, TIER_CONFIG["brain"])
        system_prompt = system_prompt_override or self.system_prompt

        messages = self._build_claude_messages(user_message, conversation_history)

        tool_calls_log = []
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            start = time.time()

            async def _make_tool_request():
                return await client.messages.create(
                    model=config["model"],
                    max_tokens=config["max_tokens"],
                    temperature=config["temperature"],
                    system=[{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=messages,
                    tools=tools,
                )

            try:
                resp = await retry_with_backoff(
                    _make_tool_request,
                    policy=API_RETRY_POLICY,
                    context=f"Claude tool-use (iter {iteration})",
                )
                claude_circuit.record_success()
            except Exception as e:
                claude_circuit.record_failure()
                category = classify_error(e)
                logger.error(
                    "Claude tool-use call failed (iteration %d, %s): %s",
                    iteration, category.value, e,
                )
                # Try Ollama fallback for a simple response
                if await self._check_ollama_health():
                    self.active_backend = "ollama"
                    response = await self._chat_ollama(user_message, conversation_history)
                    return response, tool_calls_log
                return user_friendly_error(category, context="processing your request"), tool_calls_log

            elapsed = time.time() - start
            self._track_usage(resp.usage, config["model"], tier, elapsed, user_message[:80])
            perf_tracker.record(f"llm.tool_loop.{tier}.iter", elapsed)

            logger.info(
                "Agentic loop [iter %d, %s/%s]: stop_reason=%s, %d blocks, %.2fs",
                iteration, tier, config["model"].split("-")[1],
                resp.stop_reason, len(resp.content), elapsed,
            )

            if resp.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})

                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        logger.info("Tool call: %s(%s)", tool_name, str(tool_input)[:200])

                        try:
                            result = await tool_executor(tool_name, tool_input)
                        except Exception as e:
                            logger.error("Tool execution error (%s): %s", tool_name, e)
                            result = f"Error executing {tool_name}: {e}"

                        if isinstance(result, list):
                            log_text = " ".join(b.get("text", "") for b in result if b.get("type") == "text")
                            tool_calls_log.append({"name": tool_name, "input": tool_input, "result": log_text[:2000]})
                            tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": result})
                        else:
                            result_str = str(result)
                            tool_calls_log.append({"name": tool_name, "input": tool_input, "result": result_str[:2000]})
                            if len(result_str) > 8000:
                                result_str = result_str[:8000] + "\n... (truncated)"
                            tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": result_str})

                messages.append({"role": "user", "content": tool_results})

            elif resp.stop_reason == "end_turn":
                text_parts = []
                for block in resp.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                final_text = "\n".join(text_parts).strip()

                logger.info(
                    "Agentic loop complete: %d iterations, %d tool calls",
                    iteration, len(tool_calls_log),
                )
                return final_text, tool_calls_log

            else:
                logger.warning("Unexpected stop_reason: %s", resp.stop_reason)
                text_parts = []
                for block in resp.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                final_text = "\n".join(text_parts).strip()
                if not final_text:
                    final_text = "I hit a processing limit. Could you simplify the request?"
                return final_text, tool_calls_log

        logger.warning("Agentic loop hit max iterations (%d).", max_iterations)
        return (
            "I hit my processing limit. Let me know if you would like to continue."
        ), tool_calls_log

    async def chat_with_tools_stream(
        self,
        user_message: str,
        tools: list[dict],
        tool_executor,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
        max_iterations: int = 10,
        system_prompt_override: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Run tool-use loop non-streaming, then stream final response."""
        client = _get_anthropic_client()
        if client is None:
            response = await self._chat_ollama(user_message, conversation_history)
            yield response
            return

        config = TIER_CONFIG.get(tier, TIER_CONFIG["brain"])
        system_prompt = system_prompt_override or self.system_prompt
        messages = self._build_claude_messages(user_message, conversation_history)

        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            start = time.time()

            try:
                resp = await client.messages.create(
                    model=config["model"],
                    max_tokens=config["max_tokens"],
                    temperature=config["temperature"],
                    system=[{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=messages,
                    tools=tools,
                )
            except Exception as e:
                logger.error("Claude tool-use stream call failed (iteration %d): %s", iteration, e)
                yield f"I encountered an error: {e}"
                return

            elapsed = time.time() - start
            self._track_usage(resp.usage, config["model"], tier, elapsed, user_message[:80])

            if resp.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})
                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        logger.info("Tool call (stream): %s(%s)", tool_name, str(tool_input)[:200])
                        try:
                            result = await tool_executor(tool_name, tool_input)
                        except Exception as e:
                            logger.error("Tool execution error (%s): %s", tool_name, e)
                            result = f"Error executing {tool_name}: {e}"

                        if isinstance(result, list):
                            tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": result})
                        else:
                            result_str = str(result)
                            if len(result_str) > 8000:
                                result_str = result_str[:8000] + "\n... (truncated)"
                            tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": result_str})

                messages.append({"role": "user", "content": tool_results})

            elif resp.stop_reason == "end_turn":
                try:
                    async with client.messages.stream(
                        model=config["model"],
                        max_tokens=config["max_tokens"],
                        temperature=config["temperature"],
                        system=[{
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }],
                        messages=messages + [{"role": "user", "content": "Continue with your final response."}]
                        if not any(hasattr(b, "text") and b.text for b in resp.content)
                        else messages,
                    ) as stream:
                        has_text = any(hasattr(b, "text") and b.text.strip() for b in resp.content)
                        if has_text:
                            for block in resp.content:
                                if hasattr(block, "text") and block.text.strip():
                                    yield block.text
                            return

                        async for text in stream.text_stream:
                            yield text

                        final_message = await stream.get_final_message()
                        if final_message and final_message.usage:
                            elapsed2 = time.time() - start
                            self._track_usage(final_message.usage, config["model"], tier, elapsed2)
                except Exception:
                    for block in resp.content:
                        if hasattr(block, "text"):
                            yield block.text
                return

            else:
                text_parts = []
                for block in resp.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                yield "\n".join(text_parts).strip() or "I hit a processing limit."
                return

        yield "I hit my processing limit. Let me know if you would like me to continue."

    async def _chat_claude(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
        system_prompt_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        temperature_override: Optional[float] = None,
    ) -> str:
        """Send message to Claude API with circuit breaker and retry logic."""
        if not claude_circuit.allow_request():
            raise ConnectionError(
                "Claude API circuit breaker is open (repeated failures). "
                "Will retry automatically after recovery window."
            )

        client = _get_anthropic_client()
        if client is None:
            raise ConnectionError("Anthropic client not available.")

        config = TIER_CONFIG.get(tier, TIER_CONFIG["brain"])
        system_prompt = system_prompt_override or self.system_prompt
        max_tokens = max_tokens_override or config["max_tokens"]
        temperature = temperature_override or config["temperature"]

        user_message = sanitize_user_input(user_message)
        messages = self._build_claude_messages(user_message, conversation_history)

        start = time.time()

        async def _make_request():
            return await client.messages.create(
                model=config["model"],
                max_tokens=max_tokens,
                temperature=temperature,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=messages,
            )

        try:
            resp = await retry_with_backoff(
                _make_request,
                policy=API_RETRY_POLICY,
                context=f"Claude chat ({tier})",
            )
            claude_circuit.record_success()
        except Exception as e:
            claude_circuit.record_failure()
            raise

        elapsed = time.time() - start
        content = resp.content[0].text if resp.content else ""

        # Track costs and performance
        self._track_usage(resp.usage, config["model"], tier, elapsed, user_message[:80])
        perf_tracker.record(f"llm.chat.{tier}", elapsed)

        logger.info(
            "Claude [%s/%s] response: %d chars in %.2fs (in:%d out:%d tokens)",
            tier, config["model"].split("-")[1], len(content), elapsed,
            resp.usage.input_tokens, resp.usage.output_tokens,
        )
        return content.strip()

    async def _stream_claude(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens from Claude API."""
        client = _get_anthropic_client()
        if client is None:
            raise ConnectionError("Anthropic client not available.")

        config = TIER_CONFIG.get(tier, TIER_CONFIG["brain"])
        messages = self._build_claude_messages(user_message, conversation_history)

        start = time.time()
        total_input = 0
        total_output = 0

        async with client.messages.stream(
            model=config["model"],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
            system=[{
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

            final_message = await stream.get_final_message()
            if final_message and final_message.usage:
                elapsed = time.time() - start
                self._track_usage(final_message.usage, config["model"], tier, elapsed)

    def _build_claude_messages(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Build message list for Claude API."""
        messages = []
        if conversation_history:
            recent = conversation_history[-settings.MAX_CONTEXT_MESSAGES:]
            for msg in recent:
                if messages and messages[-1]["role"] == msg["role"]:
                    messages[-1]["content"] += "\n" + msg["content"]
                else:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        if messages and messages[0]["role"] != "user":
            messages = messages[1:]

        messages.append({"role": "user", "content": user_message})
        return messages

    async def _chat_ollama(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> str:
        """Send message to Ollama and return response."""
        messages = self._build_ollama_messages(user_message, conversation_history)
        try:
            resp = await self._ollama_client.post(
                f"{self._ollama_base_url}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 256,
                        "num_ctx": 4096,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            self._session_costs["request_count"] += 1
            self._session_costs["requests_by_tier"]["ollama"] += 1
            logger.info("Ollama response: %d chars", len(content))
            return content.strip()
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama. Is it running?")
            return "I cannot connect to any language model. Please check that Ollama is running or that your Anthropic API key is set."
        except Exception as e:
            logger.error("Ollama chat error: %s", e)
            return f"I encountered an error: {e}"

    async def _stream_ollama(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
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
        conversation_history: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Build message list for Ollama API."""
        messages = [{"role": "system", "content": self.system_prompt}]
        if conversation_history:
            recent = conversation_history[-settings.MAX_CONTEXT_MESSAGES:]
            messages.extend(recent)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _track_usage(self, usage, model: str, tier: str, elapsed: float, user_preview: str = ""):
        """Record token usage and cost."""
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

        pricing = settings.CLAUDE_PRICING.get(model, {})
        if pricing:
            standard_input = max(0, input_tokens - cache_read - cache_creation)
            cost = (
                (standard_input / 1_000_000) * pricing["input"]
                + (output_tokens / 1_000_000) * pricing["output"]
                + (cache_creation / 1_000_000) * pricing["cache_write"]
                + (cache_read / 1_000_000) * pricing["cache_read"]
            )
        else:
            cost = 0.0

        self._session_costs["total_input_tokens"] += input_tokens
        self._session_costs["total_output_tokens"] += output_tokens
        self._session_costs["total_cache_read_tokens"] += cache_read
        self._session_costs["total_cache_creation_tokens"] += cache_creation
        self._session_costs["total_cost_usd"] += cost
        self._session_costs["request_count"] += 1
        self._session_costs["requests_by_tier"][tier] = (
            self._session_costs["requests_by_tier"].get(tier, 0) + 1
        )

        try:
            from jarvis.core.cost_tracker import log_request
            log_request(
                model=model, tier=tier,
                input_tokens=input_tokens, output_tokens=output_tokens,
                cache_read_tokens=cache_read, cache_creation_tokens=cache_creation,
                cost_usd=cost, elapsed_seconds=elapsed,
                user_input_preview=user_preview,
            )
        except Exception as e:
            logger.debug("Cost log write failed (non-critical): %s", e)

        logger.info(
            "Cost: $%.4f (in:%d out:%d cache_r:%d cache_w:%d) | Session: $%.4f (%d reqs)",
            cost, input_tokens, output_tokens, cache_read, cache_creation,
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
        if self.active_backend == "claude":
            config = TIER_CONFIG.get(tier, TIER_CONFIG["brain"])
            return config["model"]
        elif self.active_backend == "ollama":
            return settings.OLLAMA_MODEL
        return "none"

    async def close(self):
        """Close HTTP clients and log final session cost."""
        await self._ollama_client.aclose()
        logger.info(
            "LLM engine shut down. Session cost: $%.4f across %d requests.",
            self._session_costs["total_cost_usd"],
            self._session_costs["request_count"],
        )


OllamaLLM = JarvisLLM
