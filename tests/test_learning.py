"""Tests for JARVIS learning loop module."""
import json
import time
from pathlib import Path

import pytest

from jarvis.agent.learning import (
    LearningLoop,
    ToolStats,
    PlanPattern,
    MIN_EXECUTIONS_FOR_RELIABILITY,
)


class TestToolStats:
    """Test the ToolStats data class."""

    def test_tool_stats_creation(self):
        """ToolStats should initialize with defaults."""
        stats = ToolStats(name="test_tool")
        assert stats.name == "test_tool"
        assert stats.total_calls == 0
        assert stats.successes == 0
        assert stats.failures == 0

    def test_success_rate_no_calls(self):
        """Success rate should be 1.0 when no calls have been made."""
        stats = ToolStats(name="test_tool")
        assert stats.success_rate == 1.0

    def test_success_rate_calculation(self):
        """Success rate should be calculated correctly."""
        stats = ToolStats(name="test_tool", total_calls=10, successes=8)
        assert stats.success_rate == 0.8

    def test_avg_duration_no_success(self):
        """Avg duration should be 0.0 when no successful calls."""
        stats = ToolStats(name="test_tool", total_calls=5, successes=0)
        assert stats.avg_duration_s == 0.0

    def test_avg_duration_calculation(self):
        """Avg duration should be calculated correctly."""
        stats = ToolStats(
            name="test_tool",
            total_calls=10,
            successes=10,
            total_duration_s=50.0
        )
        assert stats.avg_duration_s == 5.0

    def test_is_reliable_insufficient_data(self):
        """Tool should be considered reliable with insufficient data."""
        stats = ToolStats(name="test_tool", total_calls=1, successes=1)
        assert stats.is_reliable is True

    def test_is_reliable_above_threshold(self):
        """Tool with > 80% success rate should be reliable."""
        total = MIN_EXECUTIONS_FOR_RELIABILITY + 1
        stats = ToolStats(
            name="test_tool",
            total_calls=total,
            successes=total,  # 100% success rate
        )
        assert stats.is_reliable is True

    def test_is_reliable_below_threshold(self):
        """Tool with < 80% success rate should be unreliable."""
        stats = ToolStats(
            name="test_tool",
            total_calls=MIN_EXECUTIONS_FOR_RELIABILITY + 10,
            successes=int((MIN_EXECUTIONS_FOR_RELIABILITY + 10) * 0.5)  # 50%
        )
        assert stats.is_reliable is False

    def test_to_dict(self):
        """ToolStats should serialize to dict."""
        stats = ToolStats(
            name="test_tool",
            total_calls=10,
            successes=8,
            failures=2,
            total_duration_s=40.0,
            last_used=1704067200.0
        )
        data = stats.to_dict()
        assert data["name"] == "test_tool"
        assert data["total_calls"] == 10
        assert data["success_rate"] == 0.8

    def test_from_dict(self):
        """ToolStats should deserialize from dict."""
        data = {
            "name": "test_tool",
            "total_calls": 10,
            "successes": 8,
            "failures": 2,
            "total_duration_s": 40.0,
            "success_rate": 0.8,
            "avg_duration_s": 5.0,
            "last_used": 1704067200.0,
            "is_reliable": True,
            "failure_reasons": []
        }
        stats = ToolStats.from_dict(data)
        assert stats.name == "test_tool"
        assert stats.total_calls == 10


class TestPlanPattern:
    """Test the PlanPattern data class."""

    def test_plan_pattern_creation(self):
        """PlanPattern should initialize correctly."""
        pattern = PlanPattern(
            request_summary="Test request",
            goal_summary="Test goal",
            subtask_count=2,
            subtask_titles=["Step 1", "Step 2"],
            completed_count=2,
            failed_count=0,
            total_duration_s=10.5,
            outcome="success"
        )
        assert pattern.request_summary == "Test request"
        assert pattern.outcome == "success"

    def test_plan_pattern_to_dict(self):
        """PlanPattern should serialize to dict."""
        pattern = PlanPattern(
            request_summary="Test request",
            goal_summary="Test goal",
            subtask_count=2,
            subtask_titles=["Step 1", "Step 2"],
            completed_count=2,
            failed_count=0,
            total_duration_s=10.5,
            outcome="success"
        )
        data = pattern.to_dict()
        assert data["request_summary"] == "Test request"
        assert data["outcome"] == "success"

    def test_plan_pattern_from_dict(self):
        """PlanPattern should deserialize from dict."""
        data = {
            "request_summary": "Test request",
            "goal_summary": "Test goal",
            "subtask_count": 2,
            "subtask_titles": ["Step 1", "Step 2"],
            "completed_count": 2,
            "failed_count": 0,
            "total_duration_s": 10.5,
            "outcome": "success",
            "timestamp": time.time(),
            "failure_reasons": []
        }
        pattern = PlanPattern.from_dict(data)
        assert pattern.request_summary == "Test request"


