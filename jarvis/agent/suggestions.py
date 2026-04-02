"""
Proactive Suggestions Agent - Post-task suggestions based on file system heuristics.

Analyzes completed tasks and the project directory to suggest follow-up improvements
without requiring LLM calls. All suggestions are based on file system patterns and
heuristics.

Suggestion priority order:
    1. Missing favicon in web projects
    2. No tests directory/files found
    3. No README.md present (for projects with 3+ files)
    4. Missing .gitignore
    5. Lint issues (basic file checks)
    6. Quality improvements from QA results
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jarvis.agent.qa_agent import QAResult

logger = logging.getLogger("jarvis.suggestions")

# Web project indicators
WEB_PROJECT_FILES = {"package.json", "index.html", "index.js", "index.tsx", "main.jsx"}

# Favicon patterns
FAVICON_PATTERNS = {"favicon.ico", "favicon.png", "favicon.svg", "apple-touch-icon.png"}

# Test directory/file patterns
TEST_PATTERNS = {
    "__tests__",
    "tests",
    "test",
    "_test",
    ".test",
    ".spec",
    "_spec",
}

# Task types that benefit from suggestions
SUGGEST_FOR_TASK_TYPES = {"build", "feature", "fix", "create", "setup"}


@dataclass
class Suggestion:
    """A follow-up suggestion for the user."""
    text: str  # Voice-friendly suggestion text
    action_type: str  # "add_favicon", "add_tests", "add_readme", "refactor"
    action_details: dict  # Tool-specific details (path, content, etc.)


def suggest_followup(
    task_type: str,
    task_description: str,
    working_dir: str,
    qa_result: Optional[QAResult] = None,
) -> Optional[Suggestion]:
    """
    Generate a proactive follow-up suggestion based on task and project state.

    Checks are performed in priority order; returns first match.

    Args:
        task_type: Type of task completed (build, feature, fix, etc.)
        task_description: Description of what was done
        working_dir: Working directory path to analyze
        qa_result: QAResult from verification (optional)

    Returns:
        Suggestion object if found, None if no suggestions apply
    """
    if task_type not in SUGGEST_FOR_TASK_TYPES:
        logger.debug("Task type '%s' not eligible for suggestions", task_type)
        return None

    if not os.path.isdir(working_dir):
        logger.warning("Working directory does not exist: %s", working_dir)
        return None

    logger.info("Checking for follow-up suggestions in %s (task_type=%s)", working_dir, task_type)

    # Priority 1: Missing favicon in web projects
    if _is_web_project(working_dir):
        favicon_suggestion = _check_missing_favicon(working_dir)
        if favicon_suggestion:
            return favicon_suggestion

    # Priority 2: No tests directory/files
    tests_suggestion = _check_missing_tests(working_dir)
    if tests_suggestion:
        return tests_suggestion

    # Priority 3: No README.md (only if project has 3+ files)
    file_count = len([f for f in os.listdir(working_dir) if os.path.isfile(os.path.join(working_dir, f))])
    if file_count >= 3:
        readme_suggestion = _check_missing_readme(working_dir)
        if readme_suggestion:
            return readme_suggestion

    # Priority 4: QA noted quality improvements
    if qa_result and qa_result.issues:
        quality_suggestion = _check_quality_issues(qa_result)
        if quality_suggestion:
            return quality_suggestion

    logger.debug("No suggestions found for task in %s", working_dir)
    return None


def _is_web_project(path: str) -> bool:
    """
    Check if directory appears to be a web project.

    Looks for package.json, index.html, or other web project indicators.

    Args:
        path: Directory path to check

    Returns:
        True if web project indicators found
    """
    try:
        files = os.listdir(path)
        files_lower = [f.lower() for f in files]
        return any(indicator in files_lower for indicator in WEB_PROJECT_FILES)
    except OSError as e:
        logger.warning("Error checking web project: %s", e)
        return False


def _check_missing_favicon(working_dir: str) -> Optional[Suggestion]:
    """
    Check if web project is missing a favicon.

    Args:
        working_dir: Project directory path

    Returns:
        Suggestion if favicon is missing, None otherwise
    """
    try:
        files = os.listdir(working_dir)
        files_lower = [f.lower() for f in files]

        for pattern in FAVICON_PATTERNS:
            if pattern.lower() in files_lower:
                return None

        logger.info("Web project missing favicon in %s", working_dir)

        return Suggestion(
            text="That's done, sir. I noticed the project is missing a favicon. "
                 "Would you like me to generate one?",
            action_type="add_favicon",
            action_details={
                "path": os.path.join(working_dir, "favicon.ico"),
                "description": "Generate or add favicon for web project",
            },
        )

    except OSError as e:
        logger.warning("Error checking favicon: %s", e)
        return None


def _check_missing_tests(working_dir: str) -> Optional[Suggestion]:
    """
    Check if project is missing test files or directory.

    Args:
        working_dir: Project directory path

    Returns:
        Suggestion if tests are missing, None otherwise
    """
    try:
        entries = os.listdir(working_dir)
        entries_lower = [e.lower() for e in entries]

        # Check for test directories
        for pattern in TEST_PATTERNS:
            if pattern in entries_lower:
                return None

            if pattern.startswith("_") or pattern.startswith("."):
                pattern_variants = [
                    f"{pattern[1:]}_test",
                    f"{pattern[1:]}_spec",
                ]
                if any(v in entries_lower for v in pattern_variants):
                    return None

        # Check for test files
        test_file_patterns = [".test.", ".spec.", "_test.", "_spec."]
        if any(
            any(pattern in f for pattern in test_file_patterns)
            for f in entries
        ):
            return None

        logger.info("Project missing tests in %s", working_dir)

        return Suggestion(
            text="That's done, sir. I notice there are no test files yet. "
                 "Should I set up a test framework?",
            action_type="add_tests",
            action_details={
                "directory": os.path.join(working_dir, "tests"),
                "description": "Add test framework and initial tests",
            },
        )

    except OSError as e:
        logger.warning("Error checking tests: %s", e)
        return None


def _check_missing_readme(working_dir: str) -> Optional[Suggestion]:
    """
    Check if project is missing a README.md file.

    Args:
        working_dir: Project directory path

    Returns:
        Suggestion if README is missing, None otherwise
    """
    try:
        files = os.listdir(working_dir)
        files_lower = [f.lower() for f in files]

        readme_patterns = ["readme.md", "readme.txt", "readme"]
        if any(pattern in files_lower for pattern in readme_patterns):
            return None

        logger.info("Project missing README in %s", working_dir)

        return Suggestion(
            text="That's done, sir. I noticed the project lacks a README. "
                 "Shall I write one?",
            action_type="add_readme",
            action_details={
                "path": os.path.join(working_dir, "README.md"),
                "description": "Generate README.md with project overview",
            },
        )

    except OSError as e:
        logger.warning("Error checking README: %s", e)
        return None


def _check_quality_issues(qa_result: Optional[list[str]]) -> Optional[Suggestion]:
    """
    Check if QA results suggest quality improvements.

    Args:
        qa_result: List of QA issues from verification

    Returns:
        Suggestion if quality improvements are noted, None otherwise
    """
    if not qa_result or len(qa_result) == 0:
        return None

    issue_keywords = ["refactor", "clean", "optimize", "simplify", "improve"]
    issue_text = " ".join(qa_result).lower()

    if any(keyword in issue_text for keyword in issue_keywords):
        logger.info("Quality improvement suggested from QA: %s", qa_result[0])

        return Suggestion(
            text="That's done, sir. The QA noted some quality opportunities. "
                 "Would you like me to refactor for better code clarity?",
            action_type="refactor",
            action_details={
                "issues": qa_result,
                "description": "Address quality improvements noted in QA",
            },
        )

    return None


def _check_missing_gitignore(working_dir: str) -> Optional[Suggestion]:
    """
    Check if project is missing a .gitignore file.

    Args:
        working_dir: Project directory path

    Returns:
        Suggestion if .gitignore is missing, None otherwise
    """
    try:
        files = os.listdir(working_dir)
        files_lower = [f.lower() for f in files]

        if ".gitignore" in files_lower:
            return None

        logger.info("Project missing .gitignore in %s", working_dir)

        return Suggestion(
            text="That's done, sir. I notice the project is missing a .gitignore. "
                 "Should I create one with common patterns?",
            action_type="add_gitignore",
            action_details={
                "path": os.path.join(working_dir, ".gitignore"),
                "description": "Generate .gitignore with language-appropriate patterns",
            },
        )

    except OSError as e:
        logger.warning("Error checking gitignore: %s", e)
        return None


def _has_tests(working_dir: str) -> bool:
    """
    Check if project has test files or directory.

    Args:
        working_dir: Project directory path

    Returns:
        True if tests found, False otherwise
    """
    try:
        entries = os.listdir(working_dir)
        entries_lower = [e.lower() for e in entries]

        for pattern in TEST_PATTERNS:
            if pattern in entries_lower:
                return True

        test_file_patterns = [".test.", ".spec.", "_test.", "_spec."]
        if any(
            any(pattern in f for pattern in test_file_patterns)
            for f in entries
        ):
            return True

        return False

    except OSError:
        return False


def _is_python_project(path: str) -> bool:
    """
    Check if directory appears to be a Python project.

    Looks for setup.py, pyproject.toml, or requirements.txt.

    Args:
        path: Directory path to check

    Returns:
        True if Python project indicators found
    """
    try:
        files = os.listdir(path)
        files_lower = [f.lower() for f in files]
        python_indicators = {"setup.py", "pyproject.toml", "requirements.txt", "poetry.lock", "pipfile"}
        return any(indicator in files_lower for indicator in python_indicators)
    except OSError:
        return False


async def suggest_task_followup(
    completed_task: str,
    task_result: str,
    working_dir: Optional[str] = None,
    qa_issues: Optional[list[str]] = None,
) -> Optional[str]:
    """
    Suggest a follow-up action after task completion.

    Analyzes task result and project state to suggest next steps without LLM.
    All checks are synchronous and heuristic-based.

    Args:
        completed_task: Description of the completed task
        task_result: Result or output from the task
        working_dir: Working directory to analyze (optional)
        qa_issues: List of QA issues from verification (optional)

    Returns:
        Voice-friendly suggestion text (British butler style), or None if no suggestion
    """
    if not working_dir or not os.path.isdir(working_dir):
        logger.debug("No working directory or invalid path; skipping task followup suggestions")
        return None

    logger.info("Checking for task followup suggestions (task=%s)", completed_task)

    suggestion = None

    # Priority 1: Check for missing tests
    if not _has_tests(working_dir):
        suggestion = _check_missing_tests(working_dir)
        if suggestion:
            return suggestion.text

    # Priority 2: Check for missing README
    try:
        file_count = len([f for f in os.listdir(working_dir) if os.path.isfile(os.path.join(working_dir, f))])
        if file_count >= 3:
            suggestion = _check_missing_readme(working_dir)
            if suggestion:
                return suggestion.text
    except OSError:
        pass

    # Priority 3: Check for missing .gitignore
    suggestion = _check_missing_gitignore(working_dir)
    if suggestion:
        return suggestion.text

    # Priority 4: Check for missing favicon (web projects)
    if _is_web_project(working_dir):
        suggestion = _check_missing_favicon(working_dir)
        if suggestion:
            return suggestion.text

    # Priority 5: QA-noted improvements
    if qa_issues:
        suggestion = _check_quality_issues(qa_issues)
        if suggestion:
            return suggestion.text

    logger.debug("No followup suggestions found for task in %s", working_dir)
    return None
