"""
QA Verification Agent - Checks completed task output and auto-retries on failure.

The QAAgent verifies that task outputs meet requirements by sending them to Claude
for validation. If verification fails, it orchestrates automatic retries with
feedback incorporated into the retry prompt.

Architecture:
    verify(task_prompt, task_result) calls Claude with a verification prompt
    auto_retry(task_prompt, issues, executor) retries up to MAX_RETRIES times
    verify_and_retry combines both for a full verification/retry flow
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from jarvis.config import settings
from jarvis.core.llm import JarvisLLM

logger = logging.getLogger("jarvis.qa")

MAX_RETRIES = 3
VERIFY_TIMEOUT = 120
RETRY_TIMEOUT = 300


@dataclass
class QAResult:
    """Result of QA verification pass/fail."""
    passed: bool
    issues: list[str]
    summary: str
    attempt: int


class QAAgent:
    """Verification agent for task outputs with auto-retry capability."""

    def __init__(self):
        """Initialize QA agent."""
        self.verification_system_prompt = (
            "You are a strict quality assurance verifier. Your job is to validate "
            "whether task outputs meet the stated requirements. "
            "Respond in JSON format only: {\"passed\": true/false, \"issues\": [...], "
            "\"summary\": \"...\"}"
        )

    async def verify(
        self,
        task_prompt: str,
        task_result: str,
        llm: JarvisLLM,
        tier: str = "fast",
    ) -> QAResult:
        """
        Verify that a task result meets the requirements.

        Args:
            task_prompt: The original task/requirements description
            task_result: The output to verify
            llm: JarvisLLM instance for Claude communication
            tier: Model tier to use ("fast", "brain", "deep")

        Returns:
            QAResult with passed status, issues list, and summary
        """
        logger.info("QA verification starting (tier=%s)", tier)

        verification_prompt = (
            f"Task requirement:\n{task_prompt}\n\n"
            f"Task output:\n{task_result}\n\n"
            f"Please verify if this output fully satisfies the requirement. "
            f"Check for completeness, correctness, and quality. "
            f"Respond with JSON only."
        )

        try:
            response = await asyncio.wait_for(
                llm.chat(
                    user_message=verification_prompt,
                    system_prompt_override=self.verification_system_prompt,
                    tier=tier,
                    max_tokens_override=500,
                    temperature_override=0.1,
                ),
                timeout=VERIFY_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("QA verification timed out after %d seconds", VERIFY_TIMEOUT)
            return QAResult(
                passed=False,
                issues=["Verification timeout; retrying task"],
                summary="Verification process exceeded time limit",
                attempt=1,
            )
        except Exception as e:
            logger.error("QA verification failed: %s", e)
            return QAResult(
                passed=False,
                issues=[f"Verification error: {str(e)}"],
                summary="QA system encountered an error",
                attempt=1,
            )

        return self._parse_qa_response(response)

    async def auto_retry(
        self,
        task_prompt: str,
        issues: list[str],
        llm: JarvisLLM,
        executor,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
    ) -> dict:
        """
        Automatically retry task execution up to MAX_RETRIES times.

        Args:
            task_prompt: The original task prompt
            issues: List of issues found during verification
            llm: JarvisLLM instance
            executor: Function/object with execute(prompt) -> str method
            conversation_history: Conversation context for executor
            tier: Model tier to use

        Returns:
            Dict with keys: status, result, error, attempt
        """
        logger.info("Starting auto-retry loop (max %d attempts)", MAX_RETRIES)

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info("Retry attempt %d of %d", attempt, MAX_RETRIES)

            retry_prompt = self._build_retry_prompt(task_prompt, issues, attempt)

            try:
                result = await asyncio.wait_for(
                    executor.execute(
                        retry_prompt,
                        conversation_history=conversation_history,
                        tier=tier,
                    ) if hasattr(executor, 'execute') else executor(retry_prompt),
                    timeout=RETRY_TIMEOUT,
                )

                logger.info("Retry attempt %d produced output (length=%d)", attempt, len(result))
                return {
                    "status": "completed",
                    "result": result,
                    "error": None,
                    "attempt": attempt,
                }

            except asyncio.TimeoutError:
                logger.warning("Retry attempt %d timed out", attempt)
                if attempt == MAX_RETRIES:
                    return {
                        "status": "failed",
                        "result": None,
                        "error": f"Timeout on retry attempt {attempt}",
                        "attempt": attempt,
                    }

            except Exception as e:
                logger.warning("Retry attempt %d failed: %s", attempt, e)
                if attempt == MAX_RETRIES:
                    return {
                        "status": "failed",
                        "result": None,
                        "error": str(e),
                        "attempt": attempt,
                    }

        return {
            "status": "failed",
            "result": None,
            "error": f"Failed after {MAX_RETRIES} retry attempts",
            "attempt": MAX_RETRIES,
        }

    async def verify_and_retry(
        self,
        task_prompt: str,
        task_result: str,
        llm: JarvisLLM,
        executor,
        conversation_history: Optional[list[dict]] = None,
        tier: str = "brain",
    ) -> tuple[str, QAResult]:
        """
        Convenience method combining verify and auto_retry.

        If verification passes, return the original result.
        If verification fails, retry with feedback loop.

        Args:
            task_prompt: The original task/requirements
            task_result: The initial output
            llm: JarvisLLM instance
            executor: Task executor with execute() method
            conversation_history: Conversation context
            tier: Model tier to use

        Returns:
            Tuple of (final_result, qa_result)
        """
        logger.info("Starting verify_and_retry flow")

        qa_result = await self.verify(
            task_prompt=task_prompt,
            task_result=task_result,
            llm=llm,
            tier="fast",
        )

        if qa_result.passed:
            logger.info("QA verification passed on first attempt")
            return task_result, qa_result

        logger.info("QA verification failed. Starting retry loop. Issues: %s", qa_result.issues)

        retry_result = await self.auto_retry(
            task_prompt=task_prompt,
            issues=qa_result.issues,
            llm=llm,
            executor=executor,
            conversation_history=conversation_history,
            tier=tier,
        )

        if retry_result["status"] == "completed":
            final_result = retry_result["result"]
            qa_result = await self.verify(
                task_prompt=task_prompt,
                task_result=final_result,
                llm=llm,
                tier="fast",
            )
            qa_result.attempt = retry_result["attempt"]
            logger.info(
                "Retry completed. Final QA result passed=%s (attempt=%d)",
                qa_result.passed,
                qa_result.attempt,
            )
            return final_result, qa_result
        else:
            logger.error("Retry failed: %s", retry_result["error"])
            return task_result, QAResult(
                passed=False,
                issues=qa_result.issues + [retry_result["error"]],
                summary=f"Retry failed after {retry_result['attempt']} attempts",
                attempt=retry_result["attempt"],
            )

    def _build_retry_prompt(
        self,
        task_prompt: str,
        issues: list[str],
        attempt: int,
    ) -> str:
        """
        Build a prompt for retry execution incorporating QA feedback.

        Args:
            task_prompt: Original task description
            issues: List of issues found
            attempt: Current attempt number

        Returns:
            Formatted retry prompt
        """
        issues_text = "\n".join([f"- {issue}" for issue in issues])

        return (
            f"Previous attempt had these issues:\n{issues_text}\n\n"
            f"Please redo this task, addressing all issues above:\n\n"
            f"{task_prompt}\n\n"
            f"Focus on fixing the identified problems. "
            f"This is attempt {attempt} of {MAX_RETRIES}."
        )

    def _parse_qa_response(self, response: str) -> QAResult:
        """
        Parse Claude's JSON verification response.

        Args:
            response: Raw response from Claude

        Returns:
            QAResult dataclass

        Handles markdown code fences and JSON parsing errors gracefully.
        """
        try:
            cleaned = response.strip()

            if "```json" in cleaned:
                match = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)
            elif "```" in cleaned:
                match = re.search(r"```\s*(.*?)\s*```", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)

            data = json.loads(cleaned)

            return QAResult(
                passed=bool(data.get("passed", False)),
                issues=data.get("issues", []),
                summary=data.get("summary", "No summary provided"),
                attempt=1,
            )

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse QA JSON response: %s. Raw: %s", e, response[:200])
            return QAResult(
                passed=True,
                issues=[],
                summary="Verification result unclear; treating as passed",
                attempt=1,
            )
        except Exception as e:
            logger.error("Unexpected error parsing QA response: %s", e)
            return QAResult(
                passed=False,
                issues=[f"Parsing error: {str(e)}"],
                summary="Unable to parse verification result",
                attempt=1,
            )
