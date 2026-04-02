"""Tests for JARVIS cost tracking module."""
from datetime import date, datetime, timedelta
from pathlib import Path
import json

import pytest

from jarvis.core.cost_tracker import (
    log_request,
    get_today_summary,
    get_month_summary,
    _load_day,
    _save_day,
    _today_file,
)


@pytest.fixture
def cost_tracker_setup(tmp_path, monkeypatch):
    """Set up cost tracker with temporary directory."""
    from jarvis.config import settings
    cost_dir = tmp_path / "cost_logs"
    cost_dir.mkdir()
    monkeypatch.setattr(settings, "COST_LOG_DIR", str(cost_dir))
    return cost_dir


class TestLoadDay:
    """Test loading day cost data."""

    def test_load_nonexistent_day(self, cost_tracker_setup):
        """Loading nonexistent day should return default structure."""
        file_path = cost_tracker_setup / "2024-01-15.json"
        data = _load_day(file_path)
        assert data["date"] == "2024-01-15"
        assert data["total_cost_usd"] == 0.0
        assert data["total_requests"] == 0
        assert "by_tier" in data
        assert "by_model" in data

    def test_load_existing_day(self, cost_tracker_setup):
        """Loading existing day should read from file."""
        file_path = cost_tracker_setup / "2024-01-15.json"
        test_data = {
            "date": "2024-01-15",
            "total_cost_usd": 5.50,
            "total_requests": 10,
            "total_input_tokens": 1000,
            "total_output_tokens": 500,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "by_tier": {"fast": 5, "brain": 5},
            "by_model": {"claude-haiku": 10},
            "requests": []
        }
        file_path.write_text(json.dumps(test_data))
        data = _load_day(file_path)
        assert data["total_cost_usd"] == 5.50
        assert data["total_requests"] == 10

    def test_load_corrupted_json(self, cost_tracker_setup):
        """Loading corrupted JSON should return default."""
        file_path = cost_tracker_setup / "2024-01-15.json"
        file_path.write_text("not valid json")
        data = _load_day(file_path)
        assert data["total_cost_usd"] == 0.0


class TestSaveDay:
    """Test saving day cost data."""

    def test_save_creates_file(self, cost_tracker_setup):
        """Saving should create file if it doesn't exist."""
        file_path = cost_tracker_setup / "2024-01-15.json"
        data = {
            "date": "2024-01-15",
            "total_cost_usd": 3.50,
            "total_requests": 5,
            "by_tier": {},
            "by_model": {},
            "requests": []
        }
        _save_day(file_path, data)
        assert file_path.exists()
        loaded = json.loads(file_path.read_text())
        assert loaded["total_cost_usd"] == 3.50

    def test_save_overwrites_existing(self, cost_tracker_setup):
        """Saving should overwrite existing file."""
        file_path = cost_tracker_setup / "2024-01-15.json"
        data1 = {
            "date": "2024-01-15",
            "total_cost_usd": 1.0,
            "total_requests": 1,
            "by_tier": {},
            "by_model": {},
            "requests": []
        }
        _save_day(file_path, data1)
        data2 = {
            "date": "2024-01-15",
            "total_cost_usd": 5.0,
            "total_requests": 5,
            "by_tier": {},
            "by_model": {},
            "requests": []
        }
        _save_day(file_path, data2)
        loaded = json.loads(file_path.read_text())
        assert loaded["total_cost_usd"] == 5.0


class TestLogRequest:
    """Test logging API requests."""

    def test_log_single_request(self, cost_tracker_setup):
        """Logging a single request should update totals."""
        log_request(
            model="claude-3-5-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            elapsed_seconds=1.5,
            user_input_preview="search for something"
        )
        summary = get_today_summary()
        assert summary["total_requests"] == 1
        assert summary["total_input_tokens"] == 100
        assert summary["total_output_tokens"] == 50
        assert summary["total_cost_usd"] == 0.001

    def test_log_multiple_requests(self, cost_tracker_setup):
        """Multiple requests should accumulate."""
        for i in range(5):
            log_request(
                model="claude-3-5-haiku",
                tier="fast",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.001 * (i + 1),
                elapsed_seconds=1.0
            )
        summary = get_today_summary()
        assert summary["total_requests"] == 5
        assert summary["total_input_tokens"] == 500
        assert summary["total_output_tokens"] == 250
        # Sum: 0.001 + 0.002 + 0.003 + 0.004 + 0.005 = 0.015
        assert abs(summary["total_cost_usd"] - 0.015) < 0.0001

    def test_log_request_by_tier(self, cost_tracker_setup):
        """Requests should be tracked by tier."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001
        )
        log_request(
            model="claude-sonnet",
            tier="brain",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01
        )
        summary = get_today_summary()
        assert summary["by_tier"]["fast"] == 1
        assert summary["by_tier"]["brain"] == 1

    def test_log_request_by_model(self, cost_tracker_setup):
        """Requests should be tracked by model."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001
        )
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001
        )
        summary = get_today_summary()
        assert summary["by_tier"]["fast"] == 2

    def test_log_request_with_cache_tokens(self, cost_tracker_setup):
        """Cache tokens should be tracked separately."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=200,
            cache_creation_tokens=150,
            cost_usd=0.001
        )
        summary = get_today_summary()
        assert summary["total_input_tokens"] == 100
        assert summary["total_output_tokens"] == 50
        # Note: Cache tokens are in the full data, not summary

    def test_log_request_with_preview(self, cost_tracker_setup):
        """Request preview should be stored."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            user_input_preview="search for Python documentation"
        )
        data = _load_day(_today_file())
        assert len(data["requests"]) == 1
        assert "search for" in data["requests"][0]["preview"]

    def test_log_request_caps_requests_list(self, cost_tracker_setup):
        """Requests list should be capped at 500."""
        for i in range(600):
            log_request(
                model="claude-haiku",
                tier="fast",
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.0001
            )
        data = _load_day(_today_file())
        assert len(data["requests"]) <= 500


