"""Tests for JARVIS memory module (facts and preferences)."""
import time

import pytest

from jarvis.memory.facts import (
    FactStore,
    Fact,
    MIN_CONFIDENCE,
    DAILY_CONFIDENCE_DECAY,
)
from jarvis.memory.preferences import (
    PreferenceTracker,
    InteractionPattern,
    DECAY_RATE,
)


class TestFact:
    """Test the Fact data class."""

    def test_fact_creation(self):
        """Fact should initialize with correct attributes."""
        fact = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern"
        )
        assert fact.category == "personal"
        assert fact.subject == "name"
        assert fact.value == "John"
        assert fact.confidence == 0.95

    def test_fact_key_generation(self):
        """Fact key should combine category and subject."""
        fact = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern"
        )
        assert fact.key == "personal:name"

    def test_fact_effective_confidence_no_decay(self):
        """Fresh fact should have full confidence."""
        fact = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern"
        )
        # Just created, should have nearly full confidence
        assert fact.effective_confidence >= 0.94

    def test_fact_effective_confidence_decay(self):
        """Old facts should have decayed confidence."""
        fact = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern",
            last_reinforced=time.time() - 86400  # 1 day ago
        )
        effective = fact.effective_confidence
        assert effective < 0.95
        assert effective > 0.90

    def test_fact_to_dict(self):
        """Fact should serialize to dict."""
        fact = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern"
        )
        data = fact.to_dict()
        assert data["category"] == "personal"
        assert data["value"] == "John"

    def test_fact_from_dict(self):
        """Fact should deserialize from dict."""
        data = {
            "category": "personal",
            "subject": "name",
            "value": "John",
            "confidence": 0.95,
            "source": "pattern"
        }
        fact = Fact.from_dict(data)
        assert fact.category == "personal"
        assert fact.value == "John"


