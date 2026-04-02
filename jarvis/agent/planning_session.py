"""
Planning Session Management - Multi-turn planning with decision tracking.

Manages extended planning sessions where JARVIS and the user iterate on
task strategy, requirements, and approach before execution. Tracks decisions,
maintains conversation context, and handles plan modifications.

Architecture:
    PlanningSession tracks decisions, plan state, and conversation history
    ConversationMode manages transitions between chat/planning/browsing
    detect_planning_mode determines if a request needs planning discussion
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from jarvis.core.llm import JarvisLLM

logger = logging.getLogger("jarvis.planning")

# Phrases that bypass planning and go straight to execution
BYPASS_PHRASES = {
    "just do it",
    "figure it out",
    "skip planning",
    "wing it",
    "surprise me",
    "no planning",
    "let's go",
    "start now",
    "don't ask",
    "trust me",
}

# Smart defaults for each task type
SMART_DEFAULTS = {
    "build": {
        "framework": "react",
        "styling": "tailwind",
        "testing": "vitest",
        "bundler": "vite",
    },
    "fix": {
        "approach": "diagnose in-place",
        "testing": "add regression test",
        "documentation": "document fix rationale",
    },
    "feature": {
        "approach": "add to existing structure",
        "testing": "add feature tests",
        "backwards_compat": "ensure backward compatibility",
    },
    "refactor": {
        "approach": "incremental refactoring",
        "testing": "preserve test suite",
        "documentation": "update docstrings",
    },
    "deploy": {
        "backup": "backup before deploy",
        "testing": "test in staging first",
        "rollback": "prepare rollback plan",
    },
}

# Clarifying questions for each task type
QUESTION_MAP = {
    "build": [
        "What framework or stack should we use?",
        "What's the target audience or use case?",
        "What are the core features?",
    ],
    "fix": [
        "What's the exact symptom or error?",
        "When did this start happening?",
        "What's the expected behavior?",
    ],
    "feature": [
        "What problem does this solve?",
        "How should users interact with it?",
        "Any constraints or requirements?",
    ],
    "refactor": [
        "What's the primary goal: performance, readability, or maintainability?",
        "What areas are most problematic?",
        "Are there specific patterns to adopt?",
    ],
    "deploy": [
        "What environment are we deploying to?",
        "Are there zero-downtime requirements?",
        "What's the rollback strategy?",
    ],
}


@dataclass
class Decision:
    """A single planning decision."""
    key: str  # e.g., "framework", "approach", "testing"
    value: str  # decision value
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PlanSummary:
    """Summary of the current plan."""
    description: str
    task_type: str
    project: str
    working_dir: str
    tech_stack: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Convert plan to readable text format."""
        lines = [
            f"Task: {self.task_type.upper()}",
            f"Project: {self.project}",
            f"",
            self.description,
            "",
        ]

        if self.tech_stack:
            lines.append(f"Tech Stack: {', '.join(self.tech_stack)}")

        if self.features:
            lines.append("Features:")
            for feature in self.features:
                lines.append(f"  - {feature}")

        if self.constraints:
            lines.append("Constraints:")
            for constraint in self.constraints:
                lines.append(f"  - {constraint}")

        return "\n".join(lines)


@dataclass
class PlanningDecision:
    """Decision from planning mode detection."""
    needs_planning: bool
    task_type: str
    confidence: float  # 0.0 to 1.0
    missing_info: list[str] = field(default_factory=list)
    smart_defaults: dict = field(default_factory=dict)


