"""
JARVIS Agent Executor (v2.1: Agentic Loop + Task Decomposition)

Replaces the regex-based intent matching with Claude's native tool_use.
Claude decides which tools to call, when to call them, and when to stop.
This enables multi-step task completion, error recovery, and natural follow-ups.

v2.1 adds task decomposition: complex requests can be broken into subtasks
by the TaskPlanner, then each subtask is executed through the agentic loop
with accumulated context from previous steps.

Architecture:
    User says something
    -> TaskPlanner checks complexity (heuristic + optional LLM check)
    -> If complex: decompose into subtask plan
       -> Execute each subtask via the agentic loop, passing prior results as context
       -> Track progress, handle failures, produce final summary
    -> If simple: run single agentic loop as before
    -> Claude decides which tool(s) to call (or just responds conversationally)
    -> Tool executes, result feeds back to Claude
    -> Claude decides: done? Or call another tool?
    -> Loop until task is complete
"""
import asyncio
import contextlib
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any, cast

from jarvis.agent.qa_agent import QAAgent
from jarvis.agent.tool_selector import select_tools_for_request
from jarvis.agent.tools_schema import TOOL_REGISTRY, TOOL_SCHEMAS
from jarvis.core.cache import invalidate_on_mutation, tool_cache
from jarvis.core.confirmation import confirmed_scope
from jarvis.core.hardening import (
    check_dangerous_command,
    classify_error,
    execute_with_timeout,
    get_tool_circuit,
    get_tool_timeout,
    user_friendly_error,
    validate_tool_args,
)
from jarvis.core.llm import JarvisLLM
from jarvis.core.pending_actions import confirmation_available, request_confirmation
from jarvis.core.perf import perf_tracker
from jarvis.core.permissions import (
    assess_tool_call,
    call_is_confirmed,
    describe_tool_call,
    record_tool_audit,
)
from jarvis.core.tracing import record_event, trace_span

logger = logging.getLogger("jarvis.agent")


