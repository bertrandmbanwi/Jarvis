"""
JARVIS Implicit Preference Tracker (Phase 6.3: Persistent Memory)

Learns user preferences from behavior patterns rather than explicit statements.
Tracks things like:
- Which tools/features the user triggers most often
- Time-of-day usage patterns (morning routines, end-of-day checks)
- Common request categories (music, weather, coding, scheduling)
- Preferred level of detail (does the user ask for more info, or prefer brief?)
- Frequently mentioned apps, websites, and topics

This is distinct from the FactStore (which captures explicit statements)
and the LearningLoop (which tracks tool reliability). PreferenceTracker
focuses on implicit user behavior patterns.

Preferences are accumulated over sessions and decay slowly, so recent
behavior is weighted more than old habits. Data persists in a JSON file.
"""
import json
import logging
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.memory.preferences")

PREFS_DIR = settings.DATA_DIR / "memory"
PREFS_DIR.mkdir(parents=True, exist_ok=True)
PREFS_FILE = PREFS_DIR / "implicit_preferences.json"

DECAY_RATE = 0.01


@dataclass
class InteractionPattern:
    """A tracked interaction pattern with frequency and recency."""
    name: str
    category: str
    count: int = 0
    last_seen: float = 0.0
    first_seen: float = 0.0
    hourly_counts: list[int] = field(default_factory=lambda: [0] * 24)

    def record(self, hour: int = -1):
        """Record an occurrence of this pattern."""
        self.count += 1
        self.last_seen = time.time()
        if self.first_seen == 0.0:
            self.first_seen = self.last_seen
        if 0 <= hour < 24:
            self.hourly_counts[hour] += 1

    @property
    def recency_weight(self) -> float:
        """Weight based on recency (1.0 = just now, decays over days)."""
        if self.last_seen == 0.0:
            return 0.0
        days_ago = (time.time() - self.last_seen) / 86400
        return math.exp(-DECAY_RATE * days_ago)

    @property
    def weighted_score(self) -> float:
        """Combined frequency and recency score."""
        return self.count * self.recency_weight

    @property
    def peak_hour(self) -> Optional[int]:
        """Hour of day when this pattern is most common."""
        if max(self.hourly_counts) == 0:
            return None
        return self.hourly_counts.index(max(self.hourly_counts))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "count": self.count,
            "last_seen": self.last_seen,
            "first_seen": self.first_seen,
            "hourly_counts": self.hourly_counts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionPattern":
        hourly = data.get("hourly_counts", [0] * 24)
        # Ensure exactly 24 buckets
        if len(hourly) < 24:
            hourly.extend([0] * (24 - len(hourly)))
        return cls(
            name=data["name"],
            category=data.get("category", "unknown"),
            count=data.get("count", 0),
            last_seen=data.get("last_seen", 0.0),
            first_seen=data.get("first_seen", 0.0),
            hourly_counts=hourly[:24],
        )

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "weather": ["weather", "temperature", "forecast", "rain", "sunny", "cloudy"],
    "music": ["music", "song", "play", "spotify", "playlist", "album", "artist"],
    "email": ["email", "mail", "inbox", "unread", "send email", "compose"],
    "calendar": ["calendar", "schedule", "meeting", "event", "appointment", "remind"],
    "coding": ["code", "debug", "script", "function", "programming", "deploy", "git", "build"],
    "files": ["file", "folder", "directory", "download", "document", "pdf"],
    "web_search": ["search", "google", "look up", "find out", "what is"],
    "system": ["battery", "volume", "brightness", "disk", "cpu", "memory", "app"],
    "browsing": ["open", "website", "url", "browser", "chrome", "safari", "firefox"],
    "communication": ["slack", "message", "text", "call", "teams", "discord"],
    "news": ["news", "headlines", "what happened", "current events"],
}