class PlanningSession:
    """Manages a multi-turn planning session."""

    def __init__(
        self,
        task_type: str,
        initial_description: str,
        project_name: str = "Unknown",
        working_dir: str = "/",
    ):
        """
        Initialize a planning session.

        Args:
            task_type: Type of task (build, fix, feature, refactor, deploy)
            initial_description: Initial task description
            project_name: Name of the project
            working_dir: Working directory path
        """
        self.decisions: list[Decision] = []
        self.current_plan = PlanSummary(
            description=initial_description,
            task_type=task_type,
            project=project_name,
            working_dir=working_dir,
        )
        self.exchange_count = 0
        self.context_window: list[dict] = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self._closed = False
        self._close_reason = None

        logger.info(
            "Planning session started: task_type=%s, project=%s",
            task_type,
            project_name,
        )

    @property
    def is_active(self) -> bool:
        """Check if session is still active (not closed and not timed out)."""
        if self._closed:
            return False

        # 300 second (5 minute) inactivity timeout
        elapsed = (datetime.now() - self.last_activity).total_seconds()
        if elapsed > 300:
            logger.info("Planning session timed out after %.0f seconds of inactivity", elapsed)
            return False

        return True

    def add_decision(self, key: str, value: str) -> None:
        """
        Record a planning decision and auto-update plan.

        Args:
            key: Decision key (e.g., "framework", "approach")
            value: Decision value
        """
        decision = Decision(key=key, value=value)
        self.decisions.append(decision)
        self.last_activity = datetime.now()

        logger.info("Decision recorded: %s = %s", key, value)

        self._auto_update_plan(key, value)

    def add_exchange(self, role: str, content: str) -> None:
        """
        Add a message to the planning context window.

        Args:
            role: "user" or "assistant"
            content: Message content
        """
        self.context_window.append({
            "role": role,
            "content": content,
        })
        self.exchange_count += 1
        self.last_activity = datetime.now()

        # Keep window at max 20 entries
        if len(self.context_window) > 20:
            self.context_window = self.context_window[-20:]

        logger.debug("Exchange %d added to context window", self.exchange_count)

    def modify_plan(self, modification: str) -> None:
        """
        Handle plan modification requests.

        Patterns:
            "instead of X, do Y"
            "add X to the plan"
            "remove X from the plan"
            "change X to Y"

        Args:
            modification: Modification request text
        """
        mod_lower = modification.lower()
        logger.info("Plan modification requested: %s", modification[:100])

        if "instead of" in mod_lower:
            pattern = r"instead of ([^,]+),?\s+(?:do\s+)?(.+)"
            match = re.search(pattern, mod_lower)
            if match:
                old, new = match.groups()
                logger.info("Replacing: '%s' with '%s'", old.strip(), new.strip())
                self.current_plan.description = self.current_plan.description.replace(
                    old.strip(), new.strip()
                )

        elif any(x in mod_lower for x in ["add", "include"]):
            pattern = r"add (?:to the plan|the plan)?\s*:?\s*(.+)"
            match = re.search(pattern, mod_lower)
            if match:
                item = match.group(1).strip()
                if item not in self.current_plan.features:
                    self.current_plan.features.append(item)
                    logger.info("Added to features: %s", item)

        elif "remove" in mod_lower or "drop" in mod_lower:
            pattern = r"remove (?:from the plan|the plan)?\s*:?\s*(.+)"
            match = re.search(pattern, mod_lower)
            if match:
                item = match.group(1).strip()
                self.current_plan.features = [
                    f for f in self.current_plan.features
                    if item not in f.lower()
                ]
                logger.info("Removed from features: %s", item)

        elif "change" in mod_lower or "replace" in mod_lower:
            pattern = r"change (?:the\s+)?(\w+)\s+(?:from|to)\s+(.+?)\s+(?:to|with)\s+(.+)"
            match = re.search(pattern, mod_lower)
            if match:
                aspect, old, new = match.groups()
                self.add_decision(aspect.strip(), new.strip())

        self.last_activity = datetime.now()

    def get_context(self) -> str:
        """
        Get formatted context string for LLM injection.

        Returns:
            Formatted context including plan, decisions, and recent exchanges
        """
        context_parts = [
            "=== PLANNING SESSION CONTEXT ===",
            "",
            self.current_plan.to_text(),
            "",
            "=== DECISIONS MADE ===",
        ]

        if self.decisions:
            for decision in self.decisions:
                context_parts.append(f"- {decision.key}: {decision.value}")
        else:
            context_parts.append("(None yet)")

        context_parts.append("")
        context_parts.append("=== RECENT EXCHANGES ===")

        for exchange in self.context_window[-5:]:
            role = exchange["role"].upper()
            content = exchange["content"][:100] + ("..." if len(exchange["content"]) > 100 else "")
            context_parts.append(f"{role}: {content}")

        return "\n".join(context_parts)

    def close(self, reason: str = "Completed") -> None:
        """
        Close the planning session.

        Args:
            reason: Reason for closing
        """
        self._closed = True
        self._close_reason = reason
        elapsed = (datetime.now() - self.created_at).total_seconds()
        logger.info(
            "Planning session closed (%s) after %.0f seconds, %d exchanges",
            reason,
            elapsed,
            self.exchange_count,
        )

    def reset(self) -> None:
        """Reset the session (clear decisions and context)."""
        self.decisions.clear()
        self.context_window.clear()
        self.exchange_count = 0
        self._closed = False
        self.last_activity = datetime.now()
        logger.info("Planning session reset")

    def _auto_update_plan(self, key: str, value: str) -> None:
        """
        Auto-update plan based on known decision keys.

        Args:
            key: Decision key
            value: Decision value
        """
        if key == "framework":
            if "react" in value.lower():
                self.current_plan.tech_stack = ["React"]
        elif key == "approach":
            self.current_plan.description += f" (Approach: {value})"
        elif key == "testing":
            if "test" in value.lower():
                self.current_plan.tech_stack.append(value)