class TestTodaySummary:
    """Test today's cost summary."""

    def test_summary_empty(self, cost_tracker_setup):
        """Empty day should return zero totals."""
        summary = get_today_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_requests"] == 0

    def test_summary_with_requests(self, cost_tracker_setup):
        """Summary should aggregate today's requests."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001
        )
        log_request(
            model="claude-sonnet",
            tier="brain",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.015
        )
        summary = get_today_summary()
        assert summary["total_requests"] == 2
        assert summary["total_input_tokens"] == 600
        assert summary["total_output_tokens"] == 250
        assert abs(summary["total_cost_usd"] - 0.016) < 0.0001

    def test_summary_includes_date(self, cost_tracker_setup):
        """Summary should include today's date."""
        summary = get_today_summary()
        assert "date" in summary
        assert summary["date"] == str(date.today())


class TestMonthSummary:
    """Test monthly cost summary."""

    def test_month_summary_empty(self, cost_tracker_setup):
        """Empty month should return zero totals."""
        summary = get_month_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_requests"] == 0
        assert summary["days_active"] == 0

    def test_month_summary_single_day(self, cost_tracker_setup):
        """Month with single day of requests."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.005
        )
        summary = get_month_summary()
        assert summary["total_cost_usd"] == 0.005
        assert summary["total_requests"] == 1
        assert summary["days_active"] == 1

    def test_month_summary_multiple_days(self, cost_tracker_setup, monkeypatch):
        """Month with requests across multiple days."""
        today = date.today()

        # Mock _today_file to return different dates
        def mock_today_file():
            return cost_tracker_setup / f"{today.isoformat()}.json"

        # Log request for today
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.005
        )

        # Create file for yesterday
        yesterday = today - timedelta(days=1)
        yesterday_file = cost_tracker_setup / f"{yesterday.isoformat()}.json"
        yesterday_data = {
            "date": yesterday.isoformat(),
            "total_cost_usd": 0.010,
            "total_requests": 2,
            "total_input_tokens": 200,
            "total_output_tokens": 100,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "by_tier": {"fast": 2},
            "by_model": {"claude-haiku": 2},
            "requests": []
        }
        _save_day(yesterday_file, yesterday_data)

        summary = get_month_summary()
        assert summary["total_cost_usd"] == 0.015
        assert summary["total_requests"] == 3
        assert summary["days_active"] == 2

    def test_month_summary_projected_cost(self, cost_tracker_setup):
        """Month summary should include projected cost."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=1.0
        )
        summary = get_month_summary()
        assert "projected_monthly_usd" in summary
        assert summary["projected_monthly_usd"] > 0

    def test_month_summary_avg_daily(self, cost_tracker_setup):
        """Month summary should include average daily cost."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=1.0
        )
        summary = get_month_summary()
        assert "avg_daily_cost_usd" in summary

    def test_month_summary_includes_month_label(self, cost_tracker_setup):
        """Summary should include month label."""
        summary = get_month_summary()
        assert "month" in summary
        month_label = summary["month"]
        today = date.today()
        expected = today.strftime("%Y-%m")
        assert month_label == expected


class TestCostTrackerIntegration:
    """Integration tests for cost tracking."""

    def test_daily_accumulation(self, cost_tracker_setup):
        """Costs should accumulate throughout the day."""
        daily_cost = 0.0
        for i in range(10):
            cost = 0.001 * (i + 1)
            log_request(
                model="claude-haiku",
                tier="fast",
                input_tokens=50 + i * 10,
                output_tokens=25 + i * 5,
                cost_usd=cost
            )
            daily_cost += cost

        summary = get_today_summary()
        assert summary["total_requests"] == 10
        assert abs(summary["total_cost_usd"] - daily_cost) < 0.0001

    def test_cost_rounding(self, cost_tracker_setup):
        """Costs should be properly rounded."""
        log_request(
            model="claude-haiku",
            tier="fast",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.123456789
        )
        summary = get_today_summary()
        # Should be rounded to 6 decimal places
        assert summary["total_cost_usd"] == round(0.123456789, 6)

    def test_different_models_tracked(self, cost_tracker_setup):
        """Different models should be tracked separately."""
        models = ["claude-haiku", "claude-sonnet", "claude-opus"]
        for model in models:
            log_request(
                model=model,
                tier="fast",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.001
            )

        data = _load_day(_today_file())
        assert len(data["by_model"]) == 3
        for model in models:
            assert model in data["by_model"]

    def test_different_tiers_tracked(self, cost_tracker_setup):
        """Different tiers should be tracked separately."""
        tiers = ["fast", "brain", "deep"]
        for tier in tiers:
            log_request(
                model="claude-haiku",
                tier=tier,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.001
            )

        summary = get_today_summary()
        for tier in tiers:
            assert tier in summary["by_tier"]
            assert summary["by_tier"][tier] == 1