class PreferenceTracker:
    """Tracks implicit user preferences from behavior patterns."""

    def __init__(self):
        self._patterns: dict[str, InteractionPattern] = {}
        self._loaded = False
        self._dirty = False

        self._session_topics: Counter = Counter()
        self._session_tools: Counter = Counter()
        self._detail_requests = 0
        self._brevity_signals = 0

    def load(self):
        """Load preference data from disk."""
        if self._loaded:
            return
        if PREFS_FILE.exists():
            try:
                data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
                for item in data:
                    pattern = InteractionPattern.from_dict(item)
                    self._patterns[pattern.name] = pattern
                logger.info("Loaded %d preference patterns from disk.", len(self._patterns))
            except Exception as e:
                logger.warning("Could not load preferences: %s", e)
        self._loaded = True

    def save(self):
        """Persist preferences to disk."""
        if not self._dirty:
            return
        try:
            data = [p.to_dict() for p in self._patterns.values()]
            PREFS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._dirty = False
        except Exception as e:
            logger.warning("Could not save preferences: %s", e)

    def _get_or_create(self, name: str, category: str) -> InteractionPattern:
        """Get or create an interaction pattern."""
        if name not in self._patterns:
            self._patterns[name] = InteractionPattern(name=name, category=category)
        return self._patterns[name]

    def record_request(self, user_message: str, tier: str, tool_calls: list[str] = None):
        """Record a user interaction for preference learning."""
        from datetime import datetime
        hour = datetime.now().hour

        time_pattern = self._get_or_create("usage_time", "time")
        time_pattern.record(hour)

        tier_pattern = self._get_or_create(f"tier_{tier}", "tier")
        tier_pattern.record(hour)

        msg_lower = user_message.lower()
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in msg_lower for kw in keywords):
                topic_pattern = self._get_or_create(f"topic_{topic}", "topic")
                topic_pattern.record(hour)
                self._session_topics[topic] += 1

        if tool_calls:
            for tool_name in tool_calls:
                tool_pattern = self._get_or_create(f"tool_{tool_name}", "tool")
                tool_pattern.record(hour)
                self._session_tools[tool_name] += 1

        detail_phrases = ["more detail", "explain more", "tell me more", "elaborate", "full list", "list them all"]
        brevity_phrases = ["thanks", "got it", "ok", "perfect", "that's enough"]

        if any(p in msg_lower for p in detail_phrases):
            self._detail_requests += 1
            detail_pref = self._get_or_create("prefers_detail", "detail")
            detail_pref.record(hour)

        if any(p in msg_lower for p in brevity_phrases) and len(user_message) < 30:
            self._brevity_signals += 1
            brevity_pref = self._get_or_create("prefers_brevity", "detail")
            brevity_pref.record(hour)

        if len(user_message) > 200:
            verbose_pattern = self._get_or_create("verbose_input", "style")
            verbose_pattern.record(hour)
        elif len(user_message) < 20:
            terse_pattern = self._get_or_create("terse_input", "style")
            terse_pattern.record(hour)

        self._dirty = True

        total_count = sum(p.count for p in self._patterns.values())
        if total_count % 20 == 0:
            self.save()

    def get_top_topics(self, limit: int = 5) -> list[tuple[str, float]]:
        """Get the user's most frequent topics, weighted by recency."""
        topic_patterns = [
            (p.name.replace("topic_", ""), p.weighted_score)
            for p in self._patterns.values()
            if p.category == "topic" and p.weighted_score > 0
        ]
        topic_patterns.sort(key=lambda x: x[1], reverse=True)
        return topic_patterns[:limit]

    def get_top_tools(self, limit: int = 5) -> list[tuple[str, float]]:
        """Get the user's most frequently used tools."""
        tool_patterns = [
            (p.name.replace("tool_", ""), p.weighted_score)
            for p in self._patterns.values()
            if p.category == "tool" and p.weighted_score > 0
        ]
        tool_patterns.sort(key=lambda x: x[1], reverse=True)
        return tool_patterns[:limit]

    def get_active_hours(self) -> list[int]:
        """Get the hours of day when the user is most active."""
        time_pattern = self._patterns.get("usage_time")
        if not time_pattern:
            return []

        # Find hours with above-average activity
        hourly = time_pattern.hourly_counts
        avg = sum(hourly) / 24 if sum(hourly) > 0 else 0
        return [h for h in range(24) if hourly[h] > avg]

    def get_detail_preference(self) -> str:
        """Infer whether the user prefers detailed or brief responses."""
        detail = self._patterns.get("prefers_detail")
        brevity = self._patterns.get("prefers_brevity")

        detail_score = detail.weighted_score if detail else 0
        brevity_score = brevity.weighted_score if brevity else 0

        if detail_score > brevity_score * 1.5:
            return "detailed"
        elif brevity_score > detail_score * 1.5:
            return "brief"
        return "balanced"

    def get_context_string(self) -> str:
        """Generate preference context string for system prompt injection."""
        sections = []

        topics = self.get_top_topics(3)
        if topics:
            topic_list = ", ".join(t[0] for t in topics)
            sections.append(f"Frequent topics: {topic_list}")

        active = self.get_active_hours()
        if active:
            if len(active) > 3:
                sections.append(
                    f"Most active hours: {active[0]:02d}:00-{active[-1]:02d}:00"
                )

        detail_pref = self.get_detail_preference()
        if detail_pref != "balanced":
            sections.append(f"Response preference: {detail_pref}")

        if not sections:
            return ""

        return "<learned_preferences>\n  " + "\n  ".join(sections) + "\n</learned_preferences>"

    def get_stats(self) -> dict:
        """Get preference tracker statistics."""
        return {
            "total_patterns": len(self._patterns),
            "categories": dict(
                Counter(p.category for p in self._patterns.values())
            ),
            "top_topics": self.get_top_topics(5),
            "top_tools": self.get_top_tools(5),
            "active_hours": self.get_active_hours(),
            "detail_preference": self.get_detail_preference(),
            "session_topics": dict(self._session_topics.most_common(5)),
            "session_tools": dict(self._session_tools.most_common(5)),
        }