class ConversationMode:
    """Manages conversation mode state (chat, planning, browsing)."""

    def __init__(self):
        """Initialize conversation mode manager."""
        self._mode = "chat"
        self._planning_session: Optional[PlanningSession] = None
        self._browsing_active = False

    @property
    def mode(self) -> str:
        """Get current mode: chat, planning, or browsing."""
        return self._mode

    def enter_planning(
        self,
        task_type: str,
        description: str,
        project_name: str = "Unknown",
        working_dir: str = "/",
    ) -> PlanningSession:
        """
        Enter planning mode.

        Args:
            task_type: Type of task
            description: Task description
            project_name: Project name
            working_dir: Working directory

        Returns:
            New PlanningSession object
        """
        self._mode = "planning"
        self._planning_session = PlanningSession(
            task_type=task_type,
            initial_description=description,
            project_name=project_name,
            working_dir=working_dir,
        )
        logger.info("Entered planning mode")
        return self._planning_session

    def enter_browsing(self) -> None:
        """Enter browsing mode."""
        self._mode = "browsing"
        self._browsing_active = True
        logger.info("Entered browsing mode")

    def return_to_chat(self) -> None:
        """Return to chat mode."""
        prev_mode = self._mode
        self._mode = "chat"
        self._browsing_active = False

        if self._planning_session and self._planning_session.is_active:
            self._planning_session.close("Returned to chat")

        logger.info("Returned to chat mode (was: %s)", prev_mode)

    def is_planning(self) -> bool:
        """Check if currently in planning mode."""
        return (
            self._mode == "planning"
            and self._planning_session is not None
            and self._planning_session.is_active
        )

    def get_planning_session(self) -> Optional[PlanningSession]:
        """Get current planning session if active."""
        if self.is_planning():
            return self._planning_session
        return None


async def detect_planning_mode(
    user_text: str,
    llm: Optional[JarvisLLM] = None,
    force_bypass: bool = False,
) -> PlanningDecision:
    """
    Determine if a user request needs planning discussion.

    Uses Claude for classification if available, falls back to heuristics.

    Args:
        user_text: User message to analyze
        llm: Optional JarvisLLM instance for classification
        force_bypass: If True, always return needs_planning=False

    Returns:
        PlanningDecision with planning recommendation
    """
    user_lower = user_text.lower()

    if force_bypass:
        logger.info("Planning mode forced bypass")
        return PlanningDecision(
            needs_planning=False,
            task_type="unknown",
            confidence=1.0,
        )

    # Quick check: bypass phrases
    if any(phrase in user_lower for phrase in BYPASS_PHRASES):
        logger.info("User used bypass phrase; no planning needed")
        return PlanningDecision(
            needs_planning=False,
            task_type="unknown",
            confidence=0.95,
        )

    # Heuristic: check task type
    task_type = _detect_task_type(user_text)

    # If we have LLM available, use it for better classification
    if llm is not None:
        return await _classify_with_llm(user_text, task_type, llm)

    # Fallback to heuristic
    needs_planning = _should_plan_heuristic(user_text, task_type)
    confidence = 0.7 if needs_planning else 0.6

    missing_info = []
    if needs_planning:
        missing_info = QUESTION_MAP.get(task_type, [])[:2]

    smart_defaults = SMART_DEFAULTS.get(task_type, {})

    return PlanningDecision(
        needs_planning=needs_planning,
        task_type=task_type,
        confidence=confidence,
        missing_info=missing_info,
        smart_defaults=smart_defaults,
    )


