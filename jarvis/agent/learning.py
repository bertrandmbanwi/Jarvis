"""
JARVIS Learning Loop

Analyzes completed task plans to extract patterns, track tool reliability,
and inject learned insights into future planning prompts. This creates a
feedback loop where JARVIS gets better over time by learning from both
successes and failures.

What it tracks:
- Tool success/failure rates (which tools are reliable, which need retries)
- Plan pattern effectiveness (which decomposition strategies work well)
- Common failure modes (timeout, auth, permission, missing data)
- Average subtask durations (for better time estimates)
- User request patterns (frequently requested task types)

How insights are used:
- Injected into the planner's system prompt so future plans avoid known pitfalls
- Tool reliability scores help Claude choose more reliable tools
- Failure pattern context helps the planner add defensive steps (e.g., "check
  permissions before writing file")

Data sources:
- Completed plan JSON files in data/plans/ (persisted by TaskTracker)
- Single-shot agent executions are also logged for tool reliability data
"""
import json
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.agent.learning")

LEARNING_DIR = settings.DATA_DIR / "learning"
LEARNING_DIR.mkdir(parents=True, exist_ok=True)

TOOL_STATS_FILE = LEARNING_DIR / "tool_stats.json"
PLAN_PATTERNS_FILE = LEARNING_DIR / "plan_patterns.json"
FAILURE_LOG_FILE = LEARNING_DIR / "failure_log.json"

PLANS_DIR = settings.DATA_DIR / "plans"

MAX_FAILURE_LOG_ENTRIES = 200

MAX_PLAN_PATTERNS = 100

MIN_EXECUTIONS_FOR_RELIABILITY = 3


