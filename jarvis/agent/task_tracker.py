"""
JARVIS Task Tracker

Manages the lifecycle of decomposed task plans. Each plan consists of
ordered subtasks that are executed sequentially, with state tracked for
progress reporting, retry logic, and persistence.

A TaskPlan is the result of the planner decomposing a complex user request.
Each Subtask within the plan progresses through:
    pending -> in_progress -> completed | failed | skipped
"""
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from jarvis.config import settings

logger = logging.getLogger("jarvis.agent.task_tracker")

PLANS_DIR = settings.DATA_DIR / "plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Subtask:
    """A single subtask within a decomposed plan."""
    id: str
    title: str
    description: str
    status: SubtaskStatus = SubtaskStatus.PENDING
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_s: float = 0.0
    retry_count: int = 0
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "result": self.result[:500] if self.result else "",
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_s": self.duration_s,
            "retry_count": self.retry_count,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Subtask":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            status=SubtaskStatus(data.get("status", "pending")),
            result=data.get("result", ""),
            error=data.get("error", ""),
            started_at=data.get("started_at", 0.0),
            completed_at=data.get("completed_at", 0.0),
            duration_s=data.get("duration_s", 0.0),
            retry_count=data.get("retry_count", 0),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class TaskPlan:
    """A decomposed plan for a complex user request."""
    plan_id: str
    original_request: str
    goal_summary: str
    subtasks: list[Subtask]
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    status: str = "active"  # active, completed, failed, cancelled

    @property
    def total(self) -> int:
        return len(self.subtasks)

    @property
    def completed_count(self) -> int:
        return sum(
            1 for s in self.subtasks
            if s.status in (SubtaskStatus.COMPLETED, SubtaskStatus.SKIPPED)
        )

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.subtasks if s.status == SubtaskStatus.FAILED)

    @property
    def current_subtask(self) -> Optional[Subtask]:
        """Get the currently in-progress subtask, or the next pending one."""
        for s in self.subtasks:
            if s.status == SubtaskStatus.IN_PROGRESS:
                return s
        for s in self.subtasks:
            if s.status == SubtaskStatus.PENDING:
                return s
        return None

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (SubtaskStatus.COMPLETED, SubtaskStatus.SKIPPED, SubtaskStatus.FAILED)
            for s in self.subtasks
        )

    @property
    def progress_pct(self) -> int:
        if not self.subtasks:
            return 100
        return int((self.completed_count / self.total) * 100)

    def progress_summary(self) -> str:
        """Human-readable progress string."""
        lines = [f"Plan: {self.goal_summary} ({self.completed_count}/{self.total} done)"]
        for i, s in enumerate(self.subtasks, 1):
            icon = {
                SubtaskStatus.PENDING: "[ ]",
                SubtaskStatus.IN_PROGRESS: "[>]",
                SubtaskStatus.COMPLETED: "[x]",
                SubtaskStatus.FAILED: "[!]",
                SubtaskStatus.SKIPPED: "[-]",
            }.get(s.status, "[ ]")
            lines.append(f"  {icon} {i}. {s.title}")
        return "\n".join(lines)

    def context_for_subtask(self, subtask_id: str) -> str:
        """Build accumulated context from completed prior subtasks."""
        context_parts = []
        for s in self.subtasks:
            if s.id == subtask_id:
                break
            if s.status == SubtaskStatus.COMPLETED and s.result:
                context_parts.append(
                    f"[Completed step '{s.title}']: {s.result[:1000]}"
                )
            elif s.status == SubtaskStatus.FAILED and s.error:
                context_parts.append(
                    f"[Failed step '{s.title}']: {s.error[:300]}"
                )
        return "\n\n".join(context_parts) if context_parts else ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "original_request": self.original_request,
            "goal_summary": self.goal_summary,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskPlan":
        return cls(
            plan_id=data["plan_id"],
            original_request=data["original_request"],
            goal_summary=data["goal_summary"],
            subtasks=[Subtask.from_dict(s) for s in data.get("subtasks", [])],
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at", 0.0),
            status=data.get("status", "active"),
        )


