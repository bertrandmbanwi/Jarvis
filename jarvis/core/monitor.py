"""
Conversation Quality Monitor - Real-time analysis of JARVIS responses.

Analyzes JARVIS responses for quality issues including response length,
character consistency (JARVIS persona), formatting problems, and user
satisfaction patterns. All analysis is synchronous and heuristic-based
(no LLM calls).

Quality checks focus on:
    - Voice suitability (length, TTS compatibility)
    - JARVIS character consistency (specific phrases, tone)
    - Conversation health (complaint patterns, user satisfaction)
"""
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("jarvis.monitor")

# Response quality thresholds
MAX_VOICE_SENTENCES = 4
MAX_VOICE_WORDS = 100

# Patterns that break JARVIS character
CORPORATE_PHRASES = {
    "how can i help": "JARVIS does not ask 'how can I help'; he just acts",
    "is there anything else": "JARVIS does not ask 'is there anything else'",
    "i'd be happy to": "Too corporate; JARVIS says 'Will do, sir' or just does it",
    "absolutely": "JARVIS does not use filler enthusiasm like 'Absolutely'",
    "great question": "JARVIS never says 'great question'",
    "as an ai": "JARVIS never breaks character with 'as an AI'",
    "i cannot": "JARVIS says 'I'm afraid that's beyond my current capabilities, sir'",
}

# User complaint patterns indicating satisfaction issues
COMPLAINT_PATTERNS = [
    r"you forgot",
    r"that'?s wrong",
    r"you'?re not listening",
    r"i already told you",
    r"you didn'?t",
    r"that'?s not what",
]

# JARVIS should use "sir" frequently
SIR_CHECK_WINDOW = 5  # Check last 5 responses


@dataclass
class QualityIssue:
    """A single quality issue found during analysis."""
    category: str  # "voice", "character", "formatting", "complaint"
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    severity: str = "warning"  # "warning", "error", "info"


