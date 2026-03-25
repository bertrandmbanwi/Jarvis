"""
JARVIS Task Planner

Uses Claude to decompose complex user requests into ordered subtask chains.
Simple requests pass through unchanged; complex multi-step requests get
broken into a plan that the executor runs step by step.

The planner makes two key decisions:
1. Should this request be decomposed? (complexity check)
2. If yes, what are the subtasks, in what order, with what dependencies?

Complexity heuristics (checked BEFORE calling the LLM):
- Multiple verbs / action phrases ("search X, then open Y, and email Z")
- Explicit sequencing words ("first", "then", "after that", "finally")
- Compound requests joined by "and" with different action types
- Requests mentioning multiple tools or domains (browser + email + file)

If heuristics are ambiguous, the planner asks Claude (fast tier) to decide.
This keeps costs low: simple requests never touch the planner LLM at all.
"""
import json
import logging
import re
from typing import Optional

from jarvis.config import settings
from jarvis.agent.task_tracker import TaskPlan, TaskTracker

logger = logging.getLogger("jarvis.agent.planner")

MAX_SUBTASKS = 8

_SEQUENCE_MARKERS = [
    r"\bthen\b",
    r"\bafter that\b",
    r"\bnext\b",
    r"\bfinally\b",
    r"\bfirst\b",
    r"\bonce (?:you|that|it)'?s? (?:done|finished|complete)",
    r"\bstep \d",
    r"\band then\b",
    r"\bfollowed by\b",
    r"\bbefore you\b",
    r"\bwhen (?:you're|that's) done\b",
]

_ACTION_VERBS = [
    "search", "find", "look up", "research",
    "open", "navigate", "browse", "go to",
    "send", "email", "message", "notify",
    "create", "write", "draft", "compose",
    "save", "download", "export",
    "read", "check", "review", "summarize",
    "run", "execute", "install",
    "set", "change", "update", "modify",
    "schedule", "remind", "add to calendar",
]

_PLANNING_SYSTEM_PROMPT = """\
You are a task planning module for JARVIS, a personal AI assistant.

Your job: given a user request, determine if it requires multiple distinct steps,
and if so, break it into an ordered list of subtasks.

Rules:
- Each subtask should be a single, clear action that can be executed independently
  (given the results of prior steps).
- Subtasks should be in execution order.
- Keep subtask titles short (under 60 chars) and descriptions actionable.
- Do NOT decompose simple, single-action requests. Return needs_decomposition: false.
- Maximum {max_subtasks} subtasks per plan.
- If a step depends on the output of a previous step, note that in the description.

Respond ONLY with valid JSON in this exact format (no markdown, no code fences):

For simple requests:
{{"needs_decomposition": false, "reason": "Single action request"}}

For complex requests:
{{
  "needs_decomposition": true,
  "goal_summary": "Brief description of the overall goal",
  "subtasks": [
    {{
      "title": "Short action title",
      "description": "What to do in this step, including any context needed"
    }},
    ...
  ]
}}
""".format(max_subtasks=MAX_SUBTASKS)

_COMPLEXITY_CHECK_PROMPT = """\
Decide: does this user request require multiple distinct steps to complete,
or is it a single action? Consider whether different tools or actions are needed.

Request: "{request}"

Respond with ONLY "simple" or "complex". Nothing else.
"""


def _has_sequence_markers(text: str) -> bool:
    """Check if the text contains explicit sequencing language."""
    text_lower = text.lower()
    for pattern in _SEQUENCE_MARKERS:
        if re.search(pattern, text_lower):
            return True
    return False


def _count_action_verbs(text: str) -> int:
    """Count distinct action verb phrases in the text."""
    text_lower = text.lower()
    found = set()
    for verb in _ACTION_VERBS:
        if verb in text_lower:
            # Group similar verbs to avoid double-counting
            root = verb.split()[0]
            found.add(root)
    return len(found)


def _has_compound_actions(text: str) -> bool:
    """Check for multiple distinct actions joined by conjunctions."""
    text_lower = text.lower()
    parts = re.split(r'\band\b|\bthen\b|,', text_lower)
    action_parts = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        for verb in _ACTION_VERBS:
            if verb in part:
                action_parts += 1
                break
    return action_parts >= 2