class TaskTracker:
    """Manages active and historical task plans."""

    def __init__(self):
        self._active_plan: Optional[TaskPlan] = None
        self._plan_history: list[dict] = []

    @property
    def active_plan(self) -> Optional[TaskPlan]:
        return self._active_plan

    def create_plan(
        self,
        original_request: str,
        goal_summary: str,
        subtasks: list[dict],
    ) -> TaskPlan:
        """Create a new task plan from planner output."""
        plan_id = f"plan_{uuid4().hex[:8]}"
        plan = TaskPlan(
            plan_id=plan_id,
            original_request=original_request,
            goal_summary=goal_summary,
            subtasks=[
                Subtask(
                    id=f"step_{i+1}",
                    title=st.get("title", f"Step {i+1}"),
                    description=st.get("description", ""),
                    depends_on=st.get("depends_on", []),
                )
                for i, st in enumerate(subtasks)
            ],
        )
        self._active_plan = plan
        logger.info(
            "Created plan %s: '%s' with %d subtasks.",
            plan_id, goal_summary, len(plan.subtasks),
        )
        return plan

    def start_subtask(self, subtask_id: str):
        """Mark a subtask as in-progress."""
        if not self._active_plan:
            return
        for s in self._active_plan.subtasks:
            if s.id == subtask_id:
                s.status = SubtaskStatus.IN_PROGRESS
                s.started_at = time.time()
                logger.info("Subtask started: %s (%s)", s.title, subtask_id)
                return

    def complete_subtask(self, subtask_id: str, result: str):
        """Mark a subtask as completed with its result."""
        if not self._active_plan:
            return
        for s in self._active_plan.subtasks:
            if s.id == subtask_id:
                s.status = SubtaskStatus.COMPLETED
                s.result = result
                s.completed_at = time.time()
                s.duration_s = round(s.completed_at - s.started_at, 2) if s.started_at else 0.0
                logger.info(
                    "Subtask completed: %s (%.1fs)", s.title, s.duration_s,
                )
                return

    def fail_subtask(self, subtask_id: str, error: str):
        """Mark a subtask as failed."""
        if not self._active_plan:
            return
        for s in self._active_plan.subtasks:
            if s.id == subtask_id:
                s.status = SubtaskStatus.FAILED
                s.error = error
                s.completed_at = time.time()
                s.duration_s = round(s.completed_at - s.started_at, 2) if s.started_at else 0.0
                s.retry_count += 1
                logger.warning("Subtask failed: %s - %s", s.title, error[:200])
                return

    def skip_subtask(self, subtask_id: str, reason: str = ""):
        """Skip a subtask (e.g., dependency failed or user requested skip)."""
        if not self._active_plan:
            return
        for s in self._active_plan.subtasks:
            if s.id == subtask_id:
                s.status = SubtaskStatus.SKIPPED
                s.error = reason or "Skipped"
                s.completed_at = time.time()
                logger.info("Subtask skipped: %s (%s)", s.title, reason)
                return

    def finalize_plan(self):
        """Mark the active plan as complete and persist to history."""
        if not self._active_plan:
            return

        plan = self._active_plan
        plan.completed_at = time.time()

        if plan.failed_count > 0 and plan.completed_count == 0:
            plan.status = "failed"
        elif plan.is_complete:
            plan.status = "completed"
        else:
            plan.status = "completed"

        self._persist_plan(plan)
        self._plan_history.append(plan.to_dict())

        logger.info(
            "Plan %s finalized: %s (%d/%d completed, %d failed).",
            plan.plan_id, plan.status,
            plan.completed_count, plan.total, plan.failed_count,
        )

        self._active_plan = None

    def cancel_plan(self):
        """Cancel the active plan."""
        if not self._active_plan:
            return
        self._active_plan.status = "cancelled"
        self._active_plan.completed_at = time.time()
        self._persist_plan(self._active_plan)
        logger.info("Plan %s cancelled.", self._active_plan.plan_id)
        self._active_plan = None

    def get_plan_status(self) -> str:
        """Get a human-readable status of the active plan."""
        if not self._active_plan:
            return "No active plan."
        return self._active_plan.progress_summary()

    def _persist_plan(self, plan: TaskPlan):
        """Save plan to disk as JSON."""
        try:
            plan_file = PLANS_DIR / f"{plan.plan_id}.json"
            plan_file.write_text(
                json.dumps(plan.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to persist plan %s: %s", plan.plan_id, e)

    def load_recent_plans(self, limit: int = 10) -> list[dict]:
        """Load recent plan history from disk."""
        try:
            plan_files = sorted(
                PLANS_DIR.glob("plan_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
            plans = []
            for pf in plan_files:
                data = json.loads(pf.read_text(encoding="utf-8"))
                plans.append(data)
            return plans
        except Exception as e:
            logger.warning("Failed to load plan history: %s", e)
            return []
