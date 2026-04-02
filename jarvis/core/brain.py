"""Central orchestration service with agentic executor and task decomposition."""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jarvis.config import settings
from jarvis.core.llm import JarvisLLM
from jarvis.memory.store import MemoryStore
from jarvis.agent.executor import AgentExecutor
from jarvis.agent.planner import TaskPlanner
from jarvis.agent.task_tracker import SubtaskStatus
from jarvis.agent.tools_schema import (
    set_active_planner, set_active_learning, set_active_proactive,
    set_active_coordinator, set_active_memory, TOOL_SCHEMAS, get_tool_names,
)
from jarvis.agent.learning import LearningLoop
from jarvis.agent.coordinator import AgentCoordinator, AgentType
from jarvis.core.proactive import ProactiveEngine
from jarvis.core.hardening import sanitize_user_input
from jarvis.core.perf import perf_tracker, estimate_tokens, estimate_request_cost
from jarvis.core.dispatch_registry import DispatchRegistry, SuccessTracker
from jarvis.core.monitor import ConversationMonitor
from jarvis.agent.suggestions import suggest_followup, suggest_task_followup
from jarvis.agent.evolution_pipeline import EvolutionPipeline
from jarvis.tools.work_session import WorkSession

CONVERSATION_FILE = settings.DATA_DIR / "conversation_history.json"
MAX_CONVERSATION_TURNS = 100

logger = logging.getLogger("jarvis.brain")

# Phrases indicating complex reasoning; only multi-word to avoid false triggers.
DEEP_KEYWORDS = [
    "analyze in detail",
    "compare and contrast",
    "evaluate the pros and cons",
    "explain in detail",
    "write code for",
    "architect a solution",
    "debug this",
    "troubleshoot this",
    "step by step",
    "think through",
    "deep analysis",
    "detailed breakdown",
]

# Patterns for purely conversational messages.
_CHAT_ONLY_PATTERNS = [
    r"^(?:hi|hello|hey|good (?:morning|afternoon|evening|night))[\s!.,]*$",
    r"^(?:thanks?|thank you|thx|cheers)[\s!.,]*$",
    r"^(?:bye|goodbye|see you(?: later| soon| around| tomorrow)?|later|good night|that's it|that's all|i'm done|we're done)[\s!.,]*$",
    r"^(?:that's it for now|that's all for now|nothing else|no more questions)[\s!.,]*$",
    r"^(?:ok|okay|alright|sure|got it|cool|nice|great|awesome|perfect|right)[\s!.,]*$",
    r"^(?:how are you(?: today| doing)?|what's up|you good|how'?s it going)[\s!?,]*$",
    r"^(?:who are you|what are you|what is your name|what's your name)[\s!?,]*$",
    r"^(?:tell me a joke|say something funny|make me laugh)[\s!?,]*$",
    r"^(?:have a good (?:one|day|night|evening)|take care|talk later|peace)[\s!.,]*$",
    r"^(?:you're welcome|no problem|no worries|all good|it's fine)[\s!.,]*$",
    r"^(?:yes|no|yeah|yep|nope|nah)[\s!.,]*$",
    # Conversational questions about JARVIS or general small talk
    r"^(?:what are you doing|what do you do|what can you do)[\s!?,]*$",
    r"^(?:my question is,?\s*)?how are you[\w\s]*[\s!?,]*$",
    r"^(?:are you (?:there|awake|ready|listening|alive|okay|ok))[\s!?,]*$",
    r"^(?:what'?s? (?:your|the) (?:plan|deal|status|update))[\s!?,]*$",
    r"^(?:never\s*mind|forget it|skip it|doesn'?t matter|don'?t worry)[\s!.,]*$",
]


def _is_single_chat(text: str) -> bool:
    """Check if text is purely conversational."""
    text_clean = text.strip().lower()
    if not text_clean:
        return True  # Empty fragments are not actionable
    for pattern in _CHAT_ONLY_PATTERNS:
        if re.match(pattern, text_clean, re.IGNORECASE):
            return True
    return False


def _is_chat_only(text: str) -> bool:
    """Check if message is purely conversational by testing each clause."""
    text_clean = text.strip().lower()

    if _is_single_chat(text_clean):
        return True

    sentence_parts = re.split(r'[.!?;]+', text_clean)
    sentence_parts = [s.strip() for s in sentence_parts if s.strip()]

    if not sentence_parts:
        return False

    for part in sentence_parts:
        if _is_single_chat(part):
            continue
        sub_parts = [sp.strip() for sp in part.split(",") if sp.strip()]
        if not all(_is_single_chat(sp) for sp in sub_parts):
            return False

    return True


