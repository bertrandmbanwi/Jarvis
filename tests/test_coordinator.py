"""Tests for JARVIS multi-agent coordinator module."""
import pytest

from jarvis.agent.coordinator import (
    AgentType,
    AgentProfile,
    AgentTask,
    classify_subtask,
    classify_subtasks_batch,
    find_parallel_groups,
    AgentCoordinator,
)


class TestAgentType:
    """Test AgentType enumeration."""

    def test_agent_types_exist(self):
        """Should have all agent types defined."""
        assert AgentType.RESEARCHER.value == "researcher"
        assert AgentType.CODER.value == "coder"
        assert AgentType.BROWSER.value == "browser"
        assert AgentType.SYSTEM.value == "system"
        assert AgentType.COMMUNICATOR.value == "communicator"
        assert AgentType.ANALYST.value == "analyst"
        assert AgentType.GENERALIST.value == "generalist"

    def test_agent_type_string_conversion(self):
        """Agent types should convert to strings."""
        assert str(AgentType.RESEARCHER) == "AgentType.RESEARCHER"
        assert AgentType.RESEARCHER.value == "researcher"


class TestAgentProfile:
    """Test the AgentProfile class."""

    def test_profile_creation(self):
        """AgentProfile should initialize correctly."""
        profile = AgentProfile(
            agent_type=AgentType.RESEARCHER,
            display_name="Research Agent",
            system_prompt="You are a researcher",
            tool_names=["search_web", "fetch_page_text"],
            description="Searches and reads web pages"
        )
        assert profile.agent_type == AgentType.RESEARCHER
        assert profile.display_name == "Research Agent"
        assert len(profile.tool_names) == 2

    def test_profile_success_rate_no_tasks(self):
        """Success rate should be 1.0 with no tasks."""
        profile = AgentProfile(
            agent_type=AgentType.CODER,
            display_name="Coder",
            system_prompt="Code",
            tool_names=[]
        )
        assert profile.success_rate == 1.0

    def test_profile_success_rate_calculation(self):
        """Success rate should be calculated correctly."""
        profile = AgentProfile(
            agent_type=AgentType.CODER,
            display_name="Coder",
            system_prompt="Code",
            tool_names=[],
            total_tasks=10,
            successful_tasks=8
        )
        assert profile.success_rate == 0.8

    def test_profile_avg_duration_no_tasks(self):
        """Avg duration should be 0.0 with no tasks."""
        profile = AgentProfile(
            agent_type=AgentType.BROWSER,
            display_name="Browser",
            system_prompt="Browse",
            tool_names=[]
        )
        assert profile.avg_duration_s == 0.0

    def test_profile_avg_duration_calculation(self):
        """Avg duration should be calculated correctly."""
        profile = AgentProfile(
            agent_type=AgentType.BROWSER,
            display_name="Browser",
            system_prompt="Browse",
            tool_names=[],
            total_tasks=5,
            total_duration_s=25.0
        )
        assert profile.avg_duration_s == 5.0

    def test_profile_to_dict(self):
        """Profile should serialize to dict."""
        profile = AgentProfile(
            agent_type=AgentType.RESEARCHER,
            display_name="Research Agent",
            system_prompt="You are a researcher",
            tool_names=["search_web"],
            total_tasks=5,
            successful_tasks=4
        )
        data = profile.to_dict()
        assert data["agent_type"] == "researcher"
        assert data["display_name"] == "Research Agent"
        assert data["success_rate"] == 0.8


class TestAgentTask:
    """Test the AgentTask class."""

    def test_task_creation(self):
        """AgentTask should initialize correctly."""
        task = AgentTask(
            subtask_id="st_001",
            agent_type=AgentType.RESEARCHER,
            description="Search for information"
        )
        assert task.subtask_id == "st_001"
        assert task.agent_type == AgentType.RESEARCHER
        assert task.status == "pending"

    def test_task_with_dependencies(self):
        """Task should track dependencies."""
        task = AgentTask(
            subtask_id="st_002",
            agent_type=AgentType.ANALYST,
            description="Analyze results",
            depends_on=["st_001"]
        )
        assert "st_001" in task.depends_on