@dataclass
class ToolStats:
    """Aggregated statistics for a single tool."""
    name: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_s: float = 0.0
    last_used: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successes / self.total_calls

    @property
    def avg_duration_s(self) -> float:
        if self.successes == 0:
            return 0.0
        return self.total_duration_s / self.successes

    @property
    def is_reliable(self) -> bool:
        """A tool is reliable if it has enough data and > 80% success rate."""
        if self.total_calls < MIN_EXECUTIONS_FOR_RELIABILITY:
            return True  # Insufficient data; assume reliable
        return self.success_rate >= 0.8

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total_calls": self.total_calls,
            "successes": self.successes,
            "failures": self.failures,
            "total_duration_s": round(self.total_duration_s, 2),
            "success_rate": round(self.success_rate, 3),
            "avg_duration_s": round(self.avg_duration_s, 2),
            "last_used": self.last_used,
            "is_reliable": self.is_reliable,
            "failure_reasons": self.failure_reasons[-10:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolStats":
        return cls(
            name=data["name"],
            total_calls=data.get("total_calls", 0),
            successes=data.get("successes", 0),
            failures=data.get("failures", 0),
            total_duration_s=data.get("total_duration_s", 0.0),
            last_used=data.get("last_used", 0.0),
            failure_reasons=data.get("failure_reasons", []),
        )


@dataclass
class PlanPattern:
    """A recorded plan pattern with its outcome."""
    request_summary: str
    goal_summary: str
    subtask_count: int
    subtask_titles: list[str]
    completed_count: int
    failed_count: int
    total_duration_s: float
    outcome: str  # "success", "partial", "failed"
    timestamp: float = field(default_factory=time.time)
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request_summary": self.request_summary,
            "goal_summary": self.goal_summary,
            "subtask_count": self.subtask_count,
            "subtask_titles": self.subtask_titles,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "total_duration_s": round(self.total_duration_s, 2),
            "outcome": self.outcome,
            "timestamp": self.timestamp,
            "failure_reasons": self.failure_reasons,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanPattern":
        return cls(
            request_summary=data["request_summary"],
            goal_summary=data.get("goal_summary", ""),
            subtask_count=data.get("subtask_count", 0),
            subtask_titles=data.get("subtask_titles", []),
            completed_count=data.get("completed_count", 0),
            failed_count=data.get("failed_count", 0),
            total_duration_s=data.get("total_duration_s", 0.0),
            outcome=data.get("outcome", "unknown"),
            timestamp=data.get("timestamp", 0.0),
            failure_reasons=data.get("failure_reasons", []),
        )


class LearningLoop:
    """Learns from completed plans and tool executions to improve performance."""

    def __init__(self):
        self._tool_stats: dict[str, ToolStats] = {}
        self._plan_patterns: list[PlanPattern] = []
        self._failure_log: list[dict] = []
        self._loaded = False

    def initialize(self):
        """Load persisted learning data from disk."""
        if self._loaded:
            return
        self._load_tool_stats()
        self._load_plan_patterns()
        self._load_failure_log()
        self._loaded = True
        logger.info(
            "Learning loop initialized: %d tool profiles, %d plan patterns, %d failure records.",
            len(self._tool_stats),
            len(self._plan_patterns),
            len(self._failure_log),
        )

    def record_plan_outcome(self, plan_dict: dict):
        """Record outcome of a completed task plan."""
        if not plan_dict:
            return

        subtasks = plan_dict.get("subtasks", [])
        if not subtasks:
            return

        completed = 0
        failed = 0
        total_duration = 0.0
        failure_reasons = []
        subtask_titles = []
        for st in subtasks:
            subtask_titles.append(st.get("title", "unknown"))
            status = st.get("status", "pending")
            duration = st.get("duration_s", 0.0)
            total_duration += duration

            if status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
                error = st.get("error", "")
                if error:
                    failure_reasons.append(error[:200])
                    self._record_failure(
                        source="plan_subtask",
                        title=st.get("title", ""),
                        error=error,
                        plan_id=plan_dict.get("plan_id", ""),
                    )

        if failed == 0 and completed == len(subtasks):
            outcome = "success"
        elif completed > 0:
            outcome = "partial"
        else:
            outcome = "failed"

        pattern = PlanPattern(
            request_summary=plan_dict.get("original_request", "")[:200],
            goal_summary=plan_dict.get("goal_summary", ""),
            subtask_count=len(subtasks),
            subtask_titles=subtask_titles,
            completed_count=completed,
            failed_count=failed,
            total_duration_s=total_duration,
            outcome=outcome,
            timestamp=plan_dict.get("completed_at", time.time()),
            failure_reasons=failure_reasons,
        )
        self._plan_patterns.append(pattern)

        if len(self._plan_patterns) > MAX_PLAN_PATTERNS:
            self._plan_patterns = self._plan_patterns[-MAX_PLAN_PATTERNS:]

        logger.info(
            "Recorded plan outcome: '%s' -> %s (%d/%d completed, %.1fs total).",
            pattern.goal_summary[:60],
            outcome,
            completed,
            len(subtasks),
            total_duration,
        )

        self._save_plan_patterns()
        self._save_failure_log()

    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_s: float = 0.0,
        error: str = "",
    ):
        """Record a single tool execution outcome."""
        if tool_name not in self._tool_stats:
            self._tool_stats[tool_name] = ToolStats(name=tool_name)

        stats = self._tool_stats[tool_name]
        stats.total_calls += 1
        stats.last_used = time.time()

        if success:
            stats.successes += 1
            stats.total_duration_s += duration_s
        else:
            stats.failures += 1
            if error:
                stats.failure_reasons.append(error[:200])
                if len(stats.failure_reasons) > 20:
                    stats.failure_reasons = stats.failure_reasons[-20:]

        total_calls = sum(s.total_calls for s in self._tool_stats.values())
        if total_calls % 10 == 0:
            self._save_tool_stats()

    def record_agent_execution(
        self,
        user_input: str,
        tool_calls: list[dict],
        success: bool,
        duration_s: float = 0.0,
    ):
        """Record a single-shot agent execution for tool reliability tracking."""
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if tool_name:
                is_last = tc == tool_calls[-1]
                tool_success = success or not is_last
                self.record_tool_call(
                    tool_name=tool_name,
                    success=tool_success,
                    duration_s=duration_s / max(len(tool_calls), 1),
                )

    def get_tool_reliability_report(self) -> dict:
        """
        Get a summary of tool reliability scores.

        Returns:
            Dict with tool names as keys, containing success rate,
            call count, avg duration, and reliability flag.
        """
        report = {}
        for name, stats in self._tool_stats.items():
            report[name] = stats.to_dict()
        return report

    def get_unreliable_tools(self) -> list[str]:
        """Get tools with low success rates (< 80% with sufficient data)."""
        return [
            name for name, stats in self._tool_stats.items()
            if not stats.is_reliable
        ]

    def get_common_failure_patterns(self, limit: int = 5) -> list[dict]:
        """Identify most common failure patterns from recent failures."""
        if not self._failure_log:
            return []

        recent = self._failure_log[-50:]
        error_keywords = Counter()
        for entry in recent:
            error = entry.get("error", "").lower()
            for keyword in self._extract_error_keywords(error):
                error_keywords[keyword] += 1

        patterns = []
        for keyword, count in error_keywords.most_common(limit):
            example = ""
            for entry in reversed(recent):
                if keyword in entry.get("error", "").lower():
                    example = entry.get("error", "")[:200]
                    break
            patterns.append({
                "pattern": keyword,
                "count": count,
                "recent_example": example,
            })
        return patterns

    def get_plan_success_rate(self) -> dict:
        """Get overall plan success statistics."""
        if not self._plan_patterns:
            return {
                "total_plans": 0,
                "success_rate": 0.0,
                "avg_subtasks": 0,
                "avg_duration_s": 0.0,
            }

        total = len(self._plan_patterns)
        successes = sum(1 for p in self._plan_patterns if p.outcome == "success")
        partials = sum(1 for p in self._plan_patterns if p.outcome == "partial")
        avg_subtasks = sum(p.subtask_count for p in self._plan_patterns) / total
        avg_duration = sum(p.total_duration_s for p in self._plan_patterns) / total

        return {
            "total_plans": total,
            "successes": successes,
            "partials": partials,
            "failures": total - successes - partials,
            "success_rate": round(successes / total, 3) if total > 0 else 0.0,
            "avg_subtasks": round(avg_subtasks, 1),
            "avg_duration_s": round(avg_duration, 1),
        }

    def get_insights_summary(self) -> dict:
        """Get comprehensive summary of all learning insights."""
        return {
            "plan_stats": self.get_plan_success_rate(),
            "unreliable_tools": self.get_unreliable_tools(),
            "common_failures": self.get_common_failure_patterns(),
            "tool_count": len(self._tool_stats),
            "total_tool_calls": sum(
                s.total_calls for s in self._tool_stats.values()
            ),
            "plan_patterns_recorded": len(self._plan_patterns),
            "failure_log_size": len(self._failure_log),
        }

    def get_planner_context(self) -> str:
        """Generate context to inject into planner's system prompt."""
        sections = []

        unreliable = self.get_unreliable_tools()
        if unreliable:
            tool_warnings = []
            for name in unreliable:
                stats = self._tool_stats[name]
                rate_pct = int(stats.success_rate * 100)
                recent_reason = stats.failure_reasons[-1] if stats.failure_reasons else "unknown"
                tool_warnings.append(
                    f"  - {name}: {rate_pct}% success rate ({stats.total_calls} calls). "
                    f"Recent failure: {recent_reason[:100]}"
                )
            sections.append(
                "UNRELIABLE TOOLS (consider alternatives or add error handling):\n"
                + "\n".join(tool_warnings)
            )

        failure_patterns = self.get_common_failure_patterns(limit=3)
        if failure_patterns:
            pattern_lines = []
            for fp in failure_patterns:
                pattern_lines.append(
                    f"  - \"{fp['pattern']}\" (occurred {fp['count']}x). "
                    f"Example: {fp['recent_example'][:80]}"
                )
            sections.append(
                "COMMON FAILURE PATTERNS (add defensive steps to handle these):\n"
                + "\n".join(pattern_lines)
            )

        plan_stats = self.get_plan_success_rate()
        if plan_stats["total_plans"] >= 3:
            sections.append(
                f"PLAN HISTORY: {plan_stats['total_plans']} plans executed, "
                f"{int(plan_stats['success_rate'] * 100)}% fully successful. "
                f"Average {plan_stats['avg_subtasks']} subtasks, "
                f"{plan_stats['avg_duration_s']:.0f}s duration."
            )

        successful_patterns = [
            p for p in self._plan_patterns[-10:]
            if p.outcome == "success"
        ]
        if successful_patterns:
            examples = []
            for p in successful_patterns[-3:]:
                steps = ", ".join(p.subtask_titles[:4])
                if len(p.subtask_titles) > 4:
                    steps += f" (+{len(p.subtask_titles) - 4} more)"
                examples.append(f"  - \"{p.goal_summary[:60]}\": [{steps}]")
            sections.append(
                "SUCCESSFUL PLAN EXAMPLES (proven decomposition patterns):\n"
                + "\n".join(examples)
            )

        if not sections:
            return ""

        return (
            "\n--- LEARNING CONTEXT (from past executions) ---\n"
            + "\n\n".join(sections)
            + "\n--- END LEARNING CONTEXT ---"
        )

    def backfill_from_plan_files(self):
        """Scan plan files and extract learning data for bootstrap."""
        if not PLANS_DIR.exists():
            return

        plan_files = sorted(
            PLANS_DIR.glob("plan_*.json"),
            key=lambda p: p.stat().st_mtime,
        )

        if not plan_files:
            return

        backfilled = 0
        for pf in plan_files:
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                plan_id = data.get("plan_id", "")
                already_recorded = any(
                    p.goal_summary == data.get("goal_summary", "")
                    and abs(p.timestamp - data.get("completed_at", 0)) < 1.0
                    for p in self._plan_patterns
                )
                if not already_recorded:
                    self.record_plan_outcome(data)
                    backfilled += 1
            except Exception as e:
                logger.debug("Could not backfill from %s: %s", pf.name, e)

        if backfilled:
            logger.info("Backfilled learning data from %d existing plan(s).", backfilled)

    def _record_failure(
        self,
        source: str,
        title: str,
        error: str,
        plan_id: str = "",
    ):
        """Add an entry to the failure log."""
        self._failure_log.append({
            "source": source,
            "title": title,
            "error": error[:300],
            "plan_id": plan_id,
            "timestamp": time.time(),
        })
        # Cap the failure log
        if len(self._failure_log) > MAX_FAILURE_LOG_ENTRIES:
            self._failure_log = self._failure_log[-MAX_FAILURE_LOG_ENTRIES:]

    def _extract_error_keywords(self, error_text: str) -> list[str]:
        """Extract keyword phrases from error message for categorization."""
        keywords = []
        error_lower = error_text.lower()

        category_patterns = {
            "timeout": ["timeout", "timed out", "deadline exceeded"],
            "permission denied": ["permission denied", "access denied", "forbidden", "403"],
            "not found": ["not found", "404", "no such file", "does not exist"],
            "authentication": ["auth", "unauthorized", "401", "login required"],
            "rate limit": ["rate limit", "429", "too many requests"],
            "connection error": ["connection refused", "connection reset", "econnrefused"],
            "out of memory": ["out of memory", "oom", "memory error"],
            "invalid input": ["invalid", "malformed", "bad request", "400"],
        }

        for category, patterns in category_patterns.items():
            if any(p in error_lower for p in patterns):
                keywords.append(category)

        if not keywords and error_text:
            truncated = error_text[:40].strip()
            if truncated:
                keywords.append(truncated.lower())

        return keywords

    def _save_tool_stats(self):
        """Persist tool statistics to disk."""
        try:
            data = {name: stats.to_dict() for name, stats in self._tool_stats.items()}
            TOOL_STATS_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("Failed to save tool stats: %s", e)

    def _load_tool_stats(self):
        """Load tool statistics from disk."""
        if not TOOL_STATS_FILE.exists():
            return
        try:
            data = json.loads(TOOL_STATS_FILE.read_text(encoding="utf-8"))
            for name, stats_dict in data.items():
                self._tool_stats[name] = ToolStats.from_dict(stats_dict)
        except Exception as e:
            logger.warning("Could not load tool stats: %s", e)

    def _save_plan_patterns(self):
        """Persist plan patterns to disk."""
        try:
            data = [p.to_dict() for p in self._plan_patterns]
            PLAN_PATTERNS_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("Failed to save plan patterns: %s", e)

    def _load_plan_patterns(self):
        """Load plan patterns from disk."""
        if not PLAN_PATTERNS_FILE.exists():
            return
        try:
            data = json.loads(PLAN_PATTERNS_FILE.read_text(encoding="utf-8"))
            self._plan_patterns = [PlanPattern.from_dict(p) for p in data]
        except Exception as e:
            logger.warning("Could not load plan patterns: %s", e)

    def _save_failure_log(self):
        """Persist failure log to disk."""
        try:
            FAILURE_LOG_FILE.write_text(
                json.dumps(self._failure_log, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("Failed to save failure log: %s", e)

    def _load_failure_log(self):
        """Load failure log from disk."""
        if not FAILURE_LOG_FILE.exists():
            return
        try:
            self._failure_log = json.loads(
                FAILURE_LOG_FILE.read_text(encoding="utf-8")
            )
        except Exception as e:
            logger.warning("Could not load failure log: %s", e)

    def save_all(self):
        """Force-save all learning data to disk."""
        self._save_tool_stats()
        self._save_plan_patterns()
        self._save_failure_log()
        logger.info("All learning data saved to disk.")