class TestLearningLoopInit:
    """Test LearningLoop initialization."""

    def test_learning_loop_creation(self):
        """LearningLoop should initialize without errors."""
        loop = LearningLoop()
        assert loop is not None
        assert len(loop._tool_stats) == 0
        assert len(loop._plan_patterns) == 0
        assert len(loop._failure_log) == 0

    def test_initialize_with_no_data(self, tmp_config):
        """Initialize should handle case with no persisted data."""
        loop = LearningLoop()
        loop.initialize()
        assert loop._loaded is True


class TestRecordToolCall:
    """Test recording tool execution outcomes."""

    def test_record_tool_success(self):
        """Record a successful tool call."""
        loop = LearningLoop()
        loop.record_tool_call("search_web", success=True, duration_s=5.0)
        assert "search_web" in loop._tool_stats
        stats = loop._tool_stats["search_web"]
        assert stats.total_calls == 1
        assert stats.successes == 1
        assert stats.failures == 0

    def test_record_tool_failure(self):
        """Record a failed tool call."""
        loop = LearningLoop()
        loop.record_tool_call("search_web", success=False, error="timeout")
        assert "search_web" in loop._tool_stats
        stats = loop._tool_stats["search_web"]
        assert stats.total_calls == 1
        assert stats.successes == 0
        assert stats.failures == 1
        assert "timeout" in stats.failure_reasons

    def test_record_multiple_calls_same_tool(self):
        """Record multiple calls to the same tool."""
        loop = LearningLoop()
        loop.record_tool_call("search_web", success=True, duration_s=5.0)
        loop.record_tool_call("search_web", success=True, duration_s=4.0)
        loop.record_tool_call("search_web", success=False, error="connection error")
        stats = loop._tool_stats["search_web"]
        assert stats.total_calls == 3
        assert stats.successes == 2
        assert stats.failures == 1

    def test_failure_reasons_capped_at_20(self):
        """Failure reasons should be capped at 20 entries."""
        loop = LearningLoop()
        for i in range(30):
            loop.record_tool_call("bad_tool", success=False, error=f"error_{i}")
        stats = loop._tool_stats["bad_tool"]
        assert len(stats.failure_reasons) <= 20


class TestRecordPlanOutcome:
    """Test recording plan execution outcomes."""

    def test_record_fully_successful_plan(self):
        """Record a plan where all subtasks succeeded."""
        loop = LearningLoop()
        plan = {
            "plan_id": "test_001",
            "original_request": "Search and summarize",
            "goal_summary": "Research task",
            "subtasks": [
                {"title": "Search", "description": "Search for info", "status": "completed", "duration_s": 5.0},
                {"title": "Summarize", "description": "Create summary", "status": "completed", "duration_s": 3.0},
            ],
            "completed_at": time.time()
        }
        loop.record_plan_outcome(plan)
        assert len(loop._plan_patterns) == 1
        pattern = loop._plan_patterns[0]
        assert pattern.outcome == "success"
        assert pattern.completed_count == 2
        assert pattern.failed_count == 0

    def test_record_partially_successful_plan(self):
        """Record a plan where some subtasks failed."""
        loop = LearningLoop()
        plan = {
            "plan_id": "test_002",
            "original_request": "Search and summarize",
            "goal_summary": "Research task",
            "subtasks": [
                {"title": "Search", "description": "Search", "status": "completed", "duration_s": 5.0},
                {"title": "Summarize", "description": "Summarize", "status": "failed", "duration_s": 0.0, "error": "timeout"},
            ],
            "completed_at": time.time()
        }
        loop.record_plan_outcome(plan)
        pattern = loop._plan_patterns[0]
        assert pattern.outcome == "partial"
        assert pattern.completed_count == 1
        assert pattern.failed_count == 1

    def test_record_fully_failed_plan(self):
        """Record a plan where all subtasks failed."""
        loop = LearningLoop()
        plan = {
            "plan_id": "test_003",
            "original_request": "Failed task",
            "goal_summary": "Failing task",
            "subtasks": [
                {"title": "Step 1", "description": "Do something", "status": "failed", "error": "error 1"},
                {"title": "Step 2", "description": "Do something else", "status": "failed", "error": "error 2"},
            ],
            "completed_at": time.time()
        }
        loop.record_plan_outcome(plan)
        pattern = loop._plan_patterns[0]
        assert pattern.outcome == "failed"
        assert pattern.completed_count == 0
        assert pattern.failed_count == 2

    def test_plan_patterns_capped_at_max(self):
        """Plan patterns should be capped at MAX_PLAN_PATTERNS."""
        loop = LearningLoop()
        from jarvis.agent.learning import MAX_PLAN_PATTERNS

        for i in range(MAX_PLAN_PATTERNS + 20):
            plan = {
                "plan_id": f"test_{i}",
                "original_request": f"Request {i}",
                "goal_summary": f"Goal {i}",
                "subtasks": [
                    {"title": f"Step {i}", "description": "Do something", "status": "completed", "duration_s": 1.0},
                ],
                "completed_at": time.time()
            }
            loop.record_plan_outcome(plan)

        assert len(loop._plan_patterns) <= MAX_PLAN_PATTERNS