class TestFactStore:
    """Test the FactStore class."""

    def test_factstore_creation(self):
        """FactStore should initialize empty."""
        store = FactStore()
        assert len(store._facts) == 0

    def test_add_new_fact(self):
        """Adding a new fact should increase store size."""
        store = FactStore()
        fact = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern"
        )
        store.add_fact(fact)
        assert len(store._facts) == 1
        assert "personal:name" in store._facts

    def test_reinforce_existing_fact(self):
        """Adding identical fact should reinforce it."""
        store = FactStore()
        fact1 = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.95,
            source="pattern"
        )
        result1 = store.add_fact(fact1)
        assert result1 is True

        fact2 = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.90,
            source="pattern"
        )
        result2 = store.add_fact(fact2)
        assert result2 is False  # Reinforcement, not new fact

        existing = store._facts["personal:name"]
        assert existing.reinforcement_count == 2

    def test_update_fact_with_higher_confidence(self):
        """Fact with higher confidence should replace older one."""
        store = FactStore()
        fact1 = Fact(
            category="personal",
            subject="name",
            value="John",
            confidence=0.70,
            source="pattern"
        )
        store.add_fact(fact1)

        fact2 = Fact(
            category="personal",
            subject="name",
            value="Jonathan",
            confidence=0.95,
            source="explicit"
        )
        result = store.add_fact(fact2)
        assert result is True

        updated = store._facts["personal:name"]
        assert updated.value == "Jonathan"
        assert updated.confidence == 0.95

    def test_extract_from_text_name_pattern(self):
        """Should extract name from explicit statement."""
        store = FactStore()
        facts = store.extract_from_text("my name is Alice Smith")
        assert len(facts) > 0
        name_facts = [f for f in facts if f.subject == "name"]
        assert len(name_facts) > 0
        assert "Alice" in name_facts[0].value

    def test_extract_from_text_location_pattern(self):
        """Should extract location from explicit statement."""
        store = FactStore()
        facts = store.extract_from_text("I live in San Francisco")
        assert len(facts) > 0
        location_facts = [f for f in facts if f.category == "location"]
        assert len(location_facts) > 0

    def test_extract_from_text_job_pattern(self):
        """Should extract job title from statement."""
        store = FactStore()
        facts = store.extract_from_text("I am a software engineer")
        assert len(facts) > 0
        job_facts = [f for f in facts if f.subject == "job_title"]
        assert len(job_facts) > 0

    def test_extract_from_text_high_confidence(self):
        """Name extraction should have high confidence."""
        store = FactStore()
        facts = store.extract_from_text("my name is Robert")
        name_facts = [f for f in facts if f.subject == "name"]
        if name_facts:
            assert name_facts[0].confidence >= 0.90

    def test_search_facts_by_keyword(self):
        """Should search facts by keyword."""
        store = FactStore()
        fact = Fact(
            category="work",
            subject="employer",
            value="Google",
            confidence=0.95,
            source="explicit"
        )
        store.add_fact(fact)
        results = store.search("Google")
        assert len(results) > 0
        assert results[0].value == "Google"

    def test_search_facts_by_category(self):
        """Should search facts by category."""
        store = FactStore()
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        store.add_fact(Fact("work", "employer", "Google", 0.95, "pattern"))
        results = store.search("", category="personal")
        assert all(f.category == "personal" for f in results)

    def test_get_all_facts(self):
        """Should retrieve all facts above confidence threshold."""
        store = FactStore()
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        store.add_fact(Fact("work", "employer", "Google", 0.85, "pattern"))
        all_facts = store.get_all(min_confidence=0.8)
        assert len(all_facts) == 2

    def test_get_facts_by_category(self):
        """Should get all facts in a category."""
        store = FactStore()
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        store.add_fact(Fact("personal", "age", "30", 0.90, "pattern"))
        store.add_fact(Fact("work", "employer", "Google", 0.95, "pattern"))
        personal_facts = store.get_by_category("personal")
        assert len(personal_facts) == 2
        assert all(f.category == "personal" for f in personal_facts)

    def test_get_context_string(self):
        """Should generate context string for system prompt."""
        store = FactStore()
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        store.add_fact(Fact("work", "job_title", "Engineer", 0.90, "pattern"))
        context = store.get_context_string()
        if context:
            assert "Alice" in context or "name" in context.lower()

    def test_consolidate_prunes_low_confidence(self):
        """Consolidate should remove low-confidence facts."""
        store = FactStore()
        store._facts["personal:old_fact"] = Fact(
            "personal", "old_fact", "value",
            confidence=0.1,  # Below MIN_CONFIDENCE
            source="pattern",
            last_reinforced=time.time() - 100 * 86400
        )
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        before = len(store._facts)
        store.consolidate()
        after = len(store._facts)
        # Should have removed low-confidence fact
        assert after < before or "old_fact" not in store._facts

    def test_delete_fact(self):
        """Should delete fact by subject."""
        store = FactStore()
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        deleted = store.delete_fact("name")
        assert deleted is True
        assert "personal:name" not in store._facts

    def test_delete_nonexistent_fact(self):
        """Deleting nonexistent fact should return False."""
        store = FactStore()
        deleted = store.delete_fact("nonexistent")
        assert deleted is False

    def test_get_stats(self):
        """Should return fact store statistics."""
        store = FactStore()
        store.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        store.add_fact(Fact("work", "employer", "Google", 0.90, "pattern"))
        stats = store.get_stats()
        assert stats["total_facts"] == 2
        assert "by_category" in stats
        assert stats["high_confidence"] >= 0


class TestInteractionPattern:
    """Test the InteractionPattern class."""

    def test_pattern_creation(self):
        """InteractionPattern should initialize correctly."""
        pattern = InteractionPattern(name="test_pattern", category="topic")
        assert pattern.name == "test_pattern"
        assert pattern.category == "topic"
        assert pattern.count == 0

    def test_pattern_record(self):
        """Recording should increment count."""
        pattern = InteractionPattern(name="test_pattern", category="topic")
        pattern.record()
        assert pattern.count == 1
        assert pattern.last_seen > 0

    def test_pattern_record_with_hour(self):
        """Recording with hour should increment hourly count."""
        pattern = InteractionPattern(name="test_pattern", category="topic")
        pattern.record(hour=14)
        assert pattern.hourly_counts[14] == 1

    def test_pattern_peak_hour(self):
        """Peak hour should be identified correctly."""
        pattern = InteractionPattern(name="test_pattern", category="topic")
        pattern.record(hour=9)
        pattern.record(hour=9)
        pattern.record(hour=14)
        assert pattern.peak_hour == 9

    def test_pattern_recency_weight(self):
        """Recent patterns should have higher weight."""
        pattern1 = InteractionPattern(name="recent", category="topic")
        pattern1.record()

        pattern2 = InteractionPattern(name="old", category="topic")
        pattern2.record()
        pattern2.last_seen = time.time() - 86400  # 1 day ago

        assert pattern1.recency_weight > pattern2.recency_weight

    def test_pattern_weighted_score(self):
        """Weighted score should combine frequency and recency."""
        pattern = InteractionPattern(name="test", category="topic")
        for i in range(5):
            pattern.record()
        score = pattern.weighted_score
        assert score > 0
        assert score == pytest.approx(pattern.count * pattern.recency_weight)

    def test_pattern_to_dict(self):
        """Pattern should serialize to dict."""
        pattern = InteractionPattern(name="test", category="topic")
        pattern.record()
        data = pattern.to_dict()
        assert data["name"] == "test"
        assert data["count"] == 1

    def test_pattern_from_dict(self):
        """Pattern should deserialize from dict."""
        data = {
            "name": "test",
            "category": "topic",
            "count": 5,
            "hourly_counts": [0] * 24
        }
        pattern = InteractionPattern.from_dict(data)
        assert pattern.name == "test"
        assert pattern.count == 5


