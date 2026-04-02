"""Persistent logging of API usage costs to JSON files."""
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.cost_tracker")

def _cost_log_dir() -> Path:
    """Get the cost log directory from settings (evaluated at call time for testability)."""
    return Path(settings.COST_LOG_DIR)


def _today_file() -> Path:
    """Get path to today's cost log file."""

    return _cost_log_dir() / f"{date.today().isoformat()}.json"


def _load_day(file_path: Path) -> dict:
    """Load a day's cost data from file."""

    if file_path.exists():
        try:
            return json.loads(file_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read cost log %s: %s", file_path, e)
    return {
        "date": file_path.stem,
        "total_cost_usd": 0.0,
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "by_tier": {"fast": 0, "brain": 0, "deep": 0, "ollama": 0},
        "by_model": {},
        "requests": [],
    }


def _save_day(file_path: Path, data: dict):
    """Save a day's cost data to disk."""

    try:
        file_path.write_text(json.dumps(data, indent=2))
    except OSError as e:
        logger.error("Failed to write cost log %s: %s", file_path, e)


def log_request(
    model: str,
    tier: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cost_usd: float = 0.0,
    elapsed_seconds: float = 0.0,
    user_input_preview: str = "",
):
    """Log a single API request to the daily cost file."""
    log_file = _today_file()
    data = _load_day(log_file)

    data["total_cost_usd"] = round(data["total_cost_usd"] + cost_usd, 6)
    data["total_requests"] += 1
    data["total_input_tokens"] += input_tokens
    data["total_output_tokens"] += output_tokens
    data["total_cache_read_tokens"] += cache_read_tokens
    data["total_cache_creation_tokens"] += cache_creation_tokens

    data["by_tier"][tier] = data["by_tier"].get(tier, 0) + 1

    data["by_model"][model] = data["by_model"].get(model, 0) + 1

    data["requests"].append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "tier": tier,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read": cache_read_tokens,
        "cache_write": cache_creation_tokens,
        "cost_usd": round(cost_usd, 6),
        "elapsed_s": round(elapsed_seconds, 2),
        "preview": user_input_preview[:80],
    })
    if len(data["requests"]) > 500:
        data["requests"] = data["requests"][-500:]
    _save_day(log_file, data)


def get_today_summary() -> dict:
    """Get today's cost summary."""
    data = _load_day(_today_file())
    return {
        "date": data["date"],
        "total_cost_usd": data["total_cost_usd"],
        "total_requests": data["total_requests"],
        "total_input_tokens": data["total_input_tokens"],
        "total_output_tokens": data["total_output_tokens"],
        "by_tier": data["by_tier"],
    }


def get_month_summary() -> dict:
    """Get current month's cost summary."""
    today = date.today()
    month_prefix = today.strftime("%Y-%m")
    total_cost = 0.0
    total_requests = 0
    days_active = 0

    for log_file in sorted(_cost_log_dir().glob(f"{month_prefix}-*.json")):
        data = _load_day(log_file)
        total_cost += data.get("total_cost_usd", 0.0)
        total_requests += data.get("total_requests", 0)
        if data.get("total_requests", 0) > 0:
            days_active += 1

    avg_daily = total_cost / days_active if days_active > 0 else 0.0

    return {
        "month": month_prefix,
        "total_cost_usd": round(total_cost, 4),
        "total_requests": total_requests,
        "days_active": days_active,
        "avg_daily_cost_usd": round(avg_daily, 4),
        "projected_monthly_usd": round(avg_daily * 30, 2) if days_active > 0 else 0.0,
    }