def needs_decomposition_heuristic(text: str) -> Optional[bool]:
    """Quick heuristic check for whether a request needs decomposition."""
    text_stripped = text.strip()

    if len(text_stripped) < 30:
        return False

    if _has_sequence_markers(text_stripped):
        return True

    verb_count = _count_action_verbs(text_stripped)
    if verb_count >= 3:
        return True

    if _has_compound_actions(text_stripped) and verb_count >= 2:
        return None

    if verb_count <= 1:
        return False

    return None


class TaskPlanner:
    """Decomposes complex user requests into ordered subtask plans."""

    def __init__(self, llm=None):
        self.llm = llm
        self.tracker = TaskTracker()
        self._get_learning_context = None

    async def should_decompose(self, user_input: str) -> bool:
        """Decide whether a request needs task decomposition."""
        heuristic_result = needs_decomposition_heuristic(user_input)
        if heuristic_result is not None:
            logger.info(
                "Decomposition heuristic: %s (input: '%s')",
                "yes" if heuristic_result else "no",
                user_input[:80],
            )
            return heuristic_result

        if not self.llm:
            return False

        try:
            prompt = _COMPLEXITY_CHECK_PROMPT.format(request=user_input[:500])
            response = await self.llm.chat(prompt, tier="fast")
            is_complex = "complex" in response.lower()
            logger.info(
                "Decomposition LLM check: %s (input: '%s')",
                "complex" if is_complex else "simple",
                user_input[:80],
            )
            return is_complex
        except Exception as e:
            logger.warning("Complexity check failed: %s. Defaulting to no decomposition.", e)
            return False

    async def create_plan(
        self,
        user_input: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> Optional[TaskPlan]:
        """Decompose a user request into a structured task plan."""
        if not self.llm:
            logger.warning("No LLM available for planning.")
            return None

        try:
            system_prompt = _PLANNING_SYSTEM_PROMPT
            if self._get_learning_context:
                try:
                    learning_ctx = self._get_learning_context()
                    if learning_ctx:
                        system_prompt = system_prompt + "\n" + learning_ctx
                except Exception as e:
                    logger.debug("Could not get learning context: %s", e)

            response = await self.llm.chat(
                user_message=user_input,
                conversation_history=conversation_history,
                system_prompt_override=system_prompt,
                tier="brain",
            )

            plan_data = self._parse_plan_response(response)
            if not plan_data:
                return None

            if not plan_data.get("needs_decomposition", False):
                logger.info(
                    "Planner says no decomposition needed: %s",
                    plan_data.get("reason", "single action"),
                )
                return None

            subtasks = plan_data.get("subtasks", [])
            if not subtasks:
                logger.warning("Planner returned no subtasks.")
                return None

            if len(subtasks) > MAX_SUBTASKS:
                logger.warning(
                    "Plan has %d subtasks, capping at %d.",
                    len(subtasks), MAX_SUBTASKS,
                )
                subtasks = subtasks[:MAX_SUBTASKS]

            goal_summary = plan_data.get("goal_summary", user_input[:80])

            plan = self.tracker.create_plan(
                original_request=user_input,
                goal_summary=goal_summary,
                subtasks=subtasks,
            )

            logger.info(
                "Plan created: '%s' with %d subtasks.",
                goal_summary, len(plan.subtasks),
            )
            return plan

        except Exception as e:
            logger.error("Planning failed: %s", e)
            return None

    def _parse_plan_response(self, response: str) -> Optional[dict]:
        """Parse the planner's JSON response, handling markdown code fences."""
        text = response.strip()

        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*\n?', '', text)
            text = re.sub(r'\n?```\s*$', '', text)
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse planner response as JSON: %s", text[:200])
        return None

    def get_active_plan(self) -> Optional[TaskPlan]:
        """Get the currently active plan, if any."""
        return self.tracker.active_plan

    def get_plan_status(self) -> str:
        """Get human-readable status of the active plan."""
        return self.tracker.get_plan_status()