# Patterns that indicate the user wants to shut down JARVIS (intercepted to prevent system shutdown).
_JARVIS_SHUTDOWN_PATTERNS = [
    # "shut down jarvis/javies/javis" (forgiving Whisper misspellings)
    r"\b(?:shut\s*down|shutdown|power\s*off|turn\s*off)\s*(?:jarvis|javies?|javis|yourself|the\s*system|the\s*assistant)\b",
    r"\b(?:jarvis|javies?|javis|system)\s*(?:shut\s*down|shutdown|power\s*off|turn\s*off)\b",
    r"\b(?:exit|quit|stop|terminate|kill)\s*(?:jarvis|javies?|javis|yourself|the\s*system|the\s*assistant)\b",
    r"\b(?:go\s*(?:to\s*)?(?:sleep|offline)|power\s*down)\b",
    r"^(?:shut\s*down|shutdown|power\s*off|turn\s*off)[\s!.,]*$",
    r"\b(?:shut\s*down|quit|exit)\s*now\b",
]


def _is_jarvis_shutdown(text: str) -> bool:
    """Check if the user wants to shut down JARVIS (not the computer)."""
    text_clean = text.strip().lower()
    for pattern in _JARVIS_SHUTDOWN_PATTERNS:
        if re.search(pattern, text_clean):
            return True
    return False


def _select_tier(text: str) -> str:
    """Select model tier based on complexity; requires 2 signals for deep upgrade."""
    text_lower = text.lower().strip()

    if _is_chat_only(text):
        return "fast"

    # Short messages with no action verbs and no question words that imply lookup
    # are likely conversational; use fast tier to save cost
    _LOOKUP_WORDS = {"weather", "time", "news", "price", "stock", "email", "note", "calendar", "remind"}
    if len(text_lower) < 60:
        has_lookup = any(w in text_lower for w in _LOOKUP_WORDS)
        if not has_lookup:
            from jarvis.agent.planner import _count_action_verbs
            if _count_action_verbs(text_lower) == 0:
                return "fast"

    deep_signals = 0
    matched_keywords = []
    for keyword in DEEP_KEYWORDS:
        if keyword in text_lower:
            deep_signals += 1
            matched_keywords.append(keyword)

    token_estimate = estimate_tokens(text)
    if token_estimate > 200:
        deep_signals += 1
    if text.count("\n") > 5:
        deep_signals += 1

    if deep_signals >= 2:
        est_cost_deep = estimate_request_cost(token_estimate + 2000, 2000, "deep")
        est_cost_brain = estimate_request_cost(token_estimate + 2000, 2000, "brain")
        cost_premium = est_cost_deep - est_cost_brain

        if cost_premium > 0.10:
            if deep_signals >= 3:
                logger.info(
                    "Tier routing: deep (signals: %d, keywords: %s, premium: $%.3f)",
                    deep_signals, matched_keywords, cost_premium,
                )
                return "deep"
            else:
                perf_tracker.record_tier_downgrade("deep", "brain", "cost_premium_high")
                logger.info(
                    "Tier routing: brain (downgraded, premium $%.3f too high)",
                    cost_premium,
                )
                return "brain"

        logger.info(
            "Tier routing: deep (signals: %d, keywords: %s)",
            deep_signals, matched_keywords,
        )
        return "deep"

    return "brain"