class TestGetToolReliabilityReport:
    """Test tool reliability reporting."""

    def test_reliability_report_empty(self):
        """Reliability report should be empty initially."""
        loop = LearningLoop()
        report = loop.get_tool_reliability_report()
        assert report == {}

    def test_reliability_report_format(self):
        """Reliability report should have correct format."""
        loop = LearningLoop()
        loop.record_tool_call("test_tool", success=True, duration_s=5.0)
        loop.record_tool_call("test_tool", success=False, error="error")
        report = loop.get_tool_reliability_report()
        assert "test_tool" in report
        assert "success_rate" in report["test_tool"]
        assert report["test_tool"]["success_rate"] == 0.5

    def test_get_unreliable_tools(self):
        """Should identify tools below reliability threshold."""
        loop = LearningLoop()
        for i in range(MIN_EXECUTIONS_FOR_RELIABILITY + 5):
            loop.record_tool_call("unreliable", success=(i < 2), error="fail" if i >= 2 else "")
        unreliable = loop.get_unreliable_tools()
        assert "unreliable" in unreliable


class TestGetCommonFailurePatterns:
    """Test failure pattern extraction."""

    def test_no_failures(self):
        """Should return empty list when no failures."""
        loop = LearningLoop()
        patterns = loop.get_common_failure_patterns()
        assert patterns == []

    def test_failure_pattern_extraction(self):
        """Should extract and categorize failure patterns."""
        loop = LearningLoop()
        loop._failure_log = [
            {"error": "timeout after 30s"},
            {"error": "timeout exceeded"},
            {"error": "connection refused"},
        ]
        patterns = loop.get_common_failure_patterns(limit=3)
        assert len(patterns) > 0

    def test_failure_pattern_counts(self):
        """Patterns should show occurrence counts."""
        loop = LearningLoop()
        for i in range(5):
            loop._failure_log.append({"error": "timeout error", "timestamp": time.time()})
        for i in range(3):
            loop._failure_log.append({"error": "connection error", "timestamp": time.time()})
        patterns = loop.get_common_failure_patterns(limit=5)
        assert len(patterns) > 0


class TestGetPlanSuccessRate:
    """Test plan success rate calculation."""

    def test_success_rate_empty(self):
        """Success rate should handle empty patterns."""
        loop = LearningLoop()
        stats = loop.get_plan_success_rate()
        assert stats["total_plans"] == 0
        assert stats["success_rate"] == 0.0

    def test_success_rate_calculation(self):
        """Success rate should be calculated correctly."""
        loop = LearningLoop()
        plan_success = {
            "plan_id": "s1", "original_request": "req", "goal_summary": "goal",
            "subtasks": [{"title": "t", "status": "completed", "duration_s": 1.0}],
            "completed_at": time.time()
        }
        plan_failure = {
            "plan_id": "f1", "original_request": "req", "goal_summary": "goal",
            "subtasks": [{"title": "t", "status": "failed", "duration_s": 1.0, "error": "fail"}],
            "completed_at": time.time()
        }
        loop.record_plan_outcome(plan_success)
        loop.record_plan_outcome(plan_failure)
        stats = loop.get_plan_success_rate()
        assert stats["total_plans"] == 2
        assert stats["successes"] == 1
        assert stats["failures"] == 1
        assert stats["success_rate"] == 0.5