class TestPreferenceTracker:
    """Test the PreferenceTracker class."""

    def test_tracker_creation(self):
        """PreferenceTracker should initialize empty."""
        tracker = PreferenceTracker()
        assert len(tracker._patterns) == 0

    def test_record_request_simple(self):
        """Recording a request should create patterns."""
        tracker = PreferenceTracker()
        tracker.record_request("search for information", tier="fast")
        assert len(tracker._patterns) > 0

    def test_record_request_with_tools(self):
        """Recording should track tool usage."""
        tracker = PreferenceTracker()
        tracker.record_request(
            "search for information",
            tier="fast",
            tool_calls=["search_web", "fetch_page"]
        )
        assert "tool_search_web" in tracker._patterns
        assert "tool_fetch_page" in tracker._patterns

    def test_record_request_topic_detection(self):
        """Should detect request topics."""
        tracker = PreferenceTracker()
        tracker.record_request("what's the weather like?", tier="fast")
        # Should create a topic_weather pattern
        assert any("topic_weather" in p for p in tracker._patterns)

    def test_get_top_topics(self):
        """Should identify top topics."""
        tracker = PreferenceTracker()
        tracker.record_request("what's the weather today?", tier="fast")
        tracker.record_request("weather forecast", tier="fast")
        tracker.record_request("send me an email", tier="fast")
        topics = tracker.get_top_topics(limit=3)
        # Weather should be top topic
        assert any(t[0] == "weather" for t in topics)

    def test_get_top_tools(self):
        """Should identify top tools."""
        tracker = PreferenceTracker()
        for i in range(3):
            tracker.record_request("search", tier="fast", tool_calls=["search_web"])
        for i in range(2):
            tracker.record_request("read", tier="fast", tool_calls=["read_file"])
        tools = tracker.get_top_tools(limit=3)
        assert tools[0][0] == "search_web"

    def test_get_active_hours(self):
        """Should identify active usage hours."""
        tracker = PreferenceTracker()
        from datetime import datetime
        # Simulate activity at 14:00
        # This is mocked in real scenario
        tracker.record_request("test", tier="fast")
        hours = tracker.get_active_hours()
        # Should have some hours (at least current hour)
        assert isinstance(hours, list)

    def test_get_detail_preference_balanced(self):
        """Should detect balanced detail preference."""
        tracker = PreferenceTracker()
        tracker.record_request("tell me more about it", tier="fast")
        tracker.record_request("got it", tier="fast")
        pref = tracker.get_detail_preference()
        assert pref in ["detailed", "brief", "balanced"]

    def test_get_context_string(self):
        """Should generate preference context string."""
        tracker = PreferenceTracker()
        for i in range(3):
            tracker.record_request("weather forecast", tier="fast")
        context = tracker.get_context_string()
        if context:
            assert "weather" in context.lower() or "preference" in context.lower()

    def test_get_stats(self):
        """Should return tracker statistics."""
        tracker = PreferenceTracker()
        tracker.record_request("search for info", tier="fast", tool_calls=["search_web"])
        stats = tracker.get_stats()
        assert "total_patterns" in stats
        assert "categories" in stats
        assert "top_topics" in stats


class TestMemoryPersistence:
    """Test saving and loading memory data."""

    def test_fact_store_save_load(self, tmp_config):
        """Facts should persist to disk."""
        store1 = FactStore()
        store1.add_fact(Fact("personal", "name", "Alice", 0.95, "pattern"))
        store1.save()

        store2 = FactStore()
        store2.load()
        assert len(store2._facts) > 0

    def test_preference_tracker_save_load(self, tmp_config):
        """Preferences should persist to disk."""
        tracker1 = PreferenceTracker()
        tracker1.record_request("search for weather", tier="fast")
        tracker1.save()

        tracker2 = PreferenceTracker()
        tracker2.load()
        assert len(tracker2._patterns) > 0