class TestClassifySubtask:
    """Test subtask classification."""

    def test_classify_researcher_task(self):
        """Should classify research tasks."""
        agent_type = classify_subtask("search the web for information")
        assert agent_type == AgentType.RESEARCHER

    def test_classify_coder_task(self):
        """Should classify coding tasks."""
        agent_type = classify_subtask("write Python code to process the data")
        assert agent_type == AgentType.CODER

    def test_classify_browser_task(self):
        """Should classify browser tasks."""
        agent_type = classify_subtask("navigate to the website and click the button")
        assert agent_type == AgentType.BROWSER

    def test_classify_system_task(self):
        """Should classify system control tasks."""
        agent_type = classify_subtask("open the application and set the volume")
        assert agent_type == AgentType.SYSTEM

    def test_classify_communicator_task(self):
        """Should classify communication tasks."""
        agent_type = classify_subtask("send an email to alice@example.com and schedule a meeting")
        assert agent_type == AgentType.COMMUNICATOR

    def test_classify_analyst_task(self):
        """Should classify analyst tasks."""
        agent_type = classify_subtask("analyze the data and compare the results")
        assert agent_type == AgentType.ANALYST

    def test_classify_ambiguous_defaults_to_generalist(self):
        """Ambiguous task should default to generalist."""
        agent_type = classify_subtask("do something useful")
        assert agent_type == AgentType.GENERALIST

    def test_classify_multiple_keywords_highest_score(self):
        """Should pick agent type with highest keyword score."""
        # Multiple research keywords
        agent_type = classify_subtask(
            "search Google for information and look up data and research"
        )
        assert agent_type == AgentType.RESEARCHER

    def test_classify_short_description(self):
        """Should handle short descriptions."""
        agent_type = classify_subtask("search")
        assert agent_type == AgentType.RESEARCHER


class TestClassifySubtasksBatch:
    """Test batch subtask classification."""

    def test_classify_batch_mixed_types(self):
        """Should classify batch of mixed task types."""
        tasks = [
            "search for information",
            "write Python code",
            "navigate to website",
        ]
        results = classify_subtasks_batch(tasks)
        assert len(results) == 3
        assert AgentType.RESEARCHER in results
        assert AgentType.CODER in results
        assert AgentType.BROWSER in results

    def test_classify_batch_empty(self):
        """Empty batch should return empty list."""
        results = classify_subtasks_batch([])
        assert results == []

    def test_classify_batch_single_item(self):
        """Single item batch should work."""
        results = classify_subtasks_batch(["search for data"])
        assert len(results) == 1
        assert results[0] == AgentType.RESEARCHER


class TestFindParallelGroups:
    """Test parallel group scheduling."""

    def test_no_dependencies_all_parallel(self):
        """Tasks with no dependencies should all be parallel."""
        subtasks = [
            {"id": "st_1", "depends_on": []},
            {"id": "st_2", "depends_on": []},
            {"id": "st_3", "depends_on": []},
        ]
        groups = find_parallel_groups(subtasks)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_linear_dependency_chain(self):
        """Linear dependencies should create sequential groups."""
        subtasks = [
            {"id": "st_1", "depends_on": []},
            {"id": "st_2", "depends_on": ["st_1"]},
            {"id": "st_3", "depends_on": ["st_2"]},
        ]
        groups = find_parallel_groups(subtasks)
        assert len(groups) == 3
        # Each group should have exactly 1 task
        assert all(len(g) == 1 for g in groups)

    def test_mixed_dependencies(self):
        """Mixed dependencies should create appropriate groups."""
        subtasks = [
            {"id": "st_1", "depends_on": []},
            {"id": "st_2", "depends_on": []},
            {"id": "st_3", "depends_on": ["st_1", "st_2"]},
            {"id": "st_4", "depends_on": ["st_3"]},
        ]
        groups = find_parallel_groups(subtasks)
        assert len(groups) == 3
        # First group: st_1, st_2 (parallel)
        assert len(groups[0]) == 2
        # Second group: st_3
        assert len(groups[1]) == 1
        # Third group: st_4
        assert len(groups[2]) == 1

    def test_empty_subtasks(self):
        """Empty subtask list should return empty groups."""
        groups = find_parallel_groups([])
        assert groups == []

    def test_missing_dependency_handled(self):
        """Missing dependency should be handled gracefully."""
        subtasks = [
            {"id": "st_1", "depends_on": ["st_nonexistent"]},
            {"id": "st_2", "depends_on": []},
        ]
        groups = find_parallel_groups(subtasks)
        # Should complete st_2, then st_1 (with warning about deadlock)
        assert len(groups) > 0

    def test_no_dependency_ids_uses_indices(self):
        """Tasks without IDs should use indices."""
        subtasks = [
            {"depends_on": []},
            {"depends_on": []},
            {"depends_on": []},
        ]
        groups = find_parallel_groups(subtasks)
        # Should still work with index-based IDs
        assert len(groups) == 1
        assert len(groups[0]) == 3


