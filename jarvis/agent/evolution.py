"""
Template Evolution Engine

This module analyzes template failures and generates improved template versions
by learning from failure patterns and applying fixes to prompt sections.
"""

import sqlite3
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

import yaml

from jarvis.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = settings.JARVIS_HOME / "templates" / "prompts"
DB_PATH = settings.DATA_DIR / "jarvis_experiments.db"


@dataclass
class FailurePattern:
    """Represents a known failure pattern and its fix."""
    pattern_name: str
    keywords: List[str]
    fix_section: str
    fix_content: str


@dataclass
class Improvement:
    """Represents a suggested improvement to a template."""
    section_name: str
    reason: str
    suggested_addition: str


@dataclass
class FailureAnalysis:
    """Analysis of failure patterns for a task type."""
    task_type: str
    total_failures: int
    pattern_counts: Dict[str, int] = field(default_factory=dict)
    most_common_pattern: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)


class TemplateEvolver:
    """Engine for analyzing template failures and evolving templates."""

    # Known failure patterns and their fixes
    FAILURE_PATTERNS = [
        FailurePattern(
            pattern_name="import_errors",
            keywords=["import", "module not found", "cannot import", "no module", "importerror"],
            fix_section="acceptance_criteria",
            fix_content="- [ ] All imports resolve without errors"
        ),
        FailurePattern(
            pattern_name="file_missing",
            keywords=["file not found", "no such file", "cannot find", "missing file", "filenotfounderror"],
            fix_section="acceptance_criteria",
            fix_content="- [ ] All referenced files are created and exist"
        ),
        FailurePattern(
            pattern_name="syntax_error",
            keywords=["syntax error", "syntaxerror", "invalid syntax", "parsing failed"],
            fix_section="acceptance_criteria",
            fix_content="- [ ] Code passes linter without syntax errors"
        ),
        FailurePattern(
            pattern_name="wrong_tech",
            keywords=["wrong framework", "unexpected library", "incorrect tech", "wrong version"],
            fix_section="tech_stack",
            fix_content="Explicit tech stack verification required before implementation."
        ),
        FailurePattern(
            pattern_name="incomplete",
            keywords=["todo", "placeholder", "not implemented", "fix me", "xxx"],
            fix_section="acceptance_criteria",
            fix_content="- [ ] No TODO comments, placeholder text, or incomplete sections remain"
        ),
        FailurePattern(
            pattern_name="test_failure",
            keywords=["test failed", "assertion error", "testfailed", "test error"],
            fix_section="acceptance_criteria",
            fix_content="- [ ] All unit tests pass with 100% success rate"
        ),
    ]

    def __init__(self) -> None:
        """Initialize the template evolver."""
        pass

    def analyze_failures(self, task_type: str) -> FailureAnalysis:
        """
        Analyze failure patterns for a task type.

        Args:
            task_type: Type of task to analyze

        Returns:
            FailureAnalysis object with pattern counts and recommendations
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get all failed experiments for this task type
        cursor.execute("""
            SELECT id FROM experiments
            WHERE task_type = ? AND success = 0
        """, (task_type,))

        failed_experiments = [row[0] for row in cursor.fetchall()]
        conn.close()

        total_failures = len(failed_experiments)

        if total_failures == 0:
            logger.info(f"No failures found for task_type: {task_type}")
            return FailureAnalysis(
                task_type=task_type,
                total_failures=0
            )

        pattern_counts = {}
        for pattern in self.FAILURE_PATTERNS:
            pattern_counts[pattern.pattern_name] = 0

        # In a real implementation, we would check error logs or exception messages
        # For now, we provide infrastructure for pattern matching
        for experiment_id in failed_experiments:
            for pattern in self.FAILURE_PATTERNS:
                # Placeholder: actual implementation would query error details
                pass

        most_common = max(pattern_counts, key=pattern_counts.get) if pattern_counts else None

        recommendations = []
        if most_common:
            for pattern in self.FAILURE_PATTERNS:
                if pattern.pattern_name == most_common:
                    recommendations.append(
                        f"Most common failure: {pattern.pattern_name}. "
                        f"Consider adding criteria to {pattern.fix_section}."
                    )

        return FailureAnalysis(
            task_type=task_type,
            total_failures=total_failures,
            pattern_counts=pattern_counts,
            most_common_pattern=most_common,
            recommendations=recommendations
        )

    def suggest_improvements(self, task_type: str) -> List[Improvement]:
        """
        Generate improvement suggestions based on failure analysis.

        Args:
            task_type: Type of task to improve

        Returns:
            List of Improvement objects
        """
        analysis = self.analyze_failures(task_type)
        improvements = []

        if analysis.total_failures == 0:
            logger.info(f"No failures to analyze for {task_type}")
            return improvements

        for pattern_name, count in analysis.pattern_counts.items():
            if count > 0:
                pattern = next(
                    (p for p in self.FAILURE_PATTERNS if p.pattern_name == pattern_name),
                    None
                )

                if pattern:
                    improvements.append(
                        Improvement(
                            section_name=pattern.fix_section,
                            reason=f"Fix {pattern_name} pattern (occurred {count} times)",
                            suggested_addition=pattern.fix_content
                        )
                    )

        return improvements

    def create_new_version(self, task_type: str, improvements: List[Improvement]) -> str:
        """
        Create a new version of a template with improvements applied.

        Args:
            task_type: Type of task
            improvements: List of improvements to apply

        Returns:
            New version identifier (e.g., 'v2')
        """
        template_file = TEMPLATES_DIR / f"{task_type}.yaml"

        if not template_file.exists():
            logger.error(f"Template not found: {template_file}")
            return ''

        try:
            with open(template_file, 'r') as f:
                template_data = yaml.safe_load(f)

            current_version = template_data.get('version', 'v1')
            version_num = int(re.search(r'\d+', current_version).group())
            new_version = f"v{version_num + 1}"

            # Apply improvements
            sections = template_data.get('sections', [])

            for improvement in improvements:
                section_found = False

                for section in sections:
                    if section.get('name') == improvement.section_name:
                        # Append improvement content
                        current_content = section.get('content', '')
                        section['content'] = current_content.rstrip() + '\n' + improvement.suggested_addition
                        section_found = True
                        break

                if not section_found:
                    # Create new section if it doesn't exist
                    sections.append({
                        'name': improvement.section_name,
                        'content': improvement.suggested_addition
                    })

            template_data['version'] = new_version
            template_data['sections'] = sections
            template_data['created_at'] = datetime.utcnow().isoformat()

            # Save new version
            with open(template_file, 'w') as f:
                yaml.dump(template_data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Created new template version {new_version} for {task_type}")
            return new_version

        except Exception as e:
            logger.error(f"Error creating new version for {task_type}: {e}")
            return ''

    def evolve_if_needed(self, task_type: str, min_failures: int = 5) -> Optional[str]:
        """
        Analyze failures and evolve template if failure threshold is met.

        Args:
            task_type: Type of task
            min_failures: Minimum failure count before evolution

        Returns:
            New version string if evolved, None otherwise
        """
        analysis = self.analyze_failures(task_type)

        if analysis.total_failures < min_failures:
            logger.info(
                f"Insufficient failures ({analysis.total_failures}) for {task_type}. "
                f"Need {min_failures} to trigger evolution."
            )
            return None

        improvements = self.suggest_improvements(task_type)

        if not improvements:
            logger.info(f"No improvements suggested for {task_type}")
            return None

        new_version = self.create_new_version(task_type, improvements)

        if new_version:
            logger.info(
                f"Evolved {task_type} from {analysis.total_failures} failures. "
                f"New version: {new_version}"
            )

        return new_version if new_version else None
