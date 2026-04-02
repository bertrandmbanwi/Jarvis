"""Tests for JARVIS task planner module."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.agent.planner import (
    TaskPlanner,
    needs_decomposition_heuristic,
    _has_sequence_markers,
    _count_action_verbs,
    _has_compound_actions,
)


class TestDecompositionHeuristic:
    """Test the needs_decomposition_heuristic function."""

    def test_simple_single_word_request(self):
        """Very short requests should not need decomposition."""
        assert needs_decomposition_heuristic("hello") is False

    def test_short_single_action_request(self):
        """Short requests with single action should not decompose."""
        assert needs_decomposition_heuristic("search for Python") is False

    def test_explicit_sequencing_word_then(self):
        """Requests with 'then' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "search for Python documentation, then create a summary"
        )
        assert result is True

    def test_explicit_sequencing_word_after_that(self):
        """Requests with 'after that' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "find information, after that write a report"
        )
        assert result is True

    def test_explicit_sequencing_word_first(self):
        """Requests with 'first' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "first search the web, then summarize the results"
        )
        assert result is True

    def test_explicit_sequencing_word_finally(self):
        """Requests with 'finally' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "search, read pages, finally compile all findings"
        )
        assert result is True

    def test_explicit_sequencing_word_once(self):
        """Requests with 'once' + completion should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "install dependencies, once that's done run tests"
        )
        assert result is True

    def test_explicit_sequencing_word_step(self):
        """Requests with 'step 1', 'step 2' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "step 1: search for data, step 2: analyze it"
        )
        assert result is True

    def test_three_or_more_action_verbs(self):
        """Requests with 3+ distinct action verbs should decompose."""
        result = needs_decomposition_heuristic(
            "search for information, read the page, and send me an email about it"
        )
        assert result is True

    def test_compound_actions_with_and(self):
        """Compound actions with 'and' and 2+ verbs should trigger LLM check."""
        result = needs_decomposition_heuristic(
            "search for information and create a document"
        )
        assert result is None  # Ambiguous, needs LLM decision

    def test_single_verb_no_sequence(self):
        """Single verb without sequence markers should not decompose."""
        result = needs_decomposition_heuristic(
            "please search for information about machine learning"
        )
        assert result is False

    def test_two_verbs_no_sequence(self):
        """Two verbs without explicit compound or sequence should return None (ambiguous)."""
        # Must be >= 30 chars to pass length check, have 2 verbs with compound action
        result = needs_decomposition_heuristic("search the web and read the documentation for me")
        assert result is None  # Ambiguous: compound with 2 verbs

    def test_minimum_length_check(self):
        """Text shorter than 30 chars should not decompose."""
        assert needs_decomposition_heuristic("search then read") is False

    def test_followed_by_keyword(self):
        """Requests with 'followed by' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "open the website, followed by clicking the button"
        )
        assert result is True

    def test_before_you_keyword(self):
        """Requests with 'before you' should be marked for decomposition."""
        result = needs_decomposition_heuristic(
            "check permissions before you write the file"
        )
        assert result is True


class TestSequenceMarkers:
    """Test the _has_sequence_markers function."""

    def test_no_sequence_markers(self):
        """Text without sequence markers should return False."""
        assert _has_sequence_markers("this is a simple request") is False

    def test_then_marker(self):
        """Text containing 'then' should return True."""
        assert _has_sequence_markers("first do this, then do that") is True

    def test_after_that_marker(self):
        """Text containing 'after that' should return True."""
        assert _has_sequence_markers("do X, after that do Y") is True

    def test_case_insensitive(self):
        """Sequence markers should be case-insensitive."""
        assert _has_sequence_markers("THEN do something") is True
        assert _has_sequence_markers("After That comes next") is True


class TestActionVerbs:
    """Test the _count_action_verbs function."""

    def test_no_action_verbs(self):
        """Text with no action verbs should return 0."""
        assert _count_action_verbs("this is a description") == 0

    def test_single_action_verb(self):
        """Text with one action verb should return 1."""
        assert _count_action_verbs("search for information") == 1

    def test_multiple_action_verbs(self):
        """Text with multiple distinct action verbs should count them."""
        count = _count_action_verbs("search for data, create a document, and send an email")
        assert count >= 2  # At least search, create, send

    def test_duplicate_action_verbs_counted_once(self):
        """Duplicate action verbs (same root) should be counted once."""
        count = _count_action_verbs("search Google, then search bing")
        assert count == 1  # Only one 'search' root