def _detect_task_type(text: str) -> str:
    """
    Heuristically detect task type from user text.

    Returns: One of "build", "fix", "feature", "refactor", "deploy", "unknown"
    """
    text_lower = text.lower()

    if any(x in text_lower for x in ["build", "create", "make", "develop"]):
        return "build"
    elif any(x in text_lower for x in ["fix", "bug", "error", "issue", "broken"]):
        return "fix"
    elif any(x in text_lower for x in ["add", "feature", "implement", "new"]):
        return "feature"
    elif any(x in text_lower for x in ["refactor", "clean", "improve", "optimize"]):
        return "refactor"
    elif any(x in text_lower for x in ["deploy", "release", "ship", "launch"]):
        return "deploy"

    return "unknown"


def _should_plan_heuristic(text: str, task_type: str) -> bool:
    """
    Heuristic check: should this request trigger planning?

    Complex, multi-faceted tasks should go through planning.
    Simple, well-specified tasks can skip it.

    Args:
        text: User message
        task_type: Detected task type

    Returns:
        True if planning is recommended
    """
    # These task types always benefit from planning
    if task_type in ["build", "deploy", "refactor"]:
        return True

    # Check for complexity indicators
    complexity_indicators = [
        "?",  # Question suggests uncertainty
        "how",
        "should",
        "what's the best",
        "multiple",
        "depends",
    ]

    complexity_score = sum(1 for ind in complexity_indicators if ind in text.lower())
    return complexity_score >= 2


async def _classify_with_llm(
    user_text: str,
    task_type: str,
    llm: JarvisLLM,
) -> PlanningDecision:
    """
    Use Claude to classify if planning is needed.

    Args:
        user_text: User message
        task_type: Detected task type
        llm: JarvisLLM instance

    Returns:
        PlanningDecision from Claude
    """
    classification_prompt = (
        f"Analyze this request and determine if it needs a planning discussion:\n\n"
        f"Task type: {task_type}\n"
        f"User request: {user_text}\n\n"
        f"Respond with JSON only:\n"
        f"{{\n"
        f'  "needs_planning": true/false,\n'
        f'  "confidence": 0.0-1.0,\n'
        f'  "missing_info": ["question1", "question2"],\n'
        f'  "reasoning": "..."\n'
        f"}}\n\n"
        f"Consider: Is the request vague, complex, multi-faceted, or ambiguous? "
        f"Or is it clear and straightforward?"
    )

    try:
        response = await asyncio.wait_for(
            llm.chat(
                user_message=classification_prompt,
                tier="fast",
                max_tokens_override=300,
                temperature_override=0.3,
            ),
            timeout=10.0,
        )

        # Parse JSON response
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return PlanningDecision(
                needs_planning=bool(data.get("needs_planning", False)),
                task_type=task_type,
                confidence=float(data.get("confidence", 0.7)),
                missing_info=data.get("missing_info", []),
                smart_defaults=SMART_DEFAULTS.get(task_type, {}),
            )
    except Exception as e:
        logger.warning("LLM classification failed: %s. Using heuristic.", e)

    # Fallback to heuristic
    needs_planning = _should_plan_heuristic(user_text, task_type)
    return PlanningDecision(
        needs_planning=needs_planning,
        task_type=task_type,
        confidence=0.6,
        missing_info=QUESTION_MAP.get(task_type, [])[:2],
        smart_defaults=SMART_DEFAULTS.get(task_type, {}),
    )