@dataclass
class ConversationTurn:
    """Conversation turn with metadata."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    tier_used: str = ""
    tool_calls: list = field(default_factory=list)


class JarvisBrain:
    """Central orchestrator for LLM, memory, agent, and response generation."""

    def __init__(self):
        self.llm = JarvisLLM()
        self.memory = MemoryStore()
        self.agent = AgentExecutor()
        self.planner = TaskPlanner()
        self.learning = LearningLoop()
        self.coordinator = AgentCoordinator()
        self.proactive = ProactiveEngine()
        self.dispatch = DispatchRegistry()
        self.monitor = ConversationMonitor()
        self.success_tracker = SuccessTracker()
        self.evolution = EvolutionPipeline()
        self.work_session: Optional[WorkSession] = None
        self.conversation: list[ConversationTurn] = []
        self._initialized = False
        self._shutdown_requested = False
        self._conversation_file = CONVERSATION_FILE
        self._on_plan_progress = None  # Callback for broadcasting plan progress via WebSocket
        self._last_plan = None

    async def initialize(self) -> bool:
        """Initialize and check all dependencies."""
        logger.info("Initializing JARVIS brain...")

        llm_ok = await self.llm.check_health()
        if not llm_ok:
            logger.error(
                "No LLM backend available. "
                "Set ANTHROPIC_API_KEY in .env or start Ollama."
            )
            return False

        logger.info("LLM active backend: %s", self.llm.active_backend)
        self.memory.initialize()

        self.agent.llm = self.llm
        self.planner.llm = self.llm
        self.agent._on_tool_executed = self.learning.record_tool_call

        set_active_planner(self.planner)
        set_active_learning(self.learning)
        set_active_proactive(self.proactive)

        set_active_memory(self.memory)

        self.coordinator.initialize(get_tool_names())
        set_active_coordinator(self.coordinator)

        self.planner._get_learning_context = self.learning.get_planner_context

        # Wire dispatch registry context into system prompt awareness
        logger.info(
            "Dispatch registry initialized (%d active dispatches).",
            len(self.dispatch.get_active()),
        )

        self.learning.initialize()
        self.learning.backfill_from_plan_files()

        # Success tracker and evolution pipeline are initialized in __init__
        logger.info("Success tracker ready (SQLite tables ensured).")
        logger.info(
            "Evolution pipeline ready (history: %d cycles).",
            len(self.evolution._evolution_history),
        )

        # Restore persistent work session if one exists
        try:
            restored = WorkSession.restore()
            if restored:
                self.work_session = restored
                logger.info("Work session restored: %s", restored.session_id)
        except Exception as e:
            logger.debug("No prior work session to restore: %s", e)

        self._load_conversation()
        self.proactive.start()

        self._initialized = True
        logger.info(
            "JARVIS brain initialized (backend: %s, model: %s, restored %d turns).",
            self.llm.active_backend,
            self.llm.get_active_model(),
            len(self.conversation),
        )
        return True

    async def process(self, user_input: str) -> str:
        """Process user message and return response."""
        if not self._initialized:
            return "I am not fully initialized yet. Please wait a moment."

        user_input = sanitize_user_input(user_input)
        if not user_input:
            return "I didn't catch that. Could you say something?"

        start_time = time.time()
        logger.info("Processing: '%s'", user_input[:100])

        self.proactive.mark_interaction()

        if _is_jarvis_shutdown(user_input):
            logger.info("JARVIS shutdown requested by user.")
            self._shutdown_requested = True
            return "Shutting down JARVIS. All systems offline. Goodbye, sir."

        self.conversation.append(ConversationTurn(role="user", content=user_input))

        if len(self.conversation) > MAX_CONVERSATION_TURNS:
            self.conversation = self.conversation[-MAX_CONVERSATION_TURNS:]

        history = [
            {"role": turn.role, "content": turn.content}
            for turn in self.conversation[-20:]
        ][:-1]

        tier = _select_tier(user_input)

        if tier == "fast" and _is_chat_only(user_input):
            logger.info("Routing to CHAT mode [tier: fast].")
            enriched_context = self.memory.get_enriched_context(user_input, top_k=3)
            enriched_input = f"{enriched_context}\n\nUser: {user_input}" if enriched_context else user_input
            response = await self.llm.chat(enriched_input, history, tier="fast")
        else:
            should_plan = await self.planner.should_decompose(user_input)

            if should_plan:
                logger.info("Routing to PLAN+EXECUTE mode [tier: %s].", tier)
                response = await self._execute_plan(user_input, history, tier)
            else:
                logger.info("Routing to AGENT mode [tier: %s].", tier)
                response = await self.agent.execute(user_input, history, tier=tier)

        self.conversation.append(
            ConversationTurn(role="assistant", content=response, tier_used=tier)
        )

        # Monitor response quality
        try:
            quality_issues = self.monitor.analyze_response(user_input, response)
            if quality_issues:
                logger.info("Quality issues detected: %s", quality_issues)
        except Exception as e:
            logger.debug("Monitor analysis failed (non-critical): %s", e)

        self.memory.add(
            text=f"User: {user_input}\nJARVIS: {response}",
            metadata={
                "type": "agent" if tier != "fast" else "conversation",
                "tier": tier,
                "timestamp": time.time(),
            },
        )

        self.memory.process_exchange(
            user_message=user_input,
            assistant_response=response,
            tier=tier,
        )

        # Track experiment outcomes and suggestions for completed plans
        task_elapsed = time.time() - start_time
        if hasattr(self, '_last_plan') and self._last_plan:
            try:
                self.planner.record_experiment_outcome(self._last_plan, True)
            except Exception as e:
                logger.debug("Experiment tracking failed: %s", e)

            # Record in success tracker and evolution pipeline
            try:
                self.success_tracker.log_task(
                    task_type="build",
                    prompt=user_input[:200],
                    success=True,
                    duration_seconds=task_elapsed,
                )
                self.evolution.on_task_complete(
                    task_type="build",
                    success=True,
                    duration=task_elapsed,
                )
            except Exception as e:
                logger.debug("Success/evolution tracking failed (non-critical): %s", e)

            # Proactive follow-up suggestions: sync version first
            try:
                suggestion = suggest_followup(
                    task_type="build",
                    task_description=user_input[:200],
                    working_dir=str(settings.JARVIS_HOME),
                )
                if suggestion:
                    response += f"\n\nBy the way, sir: {suggestion.text}"
                    logger.info("Follow-up suggestion appended: %s", suggestion.action_type)
            except Exception as e:
                logger.debug("Suggestion generation failed (non-critical): %s", e)

            # Async follow-up suggestions (richer, checks project files)
            try:
                async_suggestion = await suggest_task_followup(
                    task_type="build",
                    task_description=user_input[:200],
                    working_dir=str(settings.JARVIS_HOME),
                )
                if async_suggestion and async_suggestion.text:
                    response += f"\n\n{async_suggestion.text}"
                    logger.info("Async follow-up appended: %s", async_suggestion.action_type)
            except Exception as e:
                logger.debug("Async suggestion failed (non-critical): %s", e)

            self._last_plan = None

        self._save_conversation()
        elapsed = time.time() - start_time
        perf_tracker.record_request(elapsed, tier)
        perf_tracker.record(f"request.{tier}", elapsed)

        logger.info(
            "Response generated in %.2fs [tier: %s]: '%s'",
            elapsed, tier, response[:100],
        )

        return response

    async def process_stream(self, user_input: str):
        """Stream response token by token. Pure chat only; agent mode returns complete."""
        if not self._initialized:
            yield "I am not fully initialized yet."
            return

        user_input = sanitize_user_input(user_input)
        if not user_input:
            yield "I didn't catch that. Could you say something?"
            return

        self.proactive.mark_interaction()

        tier = _select_tier(user_input)

        if tier == "fast" and _is_chat_only(user_input):
            self.conversation.append(ConversationTurn(role="user", content=user_input))

            if len(self.conversation) > MAX_CONVERSATION_TURNS:
                self.conversation = self.conversation[-MAX_CONVERSATION_TURNS:]

            history = [
                {"role": turn.role, "content": turn.content}
                for turn in self.conversation[-20:]
            ][:-1]

            full_response = []
            async for token in self.llm.chat_stream(user_input, history, tier="fast"):
                full_response.append(token)
                yield token

            complete = "".join(full_response)
            self.conversation.append(
                ConversationTurn(role="assistant", content=complete, tier_used="fast")
            )
            self.memory.add(
                text=f"User: {user_input}\nJARVIS: {complete}",
                metadata={"type": "conversation", "tier": "fast", "timestamp": time.time()},
            )
            self._save_conversation()
        else:
            self.conversation.append(ConversationTurn(role="user", content=user_input))

            if len(self.conversation) > MAX_CONVERSATION_TURNS:
                self.conversation = self.conversation[-MAX_CONVERSATION_TURNS:]

            history = [
                {"role": turn.role, "content": turn.content}
                for turn in self.conversation[-20:]
            ][:-1]

            should_plan = await self.planner.should_decompose(user_input)

            if should_plan:
                logger.info("Routing to PLAN+EXECUTE mode (streaming) [tier: %s].", tier)
                complete = await self._execute_plan(user_input, history, tier)
                yield complete
            else:
                logger.info("Routing to AGENT mode (streaming) [tier: %s].", tier)
                full_response = []
                async for token in self.agent.execute_stream(user_input, history, tier=tier):
                    full_response.append(token)
                    yield token
                complete = "".join(full_response)

            self.conversation.append(
                ConversationTurn(role="assistant", content=complete, tier_used=tier)
            )
            self.memory.add(
                text=f"User: {user_input}\nJARVIS: {complete}",
                metadata={"type": "agent", "tier": tier, "timestamp": time.time()},
            )
            self._save_conversation()

    async def _execute_plan(
        self,
        user_input: str,
        history: list[dict],
        tier: str,
    ) -> str:
        """Execute complex request by decomposing into subtasks."""
        plan = await self.planner.create_plan(user_input, conversation_history=history)

        if not plan:
            logger.info("Planning failed; falling back to direct agent execution.")
            return await self.agent.execute(user_input, history, tier=tier)

        subtask_dicts = [s.to_dict() for s in plan.subtasks]
        self.coordinator.route_subtasks(subtask_dicts)

        agent_assignments = {}
        for sd, subtask in zip(subtask_dicts, plan.subtasks):
            agent_type = sd.get("agent_type", "generalist")
            agent_assignments[subtask.id] = agent_type

        parallel_groups = self.coordinator.get_parallel_groups(subtask_dicts)

        has_parallel = any(len(g) > 1 for g in parallel_groups)
        if has_parallel:
            logger.info(
                "Multi-agent plan: %d groups (%d parallel). Agents: %s",
                len(parallel_groups),
                sum(1 for g in parallel_groups if len(g) > 1),
                {sid: at for sid, at in agent_assignments.items()},
            )

        await self._broadcast_plan_event({
            "event": "plan_created",
            "plan_id": plan.plan_id,
            "goal": plan.goal_summary,
            "subtasks": [
                {
                    "id": s.id,
                    "title": s.title,
                    "status": s.status.value,
                    "agent_type": agent_assignments.get(s.id, "generalist"),
                }
                for s in plan.subtasks
            ],
            "parallel_groups": [[plan.subtasks[i].id for i in g] for g in parallel_groups],
        })

        logger.info(
            "Executing plan '%s' with %d subtasks across %d group(s).",
            plan.goal_summary, plan.total, len(parallel_groups),
        )

        for group_idx, group in enumerate(parallel_groups):
            if len(group) == 1:
                idx = group[0]
                subtask = plan.subtasks[idx]
                await self._execute_single_subtask(
                    plan, subtask, history, tier,
                    agent_assignments.get(subtask.id, "generalist"), 1,
                )
            else:
                logger.info(
                    "Executing parallel group %d/%d: %d subtasks",
                    group_idx + 1, len(parallel_groups), len(group),
                )

                for idx in group:
                    subtask = plan.subtasks[idx]
                    self.planner.tracker.start_subtask(subtask.id)
                    await self._broadcast_plan_event({
                        "event": "subtask_started",
                        "plan_id": plan.plan_id,
                        "subtask_id": subtask.id,
                        "title": subtask.title,
                        "agent_type": agent_assignments.get(subtask.id, "generalist"),
                        "parallel": True,
                        "progress": plan.progress_pct,
                    })

                async def _execute_fn(st_dict, agent_type):
                    st_id = st_dict.get("id", "")
                    st_obj = next(
                        (s for s in plan.subtasks if s.id == st_id), None
                    )
                    if not st_obj:
                        return "Subtask not found."

                    prior_context = plan.context_for_subtask(st_id)
                    profile = self.coordinator.get_profile(agent_type)

                    return await self.agent.execute_subtask(
                        subtask_description=(
                            f"[Agent: {profile.display_name}]\n"
                            f"{st_obj.description}"
                        ),
                        prior_context=prior_context,
                        conversation_history=history,
                        tier=tier,
                    )

                results = await self.coordinator.execute_parallel_group(
                    group, subtask_dicts, _execute_fn,
                )

                for idx, result, error in results:
                    subtask = plan.subtasks[idx]
                    if error:
                        self.planner.tracker.fail_subtask(subtask.id, error)
                        await self._broadcast_plan_event({
                            "event": "subtask_failed",
                            "plan_id": plan.plan_id,
                            "subtask_id": subtask.id,
                            "title": subtask.title,
                            "error": error,
                            "progress": plan.progress_pct,
                        })
                    else:
                        self.planner.tracker.complete_subtask(subtask.id, result)
                        await self._broadcast_plan_event({
                            "event": "subtask_completed",
                            "plan_id": plan.plan_id,
                            "subtask_id": subtask.id,
                            "title": subtask.title,
                            "progress": plan.progress_pct,
                        })

        self.planner.tracker.finalize_plan()

        # Store plan reference for experiment tracking
        self._last_plan = plan

        # Register in dispatch registry
        try:
            dispatch_id = self.dispatch.register(
                project_name=plan.goal_summary[:100],
                original_prompt=user_input[:500],
            )
            self.dispatch.update_status(
                dispatch_id,
                status="completed" if plan.failed_count == 0 else "partial",
                summary=f"{plan.completed_count}/{plan.total} subtasks completed",
            )
        except Exception as e:
            logger.debug("Dispatch registration failed (non-critical): %s", e)

        try:
            self.learning.record_plan_outcome(plan.to_dict())
        except Exception as e:
            logger.debug("Learning loop recording failed (non-critical): %s", e)

        detailed_results = self._build_plan_detail_message(plan)
        if detailed_results:
            self.conversation.append(
                ConversationTurn(
                    role="assistant",
                    content=detailed_results,
                    tier_used="plan_detail",
                )
            )

        response = await self._summarize_plan_results(plan, user_input)

        await self._broadcast_plan_event({
            "event": "plan_completed",
            "plan_id": plan.plan_id,
            "goal": plan.goal_summary,
            "completed": plan.completed_count,
            "total": plan.total,
            "failed": plan.failed_count,
        })

        return response

    async def _execute_single_subtask(
        self,
        plan,
        subtask,
        history: list[dict],
        tier: str,
        agent_type_str: str,
        max_retries: int = 1,
    ):
        """Execute single subtask with dependency checking, retries, and progress broadcast."""
        if subtask.depends_on:
            deps_ok = all(
                any(
                    s.id == dep_id and s.status == SubtaskStatus.COMPLETED
                    for s in plan.subtasks
                )
                for dep_id in subtask.depends_on
            )
            if not deps_ok:
                self.planner.tracker.skip_subtask(
                    subtask.id, "Dependency not met"
                )
                await self._broadcast_plan_event({
                    "event": "subtask_skipped",
                    "plan_id": plan.plan_id,
                    "subtask_id": subtask.id,
                    "title": subtask.title,
                    "reason": "Dependency not met",
                })
                return

        self.planner.tracker.start_subtask(subtask.id)
        await self._broadcast_plan_event({
            "event": "subtask_started",
            "plan_id": plan.plan_id,
            "subtask_id": subtask.id,
            "title": subtask.title,
            "agent_type": agent_type_str,
            "progress": plan.progress_pct,
        })

        try:
            agent_type = AgentType(agent_type_str)
        except ValueError:
            agent_type = AgentType.GENERALIST
        profile = self.coordinator.get_profile(agent_type)

        prior_context = plan.context_for_subtask(subtask.id)

        attempt = 0
        while attempt <= max_retries:
            try:
                result = await self.agent.execute_subtask(
                    subtask_description=(
                        f"[Agent: {profile.display_name}]\n"
                        f"{subtask.description}"
                    ),
                    prior_context=prior_context,
                    conversation_history=history,
                    tier=tier,
                )
                self.planner.tracker.complete_subtask(subtask.id, result)
                self.coordinator._record_agent_stats(agent_type, True, 0.0)
                await self._broadcast_plan_event({
                    "event": "subtask_completed",
                    "plan_id": plan.plan_id,
                    "subtask_id": subtask.id,
                    "title": subtask.title,
                    "progress": plan.progress_pct,
                })
                break
            except Exception as e:
                attempt += 1
                if attempt > max_retries:
                    error_msg = str(e)[:300]
                    self.planner.tracker.fail_subtask(subtask.id, error_msg)
                    self.coordinator._record_agent_stats(agent_type, False, 0.0)
                    await self._broadcast_plan_event({
                        "event": "subtask_failed",
                        "plan_id": plan.plan_id,
                        "subtask_id": subtask.id,
                        "title": subtask.title,
                        "error": error_msg,
                        "progress": plan.progress_pct,
                    })
                    logger.warning(
                        "Subtask '%s' (%s agent) failed after %d attempts: %s",
                        subtask.title, agent_type_str, attempt, error_msg,
                    )
                else:
                    logger.info(
                        "Subtask '%s' failed, retrying (attempt %d)...",
                        subtask.title, attempt + 1,
                    )

    def _build_plan_detail_message(self, plan) -> str:
        """Build detailed message from all subtask results for conversation history."""
        parts = []
        for s in plan.subtasks:
            if s.status == SubtaskStatus.COMPLETED and s.result:
                parts.append(f"[Plan step: {s.title}]\n{s.result[:2000]}")

        if not parts:
            return ""

        return (
            f"[Task plan completed: {plan.goal_summary}]\n\n"
            + "\n\n".join(parts)
        )

    async def _summarize_plan_results(self, plan, user_input: str) -> str:
        """Synthesize all subtask results into a natural, conversational response."""
        results_text = []
        for s in plan.subtasks:
            if s.status == SubtaskStatus.COMPLETED and s.result:
                results_text.append(f"Step '{s.title}': {s.result}")
            elif s.status == SubtaskStatus.FAILED:
                results_text.append(f"Step '{s.title}': FAILED - {s.error}")
            elif s.status == SubtaskStatus.SKIPPED:
                results_text.append(f"Step '{s.title}': SKIPPED - {s.error}")

        if not results_text:
            return "I attempted to complete your request but all steps failed. Could you try rephrasing or breaking it down differently?"

        summary_prompt = (
            f"The user asked: \"{user_input}\"\n\n"
            f"I completed the following steps:\n\n"
            + "\n\n".join(results_text) +
            f"\n\nPlease provide a cohesive, natural response to the user "
            f"that summarizes what was accomplished. Be conversational, not "
            f"a dry list. If any steps failed, mention what went wrong and "
            f"what was still accomplished."
        )

        try:
            return await self.llm.chat(
                summary_prompt,
                tier="fast",
                system_prompt_override=(
                    "You are JARVIS, a personal AI assistant. Summarize the results "
                    "of a multi-step task you just completed. Be concise, warm, and "
                    "conversational. Address the user as 'sir'."
                ),
            )
        except Exception as e:
            logger.warning("Plan summary generation failed: %s", e)
            # Fallback: just concatenate the results
            return "\n\n".join(results_text)

    async def _broadcast_plan_event(self, event: dict):
        """Broadcast plan progress event to connected UI clients via WebSocket."""
        if self._on_plan_progress:
            try:
                await self._on_plan_progress(event)
            except Exception as e:
                logger.debug("Plan progress broadcast failed: %s", e)

    def _save_conversation(self):
        """Persist conversation history to disk."""
        try:
            turns = [
                {
                    "role": turn.role,
                    "content": turn.content,
                    "timestamp": turn.timestamp,
                    "tier_used": turn.tier_used,
                }
                for turn in self.conversation[-MAX_CONVERSATION_TURNS:]
            ]
            self._conversation_file.write_text(
                json.dumps(turns, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("Conversation save failed (non-critical): %s", e)

    def _load_conversation(self):
        """Restore conversation from previous session."""
        if not self._conversation_file.exists():
            return

        try:
            data = json.loads(self._conversation_file.read_text(encoding="utf-8"))
            for entry in data:
                self.conversation.append(
                    ConversationTurn(
                        role=entry["role"],
                        content=entry["content"],
                        timestamp=entry.get("timestamp", 0.0),
                        tier_used=entry.get("tier_used", ""),
                    )
                )
            logger.info("Restored %d conversation turns from disk.", len(self.conversation))
        except Exception as e:
            logger.warning("Could not load conversation history: %s. Starting fresh.", e)
            self.conversation.clear()

    def get_conversation_summary(self) -> str:
        """Get a brief summary of the current conversation."""
        if not self.conversation:
            return "No conversation yet."
        count = len(self.conversation)
        last = self.conversation[-1]
        return f"{count} messages. Last: [{last.role}] {last.content[:80]}..."

    def clear_conversation(self):
        """Clear the current conversation (memory persists)."""
        self.conversation.clear()
        try:
            if self._conversation_file.exists():
                self._conversation_file.unlink()
        except Exception:
            pass
        logger.info("Conversation cleared.")

    async def shutdown(self):
        """Persist all state and close resources."""
        self.proactive.stop()
        try:
            self.learning.save_all()
        except Exception as e:
            logger.debug("Learning data save on shutdown failed: %s", e)
        try:
            self.memory.save_all()
        except Exception as e:
            logger.debug("Memory save on shutdown failed: %s", e)
        await self.llm.close()
        logger.info("JARVIS brain shut down.")