class TestCompoundActions:
    """Test the _has_compound_actions function."""

    def test_no_compound_actions(self):
        """Single action should return False."""
        assert _has_compound_actions("search for information") is False

    def test_compound_with_and(self):
        """Multiple actions joined by 'and' should return True."""
        result = _has_compound_actions("search for data and create a summary")
        assert result is True

    def test_compound_with_then(self):
        """Multiple actions joined by 'then' should return True."""
        result = _has_compound_actions("read the file, then modify it")
        assert result is True

    def test_compound_with_comma(self):
        """Multiple actions joined by comma should return True."""
        result = _has_compound_actions("open the app, open the file, close the dialog")
        assert result is True

    def test_single_action_with_and(self):
        """Single action with 'and' modifiers should return False."""
        assert _has_compound_actions("search for Python and Django") is False


class TestTaskPlannerCreation:
    """Test TaskPlanner initialization and basic methods."""

    def test_planner_initialization(self):
        """TaskPlanner should initialize without errors."""
        planner = TaskPlanner()
        assert planner is not None
        assert planner.llm is None

    def test_planner_with_llm(self, mock_llm):
        """TaskPlanner should accept an LLM instance."""
        planner = TaskPlanner(llm=mock_llm)
        assert planner.llm is mock_llm

    def test_get_active_plan_none(self):
        """get_active_plan should return None when no plan is active."""
        planner = TaskPlanner()
        assert planner.get_active_plan() is None

    def test_get_plan_status_no_plan(self):
        """get_plan_status should return status when no plan exists."""
        planner = TaskPlanner()
        status = planner.get_plan_status()
        assert isinstance(status, str)