class TestGetInsightsSummary:
    """Test insights summary generation."""

    def test_insights_empty(self):
        """Insights should handle empty state."""
        loop = LearningLoop()
        insights = loop.get_insights_summary()
        assert "plan_stats" in insights
        assert "unreliable_tools" in insights
        assert insights["plan_stats"]["total_plans"] == 0

    def test_insights_with_data(self):
        """Insights should include all relevant data."""
        loop = LearningLoop()
        loop.record_tool_call("test_tool", success=True, duration_s=5.0)
        loop.record_tool_call("bad_tool", success=False, error="timeout")
        insights = loop.get_insights_summary()
        assert insights["tool_count"] == 2
        assert insights["total_tool_calls"] == 2


class TestGetPlannerContext:
    """Test planner context generation."""

    def test_context_empty(self):
        """Context should be empty when no data."""
        loop = LearningLoop()
        context = loop.get_planner_context()
        assert context == ""

    def test_context_with_unreliable_tools(self):
        """Context should mention unreliable tools."""
        loop = LearningLoop()
        for i in range(MIN_EXECUTIONS_FOR_RELIABILITY + 5):
            loop.record_tool_call("bad_tool", success=(i == 0), error="fail" if i > 0 else "")
        context = loop.get_planner_context()
        assert "UNRELIABLE TOOLS" in context
        assert "bad_tool" in context

    def test_context_with_successful_plans(self):
        """Context should include successful plan examples."""
        loop = LearningLoop()
        plan = {
            "plan_id": "p1", "original_request": "req",
            "goal_summary": "Example task",
            "subtasks": [{"title": "Step 1", "status": "completed", "duration_s": 1.0},
                        {"title": "Step 2", "status": "completed", "duration_s": 1.0}],
            "completed_at": time.time()
        }
        for i in range(5):
            loop.record_plan_outcome(plan)
        context = loop.get_planner_context()
        assert "SUCCESSFUL PLAN EXAMPLES" in context or "PLAN HISTORY" in context

    def test_context_formatting(self):
        """Context should be properly formatted for injection."""
        loop = LearningLoop()
        loop.record_tool_call("test_tool", success=True, duration_s=5.0)
        context = loop.get_planner_context()
        if context:  # May be empty if no significant data
            assert "--- LEARNING CONTEXT" in context
            assert "--- END LEARNING CONTEXT" in context


class TestBackfillFromPlanFiles:
    """Test backfilling learning data from plan files."""

    def test_backfill_no_plans_directory(self, tmp_config):
        """Backfill should handle missing plans directory."""
        loop = LearningLoop()
        loop.backfill_from_plan_files()
        # Should not crash

    def test_backfill_with_plan_files(self, tmp_config):
        """Backfill should load existing plan files."""
        from jarvis.config import settings
        plans_dir = settings.DATA_DIR / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        plan_file = plans_dir / "plan_test.json"
        plan_data = {
            "plan_id": "test_plan",
            "original_request": "test",
            "goal_summary": "test goal",
            "subtasks": [{"title": "step", "status": "completed", "duration_s": 1.0}],
            "completed_at": time.time()
        }
        plan_file.write_text(json.dumps(plan_data))

        loop = LearningLoop()
        loop.initialize()
        loop.backfill_from_plan_files()
        assert len(loop._plan_patterns) > 0


class TestSavePersistence:
    """Test saving and loading learning data."""

    def test_save_tool_stats(self, tmp_config):
        """Tool stats should be persisted to disk."""
        loop = LearningLoop()
        loop.record_tool_call("test_tool", success=True, duration_s=5.0)
        loop._save_tool_stats()
        from jarvis.agent.learning import TOOL_STATS_FILE
        assert TOOL_STATS_FILE.exists()

    def test_load_tool_stats(self, tmp_config):
        """Tool stats should be loaded from disk."""
        loop = LearningLoop()
        loop.record_tool_call("test_tool", success=True, duration_s=5.0)
        loop._save_tool_stats()

        loop2 = LearningLoop()
        loop2._load_tool_stats()
        assert "test_tool" in loop2._tool_stats

    def test_save_all(self, tmp_config):
        """Save all should persist all data."""
        loop = LearningLoop()
        loop.record_tool_call("test_tool", success=True)
        loop.save_all()
        from jarvis.agent.learning import TOOL_STATS_FILE
        assert TOOL_STATS_FILE.exists()
