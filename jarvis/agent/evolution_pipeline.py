"""
Evolution Pipeline

Connects A/B testing, template evolution, and learning loop into a cohesive
system for continuous prompt template improvement. Orchestrates the full
feedback loop from task execution through analysis and template updates.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from jarvis.config import settings
from jarvis.agent.ab_testing import ABTester
from jarvis.agent.template_evolution import TemplateEvolver
from jarvis.agent.templates import get_template, fill_template

logger = logging.getLogger("jarvis.agent.evolution_pipeline")

PIPELINE_STATE_FILE = settings.DATA_DIR / "learning" / "evolution_pipeline_state.json"
PIPELINE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class ExperimentStatus:
    """Status of an active A/B testing experiment."""
    task_type: str
    template_version: str
    started_at: float
    total_tasks: int = 0
    successes: int = 0
    failures: int = 0
    success_rate: float = 0.0
    active: bool = True


@dataclass
class EvolutionCycle:
    """Record of a template evolution cycle."""
    task_type: str
    timestamp: float
    old_version: str
    new_version: str
    improvements_count: int
    triggered_by: str


class EvolutionPipeline:
    """Orchestrates template evolution through A/B testing and learning feedback."""

    def __init__(self, learning_loop=None):
        """
        Initialize the evolution pipeline.

        Args:
            learning_loop: Optional LearningLoop instance for failure analysis
        """
        self.ab_tester = ABTester()
        self.evolver = TemplateEvolver(learning_loop=learning_loop)
        self.learning_loop = learning_loop

        self._active_experiments: Dict[str, ExperimentStatus] = {}
        self._evolution_history: List[EvolutionCycle] = []
        self._template_versions: Dict[str, str] = {}
        self._success_tracker: Dict[str, dict] = {}

        self._load_pipeline_state()

    def run_evolution_cycle(self, task_type: str) -> Optional[str]:
        """
        Check if evolution is warranted and create new template version.

        Orchestrates the full evolution flow: failure analysis, improvement
        suggestion, template creation, and A/B test registration.

        Args:
            task_type: Type of task to evolve

        Returns:
            New version string if created, else None
        """
        logger.info("Starting evolution cycle for task_type: %s", task_type)

        new_version = self.evolver.evolve_if_needed(task_type, min_failures=5)

        if not new_version:
            logger.info("Evolution not needed for %s", task_type)
            return None

        old_version = self._template_versions.get(task_type, "v0")
        self._template_versions[task_type] = new_version

        improvement_count = len(self.evolver.suggest_improvements(task_type))

        cycle = EvolutionCycle(
            task_type=task_type,
            timestamp=time.time(),
            old_version=old_version,
            new_version=new_version,
            improvements_count=improvement_count,
            triggered_by="failure_analysis",
        )
        self._evolution_history.append(cycle)

        logger.info(
            "Evolution cycle complete: %s -> %s (%d improvements)",
            old_version,
            new_version,
            improvement_count,
        )

        self._save_pipeline_state()

        return new_version

    def on_task_complete(
        self,
        task_type: str,
        success: bool,
        duration: float = 0.0,
    ) -> None:
        """
        Record task completion and trigger evolution check if needed.

        Updates both A/B testing and success tracking databases.

        Args:
            task_type: Type of task that completed
            success: Whether the task succeeded
            duration: Execution duration in seconds
        """
        if task_type not in self._success_tracker:
            self._success_tracker[task_type] = {
                "total": 0,
                "successes": 0,
                "failures": 0,
                "total_duration": 0.0,
            }

        tracker = self._success_tracker[task_type]
        tracker["total"] += 1

        if success:
            tracker["successes"] += 1
        else:
            tracker["failures"] += 1

        tracker["total_duration"] += duration

        if tracker["total"] > 0:
            tracker["success_rate"] = tracker["successes"] / tracker["total"]

        logger.debug(
            "Task complete: %s (success=%s, duration=%.1fs)",
            task_type,
            success,
            duration,
        )

        if tracker["total"] % 5 == 0:
            logger.debug(
                "Success rate for %s: %.1f%% (%d/%d tasks)",
                task_type,
                tracker["success_rate"] * 100,
                tracker["successes"],
                tracker["total"],
            )

        if not success and tracker["failures"] >= 5 and tracker["failures"] % 5 == 0:
            logger.info(
                "Failure threshold reached for %s, triggering evolution check",
                task_type,
            )
            self.run_evolution_cycle(task_type)

        self._save_pipeline_state()

    def get_active_template(
        self,
        task_type: str,
        request_text: str = "",
    ) -> Optional[str]:
        """
        Get the currently active template for a task type.

        Returns template from A/B test if experiment is active,
        otherwise returns standard template.

        Args:
            task_type: Type of task
            request_text: Optional request text for scoring

        Returns:
            Filled template string, or None if no template found
        """
        try:
            template = get_template(task_type, request_text)
            if not template:
                logger.warning("No template found for task_type: %s", task_type)
                return None

            return template.template_format

        except Exception as e:
            logger.error("Failed to get active template: %s", e)
            return None

    def get_pipeline_status(self) -> Dict:
        """
        Get comprehensive status of pipeline, experiments, and evolution.

        Returns:
            Dict with active experiments, evolution history, and versions
        """
        status = {
            "timestamp": time.time(),
            "active_experiments": {},
            "success_rates": {},
            "evolution_history": [],
            "template_versions": self._template_versions.copy(),
            "pipeline_health": self._compute_pipeline_health(),
        }

        for task_type, tracker in self._success_tracker.items():
            status["success_rates"][task_type] = {
                "total": tracker["total"],
                "successes": tracker["successes"],
                "failures": tracker["failures"],
                "success_rate": round(tracker["success_rate"], 3),
                "avg_duration_s": round(
                    tracker["total_duration"] / max(tracker["total"], 1),
                    2,
                ),
            }

        try:
            from jarvis.agent.ab_testing import PromptTemplate as ABTemplate
            for task_type in set(t for t in self._template_versions.keys()):
                versions = self.ab_tester._discover_versions(task_type)
                if versions:
                    stats = self.ab_tester.get_version_stats(task_type)
                    status["active_experiments"][task_type] = {
                        "versions": [v.version for v in versions],
                        "stats": {
                            k: {
                                "success_rate": v.success_rate,
                                "total_tasks": v.total_tasks,
                                "passed": v.passed,
                                "failed": v.failed,
                                "confidence_interval": v.confidence_interval,
                            }
                            for k, v in stats.items()
                        },
                    }
        except Exception as e:
            logger.debug("Could not get A/B test stats: %s", e)

        for cycle in self._evolution_history[-10:]:
            status["evolution_history"].append({
                "timestamp": cycle.timestamp,
                "task_type": cycle.task_type,
                "old_version": cycle.old_version,
                "new_version": cycle.new_version,
                "improvements": cycle.improvements_count,
                "triggered_by": cycle.triggered_by,
            })

        return status

    def _compute_pipeline_health(self) -> Dict:
        """
        Compute overall health metrics for the pipeline.

        Returns:
            Dict with health indicators
        """
        if not self._success_tracker:
            return {
                "overall_success_rate": 0.0,
                "total_tasks_tracked": 0,
                "active_task_types": 0,
                "health_status": "no_data",
            }

        total_tasks = sum(t["total"] for t in self._success_tracker.values())
        total_successes = sum(t["successes"] for t in self._success_tracker.values())
        overall_rate = total_successes / total_tasks if total_tasks > 0 else 0.0

        if overall_rate >= 0.8:
            status = "healthy"
        elif overall_rate >= 0.6:
            status = "degraded"
        else:
            status = "critical"

        return {
            "overall_success_rate": round(overall_rate, 3),
            "total_tasks_tracked": total_tasks,
            "active_task_types": len(self._success_tracker),
            "evolution_cycles": len(self._evolution_history),
            "health_status": status,
        }

    def _load_pipeline_state(self) -> None:
        """Load persisted pipeline state from disk."""
        if not PIPELINE_STATE_FILE.exists():
            return

        try:
            with open(PIPELINE_STATE_FILE, 'r') as f:
                state = json.load(f)

            self._template_versions = state.get("template_versions", {})
            self._success_tracker = state.get("success_tracker", {})

            evolution_data = state.get("evolution_history", [])
            self._evolution_history = [
                EvolutionCycle(
                    task_type=e["task_type"],
                    timestamp=e["timestamp"],
                    old_version=e["old_version"],
                    new_version=e["new_version"],
                    improvements_count=e.get("improvements_count", 0),
                    triggered_by=e.get("triggered_by", "unknown"),
                )
                for e in evolution_data
            ]

            logger.info("Loaded pipeline state with %d evolution cycles",
                       len(self._evolution_history))

        except Exception as e:
            logger.warning("Could not load pipeline state: %s", e)

    def _save_pipeline_state(self) -> None:
        """Save pipeline state to disk."""
        try:
            state = {
                "timestamp": time.time(),
                "template_versions": self._template_versions.copy(),
                "success_tracker": self._success_tracker.copy(),
                "evolution_history": [
                    {
                        "task_type": c.task_type,
                        "timestamp": c.timestamp,
                        "old_version": c.old_version,
                        "new_version": c.new_version,
                        "improvements_count": c.improvements_count,
                        "triggered_by": c.triggered_by,
                    }
                    for c in self._evolution_history
                ],
            }

            with open(PIPELINE_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            logger.debug("Failed to save pipeline state: %s", e)