class TestAgentCoordinator:
    """Test the AgentCoordinator class."""

    def test_coordinator_creation(self):
        """AgentCoordinator should initialize with agent profiles."""
        coord = AgentCoordinator()
        assert len(coord.profiles) == 7  # All 7 agent types
        assert AgentType.RESEARCHER in coord.profiles
        assert AgentType.CODER in coord.profiles

    def test_profiles_have_correct_properties(self):
        """Profiles should have all required properties."""
        coord = AgentCoordinator()
        for agent_type, profile in coord.profiles.items():
            assert profile.agent_type == agent_type
            assert profile.display_name
            assert profile.system_prompt
            assert isinstance(profile.tool_names, list)

    def test_researcher_profile_has_web_tools(self):
        """Researcher profile should have web search tools."""
        coord = AgentCoordinator()
        researcher = coord.profiles[AgentType.RESEARCHER]
        assert "search_web" in researcher.tool_names
        assert "fetch_page_text" in researcher.tool_names

    def test_coder_profile_has_code_tools(self):
        """Coder profile should have code execution tools."""
        coord = AgentCoordinator()
        coder = coord.profiles[AgentType.CODER]
        assert "run_command" in coder.tool_names
        assert "run_claude_code" in coder.tool_names

    def test_browser_profile_has_browser_tools(self):
        """Browser profile should have browser interaction tools."""
        coord = AgentCoordinator()
        browser = coord.profiles[AgentType.BROWSER]
        assert "chrome_navigate" in browser.tool_names
        assert "browser_navigate" in browser.tool_names

    def test_system_profile_has_system_tools(self):
        """System profile should have system control tools."""
        coord = AgentCoordinator()
        system = coord.profiles[AgentType.SYSTEM]
        assert "open_application" in system.tool_names
        assert "set_volume" in system.tool_names

    def test_communicator_profile_has_communication_tools(self):
        """Communicator profile should have email/calendar tools."""
        coord = AgentCoordinator()
        comm = coord.profiles[AgentType.COMMUNICATOR]
        assert "send_email" in comm.tool_names
        assert "get_upcoming_events" in comm.tool_names

    def test_analyst_profile_has_reasoning_tools(self):
        """Analyst profile should have analytical tools."""
        coord = AgentCoordinator()
        analyst = coord.profiles[AgentType.ANALYST]
        assert "capture_screen" in analyst.tool_names
        assert "read_file" in analyst.tool_names

    def test_generalist_has_empty_tool_list(self):
        """Generalist profile should have empty tool list (uses all)."""
        coord = AgentCoordinator()
        generalist = coord.profiles[AgentType.GENERALIST]
        assert len(generalist.tool_names) == 0

    def test_profiles_have_system_prompts(self):
        """All profiles should have meaningful system prompts."""
        coord = AgentCoordinator()
        for agent_type, profile in coord.profiles.items():
            assert len(profile.system_prompt) > 50
            assert "Address" in profile.system_prompt or "specialty" in profile.system_prompt


class TestCoordinatorIntegration:
    """Integration tests for coordinator."""

    def test_classify_and_route_research_task(self):
        """Full workflow: classify research task."""
        description = "search for information about machine learning on the web"
        agent_type = classify_subtask(description)
        assert agent_type == AgentType.RESEARCHER

    def test_classify_and_route_coding_task(self):
        """Full workflow: classify coding task."""
        description = "write code to implement a Python function that processes the CSV file"
        agent_type = classify_subtask(description)
        assert agent_type == AgentType.CODER

    def test_complex_plan_with_dependencies(self):
        """Full workflow: complex plan with mixed dependencies."""
        subtasks = [
            {"id": "search", "description": "search the web", "depends_on": []},
            {"id": "code", "description": "write code", "depends_on": []},
            {"id": "analyze", "description": "analyze results", "depends_on": ["search", "code"]},
        ]
        groups = find_parallel_groups(subtasks)
        agent_types = [
            classify_subtask(s["description"])
            for s in subtasks
        ]
        assert AgentType.RESEARCHER in agent_types
        assert AgentType.CODER in agent_types
        assert len(groups) > 1  # Should have parallel groups

    def test_routing_keywords_coverage(self):
        """All agent types should have routing keywords."""
        coord = AgentCoordinator()
        from jarvis.agent.coordinator import _ROUTING_KEYWORDS
        for agent_type in AgentType:
            if agent_type != AgentType.GENERALIST:
                assert agent_type in _ROUTING_KEYWORDS
                assert len(_ROUTING_KEYWORDS[agent_type]) > 0
