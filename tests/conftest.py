"""Shared pytest fixtures for JARVIS tests."""
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def tmp_data_dir():
    """Create a temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_llm():
    """Create a mock LLM for testing."""
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value='{"needs_decomposition": false}')
    return llm


@pytest.fixture
def sample_plan():
    """Create a sample task plan for testing."""
    return {
        "plan_id": "test_plan_001",
        "original_request": "Search for Python documentation and create a summary",
        "goal_summary": "Research and summarize Python docs",
        "created_at": 1704067200.0,
        "completed_at": 1704070800.0,
        "status": "completed",
        "subtasks": [
            {
                "id": "st_001",
                "title": "Search for Python documentation",
                "description": "Search the web for official Python documentation",
                "status": "completed",
                "duration_s": 5.2,
                "result": "Found Python 3.11 official docs",
            },
            {
                "id": "st_002",
                "title": "Summarize key concepts",
                "description": "Create a summary of Python basics",
                "status": "completed",
                "duration_s": 3.1,
                "result": "Summary created",
            },
        ],
    }


@pytest.fixture
def sample_tool_stats():
    """Create sample tool statistics for testing."""
    return {
        "search_web": {
            "name": "search_web",
            "total_calls": 10,
            "successes": 9,
            "failures": 1,
            "total_duration_s": 45.5,
            "success_rate": 0.9,
            "avg_duration_s": 5.06,
            "last_used": 1704070800.0,
            "is_reliable": True,
            "failure_reasons": ["timeout on request"],
        },
        "read_file": {
            "name": "read_file",
            "total_calls": 20,
            "successes": 15,
            "failures": 5,
            "total_duration_s": 12.3,
            "success_rate": 0.75,
            "avg_duration_s": 0.82,
            "last_used": 1704070700.0,
            "is_reliable": False,
            "failure_reasons": ["file not found", "permission denied"],
        },
    }


@pytest.fixture
def tmp_config(tmp_data_dir, monkeypatch):
    """Temporarily patch settings to use a temporary data directory."""
    from jarvis.config import settings

    monkeypatch.setattr(settings, "DATA_DIR", tmp_data_dir)
    return settings
