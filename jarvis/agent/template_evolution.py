"""
Template Evolution System

Analyzes task failures and successes to identify patterns and suggest
improvements to prompt templates. Integrates with the learning loop
and experiments database to drive continuous template improvement.
"""
import json
import logging
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from jarvis.config import settings
from jarvis.agent.templates import PromptTemplate, register_template

logger = logging.getLogger("jarvis.agent.template_evolution")

TEMPLATES_DIR = Path(settings.TEMPLATES_DIR)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

EVOLUTION_LOG = settings.DATA_DIR / "learning" / "template_evolution.json"
EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)

FAILURE_PATTERNS: Dict[str, dict] = {
    "import": {
        "keywords": ["import", "modulenotfound", "importerror"],
        "target_sections": ["imports", "dependencies"],
        "fix": "Add missing import statement or verify package is installed",
    },
    "file_missing": {
        "keywords": ["not found", "no such file", "filenotfound"],
        "target_sections": ["file_operations", "paths"],
        "fix": "Verify file paths are correct and files exist",
    },
    "syntax": {
        "keywords": ["syntaxerror", "syntax", "invalid"],
        "target_sections": ["code_structure", "formatting"],
        "fix": "Review syntax and formatting rules",
    },
    "wrong_tech": {
        "keywords": ["wrong", "unsupported", "deprecated", "not compatible"],
        "target_sections": ["technology_choice", "version"],
        "fix": "Verify correct technology version or alternative",
    },
    "incomplete": {
        "keywords": ["incomplete", "missing", "partial", "not finished"],
        "target_sections": ["requirements", "scope"],
        "fix": "Add missing sections or complete requirements",
    },
    "test_failure": {
        "keywords": ["test failed", "assertion", "expect", "failed"],
        "target_sections": ["testing", "acceptance_criteria"],
        "fix": "Clarify testing requirements or acceptance criteria",
    },
}


@dataclass
class FailureAnalysis:
    """Analysis of failures for a specific task type."""
    task_type: str
    total_failures: int
    common_issues: List[str]
    failure_patterns: Dict[str, int]
    suggested_improvements: List[str]


@dataclass
class Improvement:
    """Suggested improvement to a template section."""
    section_name: str
    current_content: str
    suggested_change: str
    rationale: str