class TestPlannerShouldDecompose:
    """Test the should_decompose method."""

    @pytest.mark.asyncio
    async def test_should_decompose_simple_request(self, mock_llm):
        """Simple requests should not require decomposition."""
        planner = TaskPlanner(llm=mock_llm)
        result = await planner.should_decompose("search for information")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_decompose_complex_request(self, mock_llm):
        """Complex requests with sequence markers should require decomposition."""
        planner = TaskPlanner(llm=mock_llm)
        result = await planner.should_decompose(
            "search for information, then create a summary, finally send an email"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_should_decompose_no_llm(self):
        """should_decompose should default to False when no LLM and heuristic is ambiguous."""
        planner = TaskPlanner(llm=None)
        # Use input that is ambiguous (compound actions, 2 verbs, no sequence markers)
        result = await planner.should_decompose("search the web and read the full documentation for me")
        # Heuristic returns None (ambiguous), no LLM available, defaults to False
        assert result is False

    @pytest.mark.asyncio
    async def test_should_decompose_llm_fallback(self, mock_llm):
        """should_decompose should use LLM for ambiguous cases."""
        mock_llm.chat.return_value = "complex"
        planner = TaskPlanner(llm=mock_llm)
        # Use input that is ambiguous (compound actions, 2 verbs, no sequence markers)
        result = await planner.should_decompose("search the web and read the full documentation for me")
        assert result is True


class TestCreatePlan:
    """Test the create_plan method."""

    @pytest.mark.asyncio
    async def test_create_plan_no_llm(self):
        """create_plan should return None without LLM."""
        planner = TaskPlanner(llm=None)
        plan = await planner.create_plan("search for Python documentation")
        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_with_valid_response(self, mock_llm):
        """create_plan should parse valid LLM response."""
        mock_llm.chat.return_value = json.dumps({
            "needs_decomposition": True,
            "goal_summary": "Search and summarize Python docs",
            "subtasks": [
                {"title": "Search", "description": "Search for Python docs"},
                {"title": "Summarize", "description": "Summarize findings"},
            ]
        })
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("search for Python docs and summarize")
        assert plan is not None
        assert len(plan.subtasks) == 2

    @pytest.mark.asyncio
    async def test_create_plan_json_with_markdown_fence(self, mock_llm):
        """create_plan should handle JSON with markdown code fences."""
        mock_llm.chat.return_value = """```json
{
  "needs_decomposition": true,
  "goal_summary": "Test goal",
  "subtasks": [
    {"title": "Step 1", "description": "Do something"}
  ]
}
```"""
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("complex task")
        assert plan is not None

    @pytest.mark.asyncio
    async def test_create_plan_no_decomposition_needed(self, mock_llm):
        """create_plan should return None if no decomposition is needed."""
        mock_llm.chat.return_value = json.dumps({
            "needs_decomposition": False,
            "reason": "Single action request"
        })
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("simple request")
        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_caps_subtasks(self, mock_llm):
        """create_plan should cap subtasks at MAX_SUBTASKS."""
        many_subtasks = [
            {"title": f"Step {i}", "description": f"Do step {i}"}
            for i in range(15)
        ]
        mock_llm.chat.return_value = json.dumps({
            "needs_decomposition": True,
            "goal_summary": "Long plan",
            "subtasks": many_subtasks
        })
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("complex task with many steps")
        assert plan is not None
        assert len(plan.subtasks) <= 8  # MAX_SUBTASKS

    @pytest.mark.asyncio
    async def test_create_plan_invalid_json_response(self, mock_llm):
        """create_plan should handle invalid JSON gracefully."""
        mock_llm.chat.return_value = "This is not JSON at all"
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("search then read then summarize")
        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_missing_subtasks(self, mock_llm):
        """create_plan should return None if subtasks are missing."""
        mock_llm.chat.return_value = json.dumps({
            "needs_decomposition": True,
            "goal_summary": "Goal",
            "subtasks": []
        })
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("complex task")
        assert plan is None


class TestParseplanResponse:
    """Test the _parse_plan_response method."""

    def test_parse_valid_json(self):
        """Should parse valid JSON."""
        planner = TaskPlanner()
        response = '{"needs_decomposition": true, "goal_summary": "test"}'
        result = planner._parse_plan_response(response)
        assert result is not None
        assert result["needs_decomposition"] is True

    def test_parse_json_with_markdown_fence(self):
        """Should strip markdown code fences."""
        planner = TaskPlanner()
        response = """```json
{"needs_decomposition": true}
```"""
        result = planner._parse_plan_response(response)
        assert result is not None
        assert result["needs_decomposition"] is True

    def test_parse_json_with_backticks_no_language(self):
        """Should handle backticks without language specification."""
        planner = TaskPlanner()
        response = """```
{"needs_decomposition": false}
```"""
        result = planner._parse_plan_response(response)
        assert result is not None

    def test_parse_json_with_leading_text(self):
        """Should extract JSON from text with leading content."""
        planner = TaskPlanner()
        response = 'Some text {"needs_decomposition": true} trailing text'
        result = planner._parse_plan_response(response)
        assert result is not None
        assert result["needs_decomposition"] is True

    def test_parse_invalid_json(self):
        """Should return None for invalid JSON."""
        planner = TaskPlanner()
        response = "This is not JSON"
        result = planner._parse_plan_response(response)
        assert result is None

    def test_parse_empty_response(self):
        """Should handle empty response."""
        planner = TaskPlanner()
        result = planner._parse_plan_response("")
        assert result is None

    def test_parse_malformed_json(self):
        """Should return None for malformed JSON."""
        planner = TaskPlanner()
        response = '{"needs_decomposition": true, "incomplete": '
        result = planner._parse_plan_response(response)
        assert result is None


class TestPlannerEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_should_decompose_llm_error(self, mock_llm):
        """should_decompose should handle LLM errors gracefully."""
        mock_llm.chat.side_effect = Exception("LLM error")
        planner = TaskPlanner(llm=mock_llm)
        result = await planner.should_decompose("search and read and write")
        assert result is False  # Should default to False on error

    @pytest.mark.asyncio
    async def test_create_plan_llm_error(self, mock_llm):
        """create_plan should handle LLM errors gracefully."""
        mock_llm.chat.side_effect = Exception("LLM error")
        planner = TaskPlanner(llm=mock_llm)
        plan = await planner.create_plan("search then read")
        assert plan is None

    def test_heuristic_very_long_text(self):
        """Heuristic should handle very long text."""
        long_text = "search " * 100 + "for information"
        result = needs_decomposition_heuristic(long_text)
        assert result is not None  # Should not crash

    def test_heuristic_special_characters(self):
        """Heuristic should handle special characters."""
        text = "search for @#$% & find ^&* then do something"
        result = needs_decomposition_heuristic(text)
        assert result is not None  # Should not crash

    def test_heuristic_unicode_text(self):
        """Heuristic should handle unicode characters."""
        text = "search for 信息 and 创建 a summary"
        result = needs_decomposition_heuristic(text)
        assert result is not None  # Should not crash
