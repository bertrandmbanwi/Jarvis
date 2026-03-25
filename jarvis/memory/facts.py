"""
JARVIS Fact Extraction Engine (Phase 6.3: Persistent Memory)

Extracts structured facts from conversations and stores them as persistent
knowledge. Facts are things JARVIS should remember about the user: their
name, job, preferences, relationships, locations, habits, and other
personal context.

Facts are stored as simple key-value-ish records with categories, confidence
scores, and timestamps. They persist across sessions in a JSON file and
are injected into the system prompt so JARVIS can reference them naturally.

Extraction uses pattern matching for high-confidence facts (explicit
statements like "my name is X") and LLM-assisted extraction for subtler
ones (mentioned in passing during conversations).

Design:
- Pattern-based extraction: fast, no API cost, high confidence
- LLM-assisted extraction: runs periodically on accumulated context, lower confidence
- Deduplication: new facts overwrite stale ones with the same category+subject
- Decay: facts that haven't been reinforced lose confidence over time
- Privacy: facts are stored locally, never sent to external services
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.memory.facts")

FACTS_DIR = settings.DATA_DIR / "memory"
FACTS_DIR.mkdir(parents=True, exist_ok=True)
FACTS_FILE = FACTS_DIR / "user_facts.json"

MAX_FACTS = 500

MIN_CONFIDENCE = 0.2

DAILY_CONFIDENCE_DECAY = 0.02


@dataclass
class Fact:
    """A single piece of knowledge about the user or environment."""
    category: str
    subject: str
    value: str
    confidence: float
    source: str
    created_at: float = field(default_factory=time.time)
    last_reinforced: float = field(default_factory=time.time)
    reinforcement_count: int = 1

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "subject": self.subject,
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "created_at": self.created_at,
            "last_reinforced": self.last_reinforced,
            "reinforcement_count": self.reinforcement_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Fact":
        return cls(
            category=data["category"],
            subject=data["subject"],
            value=data["value"],
            confidence=data.get("confidence", 0.5),
            source=data.get("source", "pattern"),
            created_at=data.get("created_at", 0.0),
            last_reinforced=data.get("last_reinforced", 0.0),
            reinforcement_count=data.get("reinforcement_count", 1),
        )

    @property
    def effective_confidence(self) -> float:
        """Confidence adjusted for time decay (unreinforced facts fade)."""
        days_since_reinforced = (time.time() - self.last_reinforced) / 86400
        decay = days_since_reinforced * DAILY_CONFIDENCE_DECAY
        return max(0.0, self.confidence - decay)

    @property
    def key(self) -> str:
        """Unique key for deduplication: category + subject."""
        return f"{self.category}:{self.subject}"

_FACT_PATTERNS: list[tuple[re.Pattern, str, str, float]] = []


def _add_pattern(pattern: str, category: str, subject: str, confidence: float = 0.85):
    """Register a fact extraction pattern."""
    _FACT_PATTERNS.append((re.compile(pattern, re.IGNORECASE), category, subject, confidence))


# Personal identity
_add_pattern(r"my name is (?P<value>\w+(?:\s\w+)?)(?:\s+and\b|\s*[.,!?;]|\s*$)", "personal", "name", 0.95)
_add_pattern(r"(?:call me|i go by) (?P<value>\w[\w\s]{1,20})(?:\s+and\b|\s*[.,!?;]|\s*$)", "personal", "nickname", 0.92)
_add_pattern(r"i(?:'m| am) (?P<value>\d{1,3}) years old", "personal", "age", 0.93)
_add_pattern(r"my birthday is (?P<value>[\w\s,]+\d{1,2})", "personal", "birthday", 0.93)

# Location
_add_pattern(r"i live in (?P<value>[\w\s,]+?)(?:\.|,|$)", "location", "city", 0.88)
_add_pattern(r"i(?:'m| am) (?:from|based in|located in) (?P<value>[\w\s,]+?)(?:\.|,|$)", "location", "city", 0.88)
_add_pattern(r"my (?:home )?address is (?P<value>.+?)(?:\.|$)", "location", "address", 0.90)
_add_pattern(r"my timezone is (?P<value>[\w/+\-]+)", "location", "timezone", 0.93)

# Work and career
_add_pattern(r"i work (?:at|for) (?P<value>[\w\s&.,]+?)(?:\.|,| as|$)", "work", "employer", 0.88)
_add_pattern(r"i(?:'m| am) a(?:n)? (?P<value>[\w\s]+?(?:engineer|developer|designer|manager|analyst|scientist|architect|consultant|admin|director|lead|specialist))", "work", "job_title", 0.85)
_add_pattern(r"my job (?:title )?is (?P<value>[\w\s]+?)(?:\.|,|$)", "work", "job_title", 0.93)
_add_pattern(r"my team is (?:called )?(?P<value>[\w\s]+?)(?:\.|,|$)", "work", "team", 0.88)

# Tech preferences
_add_pattern(r"my (?:preferred |favorite )?(?:web )?browser is (?P<value>[\w\s]+?)(?:\.|,|$)", "preference", "browser", 0.90)
_add_pattern(r"my (?:preferred |favorite )?(?:code )?editor is (?P<value>[\w\s]+?)(?:\.|,|$)", "preference", "editor", 0.90)
_add_pattern(r"i (?:mainly |mostly |primarily )?(?:code|program|develop) in (?P<value>[\w\s,+#]+?)(?:\.|,|$)", "preference", "programming_language", 0.85)
_add_pattern(r"my (?:preferred )?(?:os|operating system) is (?P<value>[\w\s]+?)(?:\.|,|$)", "preference", "os", 0.88)
_add_pattern(r"i use (?P<value>[\w\s]+?) for (?:version control|git)", "preference", "git_platform", 0.85)

# General preferences
_add_pattern(r"my (?:preferred|favorite) (?:drink|food|coffee|tea|music|color) is (?P<value>.+?)(?:\.|,|$)", "preference", "general", 0.85)
_add_pattern(r"(?:remember|note|please note) that (?P<value>.+?)(?:\.|$)", "explicit", "user_note", 0.95)
_add_pattern(r"(?:always|never) (?P<value>.+?) (?:for me|when you)", "preference", "instruction", 0.88)

# Relationships
_add_pattern(r"my (?P<rel>wife|husband|partner|girlfriend|boyfriend|spouse)(?:'s)? (?:name is|is called|is) (?P<value>\w[\w\s]{0,20})", "relationship", "partner", 0.93)
_add_pattern(r"my (?P<rel>brother|sister|mom|dad|mother|father|son|daughter)(?:'s)? (?:name is|is called|is) (?P<value>\w[\w\s]{0,20})", "relationship", "family", 0.90)
_add_pattern(r"my (?:dog|cat|pet)(?:'s)? (?:name is|is called|is) (?P<value>\w[\w\s]{0,20})", "relationship", "pet", 0.90)

# Habits and routines
_add_pattern(r"i (?:usually|always|typically) (?P<value>.+?) (?:in the morning|at night|every day|daily)", "habit", "routine", 0.75)
_add_pattern(r"i wake up (?:at|around) (?P<value>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", "habit", "wake_time", 0.88)


def _is_valid_fact_value(value: str, subject: str, category: str) -> bool:
    """Validate that extracted value is genuine fact, not conversational noise."""
    value_lower = value.lower()

    conversational_verbs = [
        r"\b(?:looking|doing|seeing|trying|getting|making|taking|using|going|coming|working)\b"
    ]

    for verb_pattern in conversational_verbs:
        if re.search(verb_pattern, value_lower) and len(value.split()) < 5:
            logger.debug("Rejected value '%s' for %s: contains conversational verb", value, subject)
            return False

    trailing_prepositions = r"\b(?:for|at|to|in|on|with|about|as|by|from)\s*$"
    if re.search(trailing_prepositions, value_lower):
        logger.debug("Rejected value '%s' for %s: ends with incomplete preposition", value, subject)
        return False

    return True


class FactStore:
    """Manages extracted facts about the user."""

    def __init__(self):
        self._facts: dict[str, Fact] = {}
        self._loaded = False
        self._dirty = False

    def load(self):
        """Load facts from disk."""
        if self._loaded:
            return
        if FACTS_FILE.exists():
            try:
                data = json.loads(FACTS_FILE.read_text(encoding="utf-8"))
                for item in data:
                    fact = Fact.from_dict(item)
                    self._facts[fact.key] = fact
                logger.info("Loaded %d user facts from disk.", len(self._facts))
            except Exception as e:
                logger.warning("Could not load facts: %s", e)
        self._loaded = True

    def save(self):
        """Save facts to disk if dirty."""
        if not self._dirty:
            return
        try:
            data = [f.to_dict() for f in self._facts.values()]
            FACTS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._dirty = False
            logger.debug("Saved %d facts to disk.", len(self._facts))
        except Exception as e:
            logger.warning("Could not save facts: %s", e)

    def add_fact(self, fact: Fact) -> bool:
        """Add or update a fact, reinforcing or replacing as needed."""
        existing = self._facts.get(fact.key)

        if existing:
            if existing.value.lower().strip() == fact.value.lower().strip():
                existing.last_reinforced = time.time()
                existing.reinforcement_count += 1
                existing.confidence = min(1.0, existing.confidence + 0.05)
                self._dirty = True
                logger.debug("Reinforced fact: %s = %s (count: %d)", fact.subject, fact.value, existing.reinforcement_count)
                return False
            elif fact.confidence >= existing.effective_confidence:
                logger.info(
                    "Updating fact: %s = '%s' -> '%s' (confidence: %.2f -> %.2f)",
                    fact.subject, existing.value, fact.value,
                    existing.effective_confidence, fact.confidence,
                )
                self._facts[fact.key] = fact
                self._dirty = True
                return True
            else:
                return False
        else:
            self._facts[fact.key] = fact
            self._dirty = True
            logger.info("New fact: [%s] %s = '%s' (confidence: %.2f)", fact.category, fact.subject, fact.value, fact.confidence)
            return True

    def extract_from_text(self, text: str) -> list[Fact]:
        """Extract facts from text using pattern matching."""
        extracted = []

        for pattern, category, subject, confidence in _FACT_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group("value").strip()
                if not value or len(value) < 2:
                    continue

                actual_subject = subject
                if "rel" in match.groupdict():
                    rel = match.group("rel")
                    actual_subject = f"{subject}_{rel}"

                if not _is_valid_fact_value(value, actual_subject, category):
                    logger.debug("Skipped extraction: '%s' for %s (failed validation)", value, actual_subject)
                    continue

                fact = Fact(
                    category=category,
                    subject=actual_subject,
                    value=value,
                    confidence=confidence,
                    source="pattern",
                )

                if self.add_fact(fact):
                    extracted.append(fact)

        return extracted

    def extract_from_exchange(self, user_message: str, assistant_response: str) -> list[Fact]:
        """Extract facts from a user-assistant exchange."""
        facts = self.extract_from_text(user_message)

        location_match = re.search(
            r"weather (?:in|for|at) (?P<value>[\w\s,]+?)(?:\?|\.|$)",
            user_message,
            re.IGNORECASE,
        )
        if location_match:
            city = location_match.group("value").strip()
            if city and len(city) > 2:
                fact = Fact(
                    category="location",
                    subject="mentioned_city",
                    value=city,
                    confidence=0.40,
                    source="pattern",
                )
                if self.add_fact(fact):
                    facts.append(fact)

        if facts:
            self.save()

        return facts

    def search(self, query: str, category: Optional[str] = None, limit: int = 10) -> list[Fact]:
        """Search facts by keyword or category."""
        query_lower = query.lower()
        results = []
        for fact in self._facts.values():
            if fact.effective_confidence < MIN_CONFIDENCE:
                continue
            if category and fact.category != category:
                continue
            if query_lower in fact.subject.lower() or query_lower in fact.value.lower():
                results.append(fact)

        results.sort(key=lambda f: f.effective_confidence, reverse=True)
        return results[:limit]

    def get_all(self, min_confidence: float = 0.0) -> list[Fact]:
        """Get all facts above a confidence threshold."""
        return sorted(
            [f for f in self._facts.values() if f.effective_confidence >= min_confidence],
            key=lambda f: (f.category, f.subject),
        )

    def get_by_category(self, category: str) -> list[Fact]:
        """Get all facts in a category."""
        return [
            f for f in self._facts.values()
            if f.category == category and f.effective_confidence >= MIN_CONFIDENCE
        ]

    def get_context_string(self, max_facts: int = 20) -> str:
        """Generate context string for injection into system prompt."""
        all_facts = [f for f in self._facts.values() if f.effective_confidence >= 0.3]
        if not all_facts:
            return ""

        all_facts.sort(
            key=lambda f: (f.effective_confidence, f.last_reinforced),
            reverse=True,
        )

        selected = all_facts[:max_facts]

        by_category: dict[str, list[Fact]] = {}
        for f in selected:
            by_category.setdefault(f.category, []).append(f)

        lines = ["<user_knowledge>"]
        for cat, facts in sorted(by_category.items()):
            cat_label = cat.replace("_", " ").title()
            for f in facts:
                lines.append(f"  {cat_label}: {f.subject} = {f.value}")
        lines.append("</user_knowledge>")

        return "\n".join(lines)

    def consolidate(self):
        """Prune low-confidence facts and enforce size limits."""
        before = len(self._facts)

        pruned_keys = [
            key for key, fact in self._facts.items()
            if fact.effective_confidence < MIN_CONFIDENCE
        ]
        for key in pruned_keys:
            del self._facts[key]

        if len(self._facts) > MAX_FACTS:
            sorted_facts = sorted(
                self._facts.items(),
                key=lambda kv: kv[1].effective_confidence,
            )
            excess = len(self._facts) - MAX_FACTS
            for key, _ in sorted_facts[:excess]:
                del self._facts[key]

        after = len(self._facts)
        if before != after:
            self._dirty = True
            self.save()
            logger.info("Fact consolidation: %d -> %d facts (%d pruned).", before, after, before - after)

    def delete_fact(self, subject: str) -> bool:
        """Delete a fact by subject name. Returns True if found and deleted."""
        keys_to_remove = [
            key for key, fact in self._facts.items()
            if fact.subject == subject
        ]
        if keys_to_remove:
            for key in keys_to_remove:
                del self._facts[key]
            self._dirty = True
            self.save()
            logger.info("Deleted %d fact(s) with subject '%s'.", len(keys_to_remove), subject)
            return True
        return False

    def get_stats(self) -> dict:
        """Get fact store statistics."""
        by_category = {}
        for fact in self._facts.values():
            cat = fact.category
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "total_facts": len(self._facts),
            "by_category": by_category,
            "avg_confidence": round(
                sum(f.effective_confidence for f in self._facts.values()) / max(len(self._facts), 1),
                3,
            ),
            "high_confidence": sum(1 for f in self._facts.values() if f.effective_confidence >= 0.8),
            "sources": dict(
                sorted(
                    {
                        src: sum(1 for f in self._facts.values() if f.source == src)
                        for src in set(f.source for f in self._facts.values())
                    }.items()
                )
            ),
        }