class TemplateEvolver:
    """Evolves templates based on task failure patterns and learning data."""

    def __init__(self, learning_loop=None):
        """
        Initialize the template evolver.

        Args:
            learning_loop: Optional LearningLoop instance for failure data
        """
        self.learning_loop = learning_loop
        self._evolution_history: List[dict] = []
        self._load_evolution_history()

    def analyze_failures(self, task_type: str) -> Optional[FailureAnalysis]:
        """
        Analyze failures for a task type using experiments database.

        Reads from EXPERIMENTS_DB and integrates with LearningLoop
        failure_log if available.

        Args:
            task_type: Type of task to analyze

        Returns:
            FailureAnalysis with patterns and issues, or None if no data
        """
        try:
            conn = sqlite3.connect(settings.EXPERIMENTS_DB)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
                FROM experiments
                WHERE task_type = ?
            """, (task_type,))

            result = cursor.fetchone()
            conn.close()

            total_tasks, total_failures = result if result else (0, 0)

            if total_failures == 0:
                logger.debug("No failures recorded for task_type: %s", task_type)
                return None

            pattern_counts: Dict[str, int] = defaultdict(int)
            common_issues: List[str] = []

            if self.learning_loop:
                try:
                    failure_patterns = self.learning_loop.get_common_failure_patterns(
                        limit=5
                    )
                    for fp in failure_patterns:
                        pattern_name = fp.get("pattern", "")
                        if pattern_name:
                            common_issues.append(pattern_name)
                except Exception as e:
                    logger.debug("Could not get learning patterns: %s", e)

            for pattern_name, pattern_info in FAILURE_PATTERNS.items():
                keywords = pattern_info.get("keywords", [])
                for issue in common_issues:
                    if any(kw in issue.lower() for kw in keywords):
                        pattern_counts[pattern_name] += 1

            suggested = [
                FAILURE_PATTERNS[p]["fix"]
                for p in pattern_counts.keys()
                if p in FAILURE_PATTERNS
            ]

            return FailureAnalysis(
                task_type=task_type,
                total_failures=total_failures,
                common_issues=common_issues,
                failure_patterns=dict(pattern_counts),
                suggested_improvements=suggested,
            )

        except Exception as e:
            logger.error("Failed to analyze failures for %s: %s", task_type, e)
            return None

    def suggest_improvements(self, task_type: str) -> List[Improvement]:
        """
        Generate improvement suggestions for a template.

        Maps detected failure patterns to specific template sections
        that should be updated.

        Args:
            task_type: Type of task to improve

        Returns:
            List of Improvement objects with specific suggestions
        """
        analysis = self.analyze_failures(task_type)
        if not analysis or not analysis.failure_patterns:
            return []

        improvements: List[Improvement] = []

        for pattern_name, count in analysis.failure_patterns.items():
            if pattern_name not in FAILURE_PATTERNS:
                continue

            pattern_info = FAILURE_PATTERNS[pattern_name]
            target_sections = pattern_info.get("target_sections", [])
            fix = pattern_info.get("fix", "")

            for section in target_sections:
                improvements.append(
                    Improvement(
                        section_name=section,
                        current_content="",
                        suggested_change=f"Enhance '{section}' to address '{pattern_name}' pattern",
                        rationale=fix,
                    )
                )

        return improvements

    def create_new_version(
        self,
        task_type: str,
        improvements: List[Improvement],
        base_template: Optional[PromptTemplate] = None,
    ) -> Optional[str]:
        """
        Create a new template version with suggested improvements.

        Writes YAML file to TEMPLATES_DIR with versioned name.

        Args:
            task_type: Type of task
            improvements: List of suggested improvements
            base_template: Optional base template to fork from

        Returns:
            Version string (e.g. 'v2') if successful, else None
        """
        try:
            template_file = TEMPLATES_DIR / f"{task_type}.yaml"

            version_num = 1
            if template_file.exists():
                try:
                    with open(template_file, 'r') as f:
                        data = yaml.safe_load(f)
                    version_str = data.get("version", "v1")
                    version_num = int(version_str.lstrip('v')) + 1
                except Exception as e:
                    logger.debug("Could not determine version: %s", e)

            new_version = f"v{version_num}"

            template_data = {
                "name": task_type,
                "version": new_version,
                "task_type": task_type,
                "keywords": [],
                "sections": [],
                "acceptance_criteria": [],
                "design_notes": [],
            }

            if base_template:
                template_data["keywords"] = base_template.keywords
                template_data["acceptance_criteria"] = base_template.acceptance_criteria

            for improvement in improvements:
                template_data["design_notes"].append({
                    "section": improvement.section_name,
                    "change": improvement.suggested_change,
                    "rationale": improvement.rationale,
                })

            backup_file = template_file.with_suffix('.yaml.bak')
            if template_file.exists():
                template_file.rename(backup_file)

            with open(template_file, 'w') as f:
                yaml.dump(template_data, f, default_flow_style=False, sort_keys=False)

            logger.info(
                "Created new template version %s for task_type %s",
                new_version,
                task_type,
            )

            self._record_evolution(task_type, new_version, improvements)

            return new_version

        except Exception as e:
            logger.error(
                "Failed to create new template version for %s: %s",
                task_type,
                e,
            )
            return None

    def evolve_if_needed(
        self,
        task_type: str,
        min_failures: int = 5,
    ) -> Optional[str]:
        """
        Check if evolution is warranted and create new version if so.

        Orchestrates the full evolution flow: analysis, improvement
        generation, and template creation.

        Args:
            task_type: Type of task to evolve
            min_failures: Minimum failures before triggering evolution

        Returns:
            New version string if created, else None
        """
        analysis = self.analyze_failures(task_type)

        if not analysis or analysis.total_failures < min_failures:
            logger.debug(
                "Insufficient failures for %s (have %d, need %d)",
                task_type,
                analysis.total_failures if analysis else 0,
                min_failures,
            )
            return None

        improvements = self.suggest_improvements(task_type)

        if not improvements:
            logger.debug("No improvements suggested for %s", task_type)
            return None

        from jarvis.agent.templates import get_template
        base_template = get_template(task_type)

        new_version = self.create_new_version(
            task_type,
            improvements,
            base_template=base_template,
        )

        return new_version

    def get_evolution_context(self) -> str:
        """
        Generate context string for injection into planner prompts.

        Summarizes active template versions and evolution status.

        Returns:
            Formatted context string ready for prompt injection
        """
        sections = []

        if not TEMPLATES_DIR.exists():
            return ""

        yaml_files = list(TEMPLATES_DIR.glob("*.yaml"))
        if not yaml_files:
            return ""

        version_info = []
        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                task_type = data.get("task_type", yaml_file.stem)
                version = data.get("version", "unknown")
                version_info.append(f"  - {task_type}: {version}")
            except Exception as e:
                logger.debug("Could not read template %s: %s", yaml_file, e)

        if version_info:
            sections.append(
                "ACTIVE TEMPLATE VERSIONS:\n" + "\n".join(version_info)
            )

        recent_evolutions = self._evolution_history[-3:] if self._evolution_history else []
        if recent_evolutions:
            evolution_lines = []
            for evo in recent_evolutions:
                evolution_lines.append(
                    f"  - {evo.get('task_type')}: upgraded to {evo.get('new_version')} "
                    f"({len(evo.get('improvements', []))} improvements)"
                )
            sections.append(
                "RECENT TEMPLATE IMPROVEMENTS:\n" + "\n".join(evolution_lines)
            )

        if not sections:
            return ""

        return (
            "\n--- TEMPLATE EVOLUTION CONTEXT ---\n"
            + "\n\n".join(sections)
            + "\n--- END TEMPLATE EVOLUTION CONTEXT ---"
        )

    def _record_evolution(
        self,
        task_type: str,
        new_version: str,
        improvements: List[Improvement],
    ) -> None:
        """
        Record evolution event for historical tracking.

        Args:
            task_type: Type of task evolved
            new_version: New version created
            improvements: List of improvements made
        """
        record = {
            "timestamp": time.time(),
            "task_type": task_type,
            "new_version": new_version,
            "improvements": [
                {
                    "section": imp.section_name,
                    "change": imp.suggested_change,
                    "rationale": imp.rationale,
                }
                for imp in improvements
            ],
        }

        self._evolution_history.append(record)

        if len(self._evolution_history) > 100:
            self._evolution_history = self._evolution_history[-100:]

        self._save_evolution_history()

    def _load_evolution_history(self) -> None:
        """Load evolution history from disk."""
        if not EVOLUTION_LOG.exists():
            return

        try:
            with open(EVOLUTION_LOG, 'r') as f:
                self._evolution_history = json.load(f)
        except Exception as e:
            logger.debug("Could not load evolution history: %s", e)

    def _save_evolution_history(self) -> None:
        """Save evolution history to disk."""
        try:
            with open(EVOLUTION_LOG, 'w') as f:
                json.dump(self._evolution_history, f, indent=2)
        except Exception as e:
            logger.debug("Failed to save evolution history: %s", e)