def _accepted_kwargs(fn: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return only the kwargs the function actually accepts by name.

    Used to recover from a TypeError caused by the model passing extra/unknown
    keys, WITHOUT the old positional remapping (which could silently bind the
    wrong value to the wrong parameter, e.g. swapping an email subject and body).
    """
    try:
        params = inspect.signature(fn).parameters.values()
    except (ValueError, TypeError):
        return dict(kwargs)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params):
        return dict(kwargs)
    accepted = {
        p.name for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {k: v for k, v in kwargs.items() if k in accepted}


class AgentExecutor:
    """Executes user requests using Claude's native tool_use agentic loop."""

    def __init__(self, llm: JarvisLLM | None = None):
        self.llm = llm or JarvisLLM()
        self._on_tool_executed: Callable[[str, bool, float, str], Any] | None = None
        self._qa_agent = QAAgent()
        self._qa_enabled = True

    async def execute(
        self,
        user_input: str,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        tools: list[dict] | None = None,
        system_prompt_override: str | None = None,
    ) -> str:
        """Process a user request using Claude's agentic tool-use loop."""
        logger.info("Agent executing (tier=%s): '%s'", tier, user_input[:100])
        active_tools = tools or select_tools_for_request(user_input, TOOL_SCHEMAS)
        logger.info("Tool schema selection: %d/%d tools", len(active_tools), len(TOOL_SCHEMAS))

        response_text, tool_calls = await self.llm.chat_with_tools(
            user_message=user_input,
            tools=active_tools,
            tool_executor=self._execute_tool,
            conversation_history=conversation_history,
            tier=tier,
            max_iterations=10,
            system_prompt_override=system_prompt_override,
        )

        if tool_calls:
            logger.info(
                "Agent completed with %d tool call(s): %s",
                len(tool_calls),
                [tc["name"] for tc in tool_calls],
            )

            # QA verification for tool-based responses
            if self._qa_enabled and tool_calls:
                try:
                    qa_result = await self._qa_agent.verify(
                        task_prompt=user_input,
                        task_result=response_text,
                        llm=self.llm,
                        tier="fast",
                    )
                    if not qa_result.passed:
                        logger.info(
                            "QA verification failed (attempt %d): %s",
                            qa_result.attempt,
                            qa_result.issues,
                        )
                        # Single retry with QA feedback
                        retry_prompt = (
                            f"Your previous response had quality issues:\n"
                            f"Issues: {', '.join(qa_result.issues)}\n\n"
                            f"Original request: {user_input}\n\n"
                            f"Please provide a corrected response addressing these issues."
                        )
                        response_text, _ = await self.llm.chat_with_tools(
                            user_message=retry_prompt,
                            tools=active_tools,
                            tool_executor=self._execute_tool,
                            conversation_history=conversation_history,
                            tier=tier,
                            max_iterations=5,
                            system_prompt_override=system_prompt_override,
                        )
                        logger.info("QA retry completed.")
                except Exception as e:
                    logger.debug("QA verification skipped (non-critical): %s", e)

        return response_text

    async def execute_stream(
        self,
        user_input: str,
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        tools: list[dict] | None = None,
        system_prompt_override: str | None = None,
    ):
        """Stream the final response token by token after tool iterations."""
        logger.info("Agent executing (streaming, tier=%s): '%s'", tier, user_input[:100])
        active_tools = tools or select_tools_for_request(user_input, TOOL_SCHEMAS)

        async for token in self.llm.chat_with_tools_stream(
            user_message=user_input,
            tools=active_tools,
            tool_executor=self._execute_tool,
            conversation_history=conversation_history,
            tier=tier,
            max_iterations=10,
            system_prompt_override=system_prompt_override,
        ):
            yield token

    async def execute_subtask(
        self,
        subtask_description: str,
        prior_context: str = "",
        conversation_history: list[dict] | None = None,
        tier: str = "brain",
        tools: list[dict] | None = None,
        system_prompt_override: str | None = None,
    ) -> str:
        """Execute a single subtask from a decomposed plan."""
        if prior_context:
            prompt = (
                f"You are executing one step of a multi-step plan. "
                f"Here are the results from previous steps:\n\n"
                f"{prior_context}\n\n"
                f"Now execute this step:\n{subtask_description}\n\n"
                f"Focus on completing THIS step. Use the results from "
                f"previous steps as needed. Be concise in your response."
            )
        else:
            prompt = subtask_description

        logger.info("Subtask executing (tier=%s): '%s'", tier, subtask_description[:100])
        active_tools = tools or select_tools_for_request(subtask_description, TOOL_SCHEMAS)

        response_text, tool_calls = await self.llm.chat_with_tools(
            user_message=prompt,
            tools=active_tools,
            tool_executor=self._execute_tool,
            conversation_history=conversation_history,
            tier=tier,
            max_iterations=10,
            system_prompt_override=system_prompt_override,
        )

        if tool_calls:
            logger.info(
                "Subtask completed with %d tool call(s): %s",
                len(tool_calls),
                [tc["name"] for tc in tool_calls],
            )

        return response_text

    async def _execute_tool(self, tool_name: str, tool_input: dict):
        """Execute a tool with validation, timeout, circuit breaker, and caching."""
        if tool_name not in TOOL_REGISTRY:
            return f"Unknown tool: {tool_name}. Available tools: {', '.join(TOOL_REGISTRY.keys())}"

        circuit = get_tool_circuit(tool_name)
        if not circuit.allow_request():
            return (
                f"Tool '{tool_name}' is temporarily disabled due to repeated failures. "
                f"It will be retried automatically in about {int(circuit.recovery_timeout_s)}s."
            )

        tool_input = validate_tool_args(tool_name, tool_input)
        decision = assess_tool_call(tool_name, tool_input)
        if not decision.allowed:
            approved = False
            if decision.permission.requires_confirmation and confirmation_available():
                approved = await request_confirmation(
                    tool_name,
                    summary=describe_tool_call(tool_name, tool_input),
                    risk=decision.permission.risk.value,
                )
            if not approved:
                record_tool_audit(
                    tool_name,
                    tool_input,
                    allowed=False,
                    success=False,
                    error=decision.reason,
                )
                logger.warning("Tool %s blocked by permission policy: %s", tool_name, decision.reason)
                return f"Tool '{tool_name}' is blocked by policy: {decision.reason}"
            # A human approved via the app; run under a server-granted confirmation.
            with confirmed_scope():
                return await self._run_allowed_tool(tool_name, tool_input, circuit)

        return await self._run_allowed_tool(tool_name, tool_input, circuit)

    async def _run_allowed_tool(self, tool_name: str, tool_input: dict, circuit):
        """Execute a tool that has passed (or been granted) the permission gate."""
        # Replace any model-supplied confirmation flag with the server-verified
        # value, so a tool that acts on it (e.g. send_email sending vs drafting)
        # cannot be driven by a prompt-injected confirmed=true.
        if "confirmed" in tool_input:
            tool_input = {**tool_input, "confirmed": call_is_confirmed(tool_input)}

        cached_result = await tool_cache.get(tool_name, tool_input)
        if cached_result is not None:
            logger.info("Tool %s served from cache.", tool_name)
            perf_tracker.record(f"tool.{tool_name}.cache_hit", 0.0)
            record_event("tool.cache_hit", tool_name=tool_name)
            record_tool_audit(
                tool_name,
                tool_input,
                allowed=True,
                success=True,
                duration_s=0.0,
                result_preview="cache_hit",
            )
            return cached_result

        if tool_name in ("run_command", "run_terminal_command_smart"):
            cmd = tool_input.get("command", "")
            warning = check_dangerous_command(cmd)
            if warning:
                logger.warning("Dangerous command detected for %s: %s", tool_name, warning)
                record_tool_audit(
                    tool_name,
                    tool_input,
                    allowed=False,
                    success=False,
                    error=warning,
                )
                return f"Command blocked for safety: {warning}"

        tool_fn = cast(Callable[..., Any], TOOL_REGISTRY[tool_name])
        timeout_s = get_tool_timeout(tool_name)
        start_time = time.time()

        try:
            with trace_span("tool.execute", tool_name=tool_name, timeout_s=timeout_s):
                if asyncio.iscoroutinefunction(tool_fn):
                    result = await execute_with_timeout(
                        tool_fn(**tool_input),
                        timeout_s=timeout_s,
                        tool_name=tool_name,
                    )
                else:
                    result = tool_fn(**tool_input)

            duration = time.time() - start_time
            self._notify_tool_executed(tool_name, True, duration)
            perf_tracker.record(f"tool.{tool_name}", duration)
            circuit.record_success()

            if isinstance(result, list):
                record_tool_audit(
                    tool_name,
                    tool_input,
                    allowed=True,
                    success=True,
                    duration_s=duration,
                    result_preview=f"list[{len(result)}]",
                )
                return result
            result_str = str(result)
            await tool_cache.put(tool_name, tool_input, result_str)

            await invalidate_on_mutation(tool_name)

            record_tool_audit(
                tool_name,
                tool_input,
                allowed=True,
                success=True,
                duration_s=duration,
                result_preview=result_str,
            )
            return result_str
        except TypeError as e:
            filtered = _accepted_kwargs(tool_fn, tool_input)
            try:
                if filtered == tool_input:
                    # Nothing to drop — the TypeError came from inside the tool,
                    # not from arg binding. Surface it as a tool failure below
                    # instead of retrying (which would just fail identically).
                    raise e
                logger.warning(
                    "Tool %s argument mismatch: %s. Retrying without unrecognized keys: %s",
                    tool_name, e, sorted(set(tool_input) - set(filtered)),
                )
                with trace_span("tool.execute_filtered_kwargs", tool_name=tool_name, timeout_s=timeout_s):
                    if asyncio.iscoroutinefunction(tool_fn):
                        result = await execute_with_timeout(
                            tool_fn(**filtered),
                            timeout_s=timeout_s,
                            tool_name=tool_name,
                        )
                    else:
                        result = tool_fn(**filtered)

                duration = time.time() - start_time
                self._notify_tool_executed(tool_name, True, duration)
                perf_tracker.record(f"tool.{tool_name}", duration)
                circuit.record_success()

                if isinstance(result, list):
                    record_tool_audit(
                        tool_name,
                        tool_input,
                        allowed=True,
                        success=True,
                        duration_s=duration,
                        result_preview=f"list[{len(result)}]",
                    )
                    return result
                result_str = str(result)
                await tool_cache.put(tool_name, tool_input, result_str)
                await invalidate_on_mutation(tool_name)
                record_tool_audit(
                    tool_name,
                    tool_input,
                    allowed=True,
                    success=True,
                    duration_s=duration,
                    result_preview=result_str,
                )
                return result_str
            except Exception as e2:
                logger.error("Tool %s positional fallback also failed: %s", tool_name, e2)
                duration = time.time() - start_time
                self._notify_tool_executed(tool_name, False, duration, str(e2))
                perf_tracker.record(f"tool.{tool_name}.error", duration)
                circuit.record_failure()
                record_tool_audit(
                    tool_name,
                    tool_input,
                    allowed=True,
                    success=False,
                    duration_s=duration,
                    error=str(e2),
                )
                category = classify_error(e2)
                return user_friendly_error(category, context=f"running {tool_name}")
        except TimeoutError:
            duration = time.time() - start_time
            error_msg = f"Timed out after {timeout_s:.0f}s"
            self._notify_tool_executed(tool_name, False, duration, error_msg)
            perf_tracker.record(f"tool.{tool_name}.timeout", duration)
            circuit.record_failure()
            record_tool_audit(
                tool_name,
                tool_input,
                allowed=True,
                success=False,
                duration_s=duration,
                error=error_msg,
            )
            return (
                f"Tool '{tool_name}' timed out after {timeout_s:.0f} seconds. "
                f"The operation may still be running in the background. "
                f"Try again or break the task into smaller steps."
            )
        except Exception as e:
            logger.error("Tool execution error (%s): %s", tool_name, e)
            duration = time.time() - start_time
            self._notify_tool_executed(tool_name, False, duration, str(e))
            perf_tracker.record(f"tool.{tool_name}.error", duration)
            circuit.record_failure()
            record_tool_audit(
                tool_name,
                tool_input,
                allowed=True,
                success=False,
                duration_s=duration,
                error=str(e),
            )
            category = classify_error(e)
            return user_friendly_error(category, context=f"running {tool_name}")

    def _notify_tool_executed(
        self,
        tool_name: str,
        success: bool,
        duration_s: float,
        error: str = "",
    ):
        """Notify learning loop of tool execution outcome."""
        if self._on_tool_executed:
            with contextlib.suppress(Exception):
                self._on_tool_executed(tool_name, success, duration_s, error)
