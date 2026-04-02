"""
A/B Testing Framework for Prompt Templates

This module provides tools to randomly assign template versions for the same task type,
track which version was used, and calculate success rates per version.
"""

import sqlite3
import uuid
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from datetime import datetime
import random
import math

import yaml

from jarvis.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = settings.JARVIS_HOME / "templates" / "prompts"
DB_PATH = settings.DATA_DIR / "jarvis_experiments.db"

MIN_TASKS_FOR_WINNER = 20
MIN_RATE_DIFFERENCE = 10.0  # percentage points


@dataclass
class PromptTemplate:
    """Represents a prompt template version."""
    task_type: str
    version: str
    file_path: Path
    description: str
    sections: List[Dict[str, str]]
    success_rate: Optional[float] = None
    raw_data: Dict = field(default_factory=dict)


@dataclass
class VersionStats:
    """Statistics for a template version."""
    version: str
    success_rate: float
    total_tasks: int
    passed: int
    failed: int
    confidence_interval: Tuple[float, float]


class ABTester:
    """Framework for A/B testing prompt templates."""

    def __init__(self) -> None:
        """Initialize the A/B tester and ensure database exists."""
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create database and tables if they don't exist."""
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                template_version TEXT NOT NULL,
                success INTEGER,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)

        conn.commit()
        conn.close()

    def _discover_versions(self, task_type: str) -> List[PromptTemplate]:
        """
        Discover all available template versions for a task type.

        Args:
            task_type: Type of task (e.g., 'build', 'fix', 'feature')

        Returns:
            List of PromptTemplate objects
        """
        templates = []
        template_file = TEMPLATES_DIR / f"{task_type}.yaml"

        if not template_file.exists():
            logger.warning(f"No template found for task_type: {task_type}")
            return templates

        try:
            with open(template_file, 'r') as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning(f"Template file empty: {template_file}")
                return templates

            template = PromptTemplate(
                task_type=data.get('task_type', task_type),
                version=data.get('version', 'v1'),
                file_path=template_file,
                description=data.get('description', ''),
                sections=data.get('sections', []),
                raw_data=data
            )
            templates.append(template)

        except Exception as e:
            logger.error(f"Error loading template {template_file}: {e}")

        return templates

    def select_template(self, task_type: str) -> Tuple[Optional[PromptTemplate], str]:
        """
        Select a template version for a task, randomly assigning if multiple versions exist.

        Args:
            task_type: Type of task

        Returns:
            Tuple of (PromptTemplate, experiment_id) or (None, '') if no template found
        """
        versions = self._discover_versions(task_type)

        if not versions:
            logger.error(f"No templates found for task_type: {task_type}")
            return None, ''

        selected = random.choice(versions)
        experiment_id = str(uuid.uuid4())

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO experiments (id, task_type, template_version, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            experiment_id,
            task_type,
            selected.version,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        logger.info(f"Selected template {selected.version} for {task_type}, experiment_id: {experiment_id}")
        return selected, experiment_id

    def record_result(self, experiment_id: str, template_version: str, success: bool) -> None:
        """
        Record the result of a template experiment.

        Args:
            experiment_id: ID of the experiment
            template_version: Version of template used
            success: Whether the task succeeded
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE experiments
            SET success = ?, completed_at = ?
            WHERE id = ?
        """, (
            1 if success else 0,
            datetime.utcnow().isoformat(),
            experiment_id
        ))

        conn.commit()
        conn.close()

        logger.info(f"Recorded result for experiment {experiment_id}: success={success}")

    def get_version_stats(self, task_type: str) -> Dict[str, VersionStats]:
        """
        Get statistics for all versions of a task type.

        Args:
            task_type: Type of task

        Returns:
            Dictionary mapping version strings to VersionStats
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT template_version, success, COUNT(*) as total
            FROM experiments
            WHERE task_type = ? AND success IS NOT NULL
            GROUP BY template_version, success
        """, (task_type,))

        results = cursor.fetchall()
        conn.close()

        version_data = {}
        for version, success, count in results:
            if version not in version_data:
                version_data[version] = {'passed': 0, 'failed': 0}

            if success == 1:
                version_data[version]['passed'] += count
            else:
                version_data[version]['failed'] += count

        stats = {}
        for version, counts in version_data.items():
            total = counts['passed'] + counts['failed']
            passed = counts['passed']
            success_rate = (passed / total * 100) if total > 0 else 0.0

            lower, upper = self._wilson_interval(passed, total)
            confidence_interval = (lower * 100, upper * 100)

            stats[version] = VersionStats(
                version=version,
                success_rate=success_rate,
                total_tasks=total,
                passed=passed,
                failed=counts['failed'],
                confidence_interval=confidence_interval
            )

        return stats

    def promote_winner(self, task_type: str) -> Optional[str]:
        """
        Identify and promote the winning template version.

        Requires: minimum 20 tasks per version, at least 10 percentage point difference.

        Args:
            task_type: Type of task

        Returns:
            Version string of winner, or None if no clear winner
        """
        stats = self.get_version_stats(task_type)

        if not stats:
            logger.info(f"No statistics available for {task_type}")
            return None

        viable_versions = {
            v: s for v, s in stats.items()
            if s.total_tasks >= MIN_TASKS_FOR_WINNER
        }

        if len(viable_versions) < 2:
            logger.info(
                f"Not enough viable versions for {task_type}. "
                f"Need at least 2 versions with {MIN_TASKS_FOR_WINNER}+ tasks."
            )
            return None

        sorted_versions = sorted(
            viable_versions.items(),
            key=lambda x: x[1].success_rate,
            reverse=True
        )

        winner_version, winner_stats = sorted_versions[0]
        runner_up_version, runner_up_stats = sorted_versions[1]

        rate_difference = winner_stats.success_rate - runner_up_stats.success_rate

        if rate_difference >= MIN_RATE_DIFFERENCE:
            logger.info(
                f"Winner for {task_type}: {winner_version} "
                f"({winner_stats.success_rate:.1f}% vs {runner_up_stats.success_rate:.1f}%)"
            )
            return winner_version

        logger.info(
            f"No clear winner for {task_type}. "
            f"Gap: {rate_difference:.1f}% (need {MIN_RATE_DIFFERENCE}%)"
        )
        return None

    @staticmethod
    def _wilson_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
        """
        Calculate Wilson score confidence interval for success rate.

        Args:
            successes: Number of successful outcomes
            total: Total number of outcomes
            z: Z-score for confidence level (1.96 for 95%)

        Returns:
            Tuple of (lower_bound, upper_bound) as proportions (0-1)
        """
        if total == 0:
            return (0.0, 1.0)

        p = successes / total
        z_sq = z * z
        denominator = 1 + z_sq / total

        center = (p + z_sq / (2 * total)) / denominator
        margin = z * math.sqrt(p * (1 - p) / total + z_sq / (4 * total * total)) / denominator

        lower = max(0.0, center - margin)
        upper = min(1.0, center + margin)

        return (lower, upper)