class ConversationMonitor:
    """Analyzes JARVIS response quality in real-time."""

    def __init__(self, max_history: int = 200):
        """
        Initialize the conversation monitor.

        Args:
            max_history: Maximum number of issues to keep in history
        """
        self.max_history = max_history
        self.issues: deque = deque(maxlen=max_history)
        self.response_history: deque = deque(maxlen=max_history)
        self.user_history: deque = deque(maxlen=max_history)

        self.total_analyzed = 0
        self.total_issues = 0
        self._sir_usage_count = 0

    def analyze_response(self, user_text: str, jarvis_response: str) -> list[str]:
        """
        Analyze a JARVIS response for quality issues.

        Performs synchronous checks for voice suitability, character consistency,
        formatting problems, and conversation patterns.

        Args:
            user_text: The user message
            jarvis_response: JARVIS's response to analyze

        Returns:
            List of issue messages (empty if response is good)
        """
        self.total_analyzed += 1
        self.response_history.append(jarvis_response)
        self.user_history.append(user_text)

        found_issues = []

        # Check response length for voice compatibility
        voice_issues = self._check_voice_suitability(jarvis_response)
        found_issues.extend(voice_issues)

        # Check for corporate/character-breaking phrases
        character_issues = self._check_character_consistency(jarvis_response)
        found_issues.extend(character_issues)

        # Check for markdown/formatting issues
        formatting_issues = self._check_formatting(jarvis_response)
        found_issues.extend(formatting_issues)

        # Check "sir" usage across recent responses
        sir_issues = self._check_sir_usage()
        found_issues.extend(sir_issues)

        # Check user messages for complaint patterns
        complaint_issues = self._check_user_complaints(user_text)
        found_issues.extend(complaint_issues)

        # Check for memory failures
        memory_issues = self._check_memory_failure(user_text, jarvis_response)
        found_issues.extend(memory_issues)

        # Check for character breaches
        breach_issues = self._check_character_breach(jarvis_response)
        found_issues.extend(breach_issues)

        # Record issues
        for issue_msg in found_issues:
            issue = QualityIssue(
                category=self._categorize_issue(issue_msg),
                message=issue_msg,
            )
            self.issues.append(issue)
            self.total_issues += 1

        if found_issues:
            logger.warning("Response quality issues detected (%d): %s", len(found_issues), found_issues[:2])

        return found_issues

    def get_recent_issues(self, limit: int = 10) -> list[dict]:
        """
        Get recent quality issues.

        Args:
            limit: Maximum number of issues to return

        Returns:
            List of dicts with category, message, timestamp, severity
        """
        recent = list(self.issues)[-limit:]
        return [
            {
                "category": issue.category,
                "message": issue.message,
                "timestamp": issue.timestamp.isoformat(),
                "severity": issue.severity,
            }
            for issue in reversed(recent)
        ]

    def get_quality_stats(self) -> dict:
        """
        Get overall conversation quality statistics.

        Returns:
            Dict with total_analyzed, total_issues, issue_rate, recent_issues_count
        """
        issue_rate = (
            self.total_issues / self.total_analyzed
            if self.total_analyzed > 0
            else 0.0
        )

        return {
            "total_analyzed": self.total_analyzed,
            "total_issues": self.total_issues,
            "issue_rate": round(issue_rate, 3),
            "recent_issues_count": len(self.issues),
            "issue_categories": self._get_issue_categories(),
        }

    def reset(self):
        """Clear all history and stats."""
        self.issues.clear()
        self.response_history.clear()
        self.user_history.clear()
        self.total_analyzed = 0
        self.total_issues = 0
        self._sir_usage_count = 0
        logger.info("Conversation monitor reset")

    def _check_voice_suitability(self, response: str) -> list[str]:
        """
        Check if response is suitable for text-to-speech delivery.

        Issues:
            - Too many sentences (>4)
            - Too many words (>100)

        Args:
            response: Response text to check

        Returns:
            List of issue messages
        """
        issues = []

        sentence_count = len(re.split(r'[.!?]+', response.strip()))
        if sentence_count > MAX_VOICE_SENTENCES:
            issues.append(
                f"Response has {sentence_count} sentences; TTS should handle "
                f"max {MAX_VOICE_SENTENCES} (consider breaking into parts)"
            )

        word_count = len(response.split())
        if word_count > MAX_VOICE_WORDS:
            issues.append(
                f"Response has {word_count} words; recommended max {MAX_VOICE_WORDS} for voice"
            )

        return issues

    def _check_character_consistency(self, response: str) -> list[str]:
        """
        Check for phrases that break JARVIS character.

        Args:
            response: Response text to check

        Returns:
            List of issue messages for corporate/non-JARVIS phrases
        """
        issues = []
        response_lower = response.lower()

        for phrase, issue_msg in CORPORATE_PHRASES.items():
            if phrase in response_lower:
                issues.append(issue_msg)

        # Count "sir" usage
        sir_count = len(re.findall(r'\bsir\b', response_lower))
        if sir_count > 0:
            self._sir_usage_count += sir_count

        return issues

    def _check_formatting(self, response: str) -> list[str]:
        """
        Check for markdown or formatting incompatible with voice.

        Issues:
            - Em dashes (should never appear)
            - Bold markers (**)
            - Headers (#)
            - Bullet points (-, *, +)

        Args:
            response: Response text to check

        Returns:
            List of issue messages
        """
        issues = []

        if '—' in response:
            issues.append("Response contains em dashes (not TTS-compatible); use commas or periods")

        if re.search(r'\*\*.*?\*\*', response):
            issues.append("Response contains bold markdown; TTS cannot render formatting")

        if re.search(r'^#+\s', response, re.MULTILINE):
            issues.append("Response contains headers; TTS cannot render markdown")

        if re.search(r'^[-*+]\s', response, re.MULTILINE):
            issues.append("Response contains bullet points; TTS needs prose format")

        return issues

    def _check_sir_usage(self) -> list[str]:
        """
        Check if "sir" is used enough in recent responses.

        JARVIS should use "sir" at least once in the last 5 responses.

        Returns:
            List of issue messages
        """
        issues = []

        recent_responses = list(self.response_history)[-SIR_CHECK_WINDOW:]
        if recent_responses:
            sir_found = any(re.search(r'\bsir\b', r, re.IGNORECASE) for r in recent_responses)
            if not sir_found:
                issues.append(
                    f"JARVIS has not used 'sir' in the last {SIR_CHECK_WINDOW} responses; "
                    f"character consistency weakening"
                )

        return issues

    def _check_user_complaints(self, user_text: str) -> list[str]:
        """
        Check user message for complaint patterns.

        Indicates potential satisfaction or listening issues.

        Args:
            user_text: User message to analyze

        Returns:
            List of issue messages
        """
        issues = []
        user_lower = user_text.lower()

        for pattern in COMPLAINT_PATTERNS:
            if re.search(pattern, user_lower):
                issues.append(
                    f"User expressing dissatisfaction or feeling not heard "
                    f"(pattern: '{pattern}')"
                )
                break

        return issues

    def _categorize_issue(self, issue_msg: str) -> str:
        """
        Categorize an issue message.

        Args:
            issue_msg: Issue message text

        Returns:
            Category string: "voice", "character", "formatting", "complaint", "memory", "other"
        """
        msg_lower = issue_msg.lower()

        if any(x in msg_lower for x in ["tts", "voice", "sentence", "word"]):
            return "voice"
        elif any(x in msg_lower for x in ["memory", "recall", "continuity"]):
            return "memory"
        elif any(x in msg_lower for x in ["sir", "character", "corporate", "phrase", "breach", "samantha"]):
            return "character"
        elif any(x in msg_lower for x in ["markdown", "bold", "header", "bullet", "em dash"]):
            return "formatting"
        elif any(x in msg_lower for x in ["complaint", "dissatisfied", "not heard", "forgot", "wrong"]):
            return "complaint"
        else:
            return "other"

    def _get_issue_categories(self) -> dict:
        """
        Count issues by category.

        Returns:
            Dict mapping category to count
        """
        counts = {}
        for issue in self.issues:
            counts[issue.category] = counts.get(issue.category, 0) + 1
        return counts

    def _check_memory_failure(self, user_text: str, jarvis_response: str) -> list[str]:
        """
        Check for memory failure patterns.

        User mentions earlier/before/remember + JARVIS says "I don't recall".

        Args:
            user_text: User message
            jarvis_response: JARVIS response

        Returns:
            List of issue messages
        """
        issues = []
        user_lower = user_text.lower()
        response_lower = jarvis_response.lower()

        memory_triggers = [r"\bearlier\b", r"\bbefore\b", r"\bremember\b", r"\brecall\b"]
        memory_failure_patterns = [r"i don'?t recall", r"i don'?t remember", r"no memory"]

        has_memory_trigger = any(re.search(trigger, user_lower) for trigger in memory_triggers)
        has_failure_response = any(re.search(fail, response_lower) for fail in memory_failure_patterns)

        if has_memory_trigger and has_failure_response:
            issues.append(
                "Memory failure detected: user referenced past context but JARVIS "
                "has no recollection; conversation continuity broken"
            )

        return issues

    def _check_character_breach(self, response: str) -> list[str]:
        """
        Check for character breaches (e.g., mention of other AIs).

        Args:
            response: Response text

        Returns:
            List of issue messages
        """
        issues = []
        response_lower = response.lower()

        if "samantha" in response_lower:
            issues.append(
                "Character breach: 'Samantha' mentioned; JARVIS should not reference "
                "other AI systems"
            )

        return issues

    def get_quality_score(self) -> float:
        """
        Calculate conversation quality score (0.0 to 1.0).

        Based on recent issue density from last 20 responses.

        Returns:
            Quality score: 1.0 = perfect, 0.0 = all issues
        """
        if self.total_analyzed == 0:
            return 1.0

        recent_limit = 20
        recent_issues = len(list(self.issues)[-recent_limit:])
        recent_analyzed = min(self.total_analyzed, recent_limit)

        issue_rate = recent_issues / recent_analyzed if recent_analyzed > 0 else 0.0
        quality_score = max(0.0, 1.0 - issue_rate)

        return round(quality_score, 2)

    def report(self) -> dict:
        """
        Generate a quality report for the conversation.

        Returns:
            Dict with summary stats and recommendations
        """
        stats = self.get_quality_stats()
        score = self.get_quality_score()

        return {
            "quality_score": score,
            "total_responses_analyzed": stats["total_analyzed"],
            "total_issues_found": stats["total_issues"],
            "issue_rate": stats["issue_rate"],
            "issue_categories": stats["issue_categories"],
            "recent_issues": self.get_recent_issues(limit=5),
            "sir_usage_count": self._sir_usage_count,
        }
