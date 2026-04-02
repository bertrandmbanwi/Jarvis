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
import logging
import time
from typing import Optional

from jarvis.config import settings
from jarvis.core.llm import JarvisLLM
from jarvis.agent.tools_schema import TOOL_SCHEMAS, TOOL_REGISTRY
from jarvis.core.hardening import (
    get_tool_timeout, execute_with_timeout, validate_tool_args,
    check_dangerous_command, classify_error, user_friendly_error,
    get_tool_circuit, ErrorCategory,
)
from jarvis.core.cache import tool_cache, invalidate_on_mutation
from jarvis.core.perf import perf_tracker
from jarvis.agent.qa_agent import QAAgent, QAResult

logger = logging.getLogger("jarvis.agent")


class AgentExecutor:
    """Executes user requests using Claude's native tool_use agentic loop."""

    def __init__(self, llm: Optional[JarvisLLM] = None):
        self.llm = llm or JarvisLLM()
        self._on_tool_executed = None
        self._qa_agent = QAAgent()
        self._qa_enabled = True

    async def execute(
        self,
        user_input: str,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
    ) -> str:
        """Process a user request using Claude's agentic tool-use loop."""
        logger.info("Agent executing (tier=%s): '%s'", tier, user_input[:100])

        response_text, tool_calls = await self.llm.chat_with_tools(
            user_message=user_input,
            tools=TOOL_SCHEMAS,
            tool_executor=self._execute_tool,
            conversation_history=conversation_history,
            tier=tier,
            max_iterations=10,
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
                            tools=TOOL_SCHEMAS,
                            tool_executor=self._execute_tool,
                            conversation_history=conversation_history,
                            tier=tier,
                            max_iterations=5,
                        )
                        logger.info("QA retry completed.")
                except Exception as e:
                    logger.debug("QA verification skipped (non-critical): %s", e)

        return response_text

    async def execute_stream(
        self,
        user_input: str,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
    ):
        """Stream the final response token by token after tool iterations."""
        logger.info("Agent executing (streaming, tier=%s): '%s'", tier, user_input[:100])

        async for token in self.llm.chat_with_tools_stream(
            user_message=user_input,
            tools=TOOL_SCHEMAS,
            tool_executor=self._execute_tool,
            conversation_history=conversation_history,
            tier=tier,
            max_iterations=10,
        ):
            yield token

    async def execute_subtask(
        self,
        subtask_description: str,
        prior_context: str = "",
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
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

        response_text, tool_calls = await self.llm.chat_with_tools(
            user_message=prompt,
            tools=TOOL_SCHEMAS,
            tool_executor=self._execute_tool,
            conversation_history=conversation_history,
            tier=tier,
            max_iterations=10,
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

        cached_result = await tool_cache.get(tool_name, tool_input)
        if cached_result is not None:
            logger.info("Tool %s served from cache.", tool_name)
            perf_tracker.record(f"tool.{tool_name}.cache_hit", 0.0)
            return cached_result

        if tool_name in ("run_command", "run_terminal_command_smart"):
            cmd = tool_input.get("command", "")
            warning = check_dangerous_command(cmd)
            if warning:
                logger.warning("Dangerous command detected for %s: %s", tool_name, warning)

        tool_fn = TOOL_REGISTRY[tool_name]
        timeout_s = get_tool_timeout(tool_name)
        start_time = time.time()

        try:
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
                return result
            result_str = str(result)
            await tool_cache.put(tool_name, tool_input, result_str)

            await invalidate_on_mutation(tool_name)

            return result_str
        except TypeError as e:
            logger.warning(
                "Tool %s argument mismatch: %s. Input was: %s. Trying positional args.",
                tool_name, e, tool_input,
            )
            try:
                args = list(tool_input.values())
                if asyncio.iscoroutinefunction(tool_fn):
                    result = await execute_with_timeout(
                        tool_fn(*args),
                        timeout_s=timeout_s,
                        tool_name=tool_name,
                    )
                else:
                    result = tool_fn(*args)

                duration = time.time() - start_time
                self._notify_tool_executed(tool_name, True, duration)
                perf_tracker.record(f"tool.{tool_name}", duration)
                circuit.record_success()

                if isinstance(result, list):
                    return result
                result_str = str(result)
                await tool_cache.put(tool_name, tool_input, result_str)
                await invalidate_on_mutation(tool_name)
                return result_str
            except Exception as e2:
                logger.error("Tool %s positional fallback also failed: %s", tool_name, e2)
                duration = time.time() - start_time
                self._notify_tool_executed(tool_name, False, duration, str(e2))
                perf_tracker.record(f"tool.{tool_name}.error", duration)
                circuit.record_failure()
                category = classify_error(e2)
                return user_friendly_error(category, context=f"running {tool_name}")
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            error_msg = f"Timed out after {timeout_s:.0f}s"
            self._notify_tool_executed(tool_name, False, duration, error_msg)
            perf_tracker.record(f"tool.{tool_name}.timeout", duration)
            circuit.record_failure()
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
            try:
                self._on_tool_executed(tool_name, success, duration_s, error)
            except Exception:
                pass
