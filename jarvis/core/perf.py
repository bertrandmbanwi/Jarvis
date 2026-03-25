"""Lightweight latency profiling and throughput tracking for bottleneck identification."""
import asyncio
import functools
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("jarvis.core.perf")


@dataclass
class LatencyBucket:
    """Aggregated latency stats for an operation."""
    name: str
    count: int = 0
    total_s: float = 0.0
    min_s: float = float("inf")
    max_s: float = 0.0
    _recent: list[float] = field(default_factory=list)
    _recent_max: int = 50

    def record(self, duration_s: float):
        self.count += 1
        self.total_s += duration_s
        self.min_s = min(self.min_s, duration_s)
        self.max_s = max(self.max_s, duration_s)
        self._recent.append(duration_s)
        if len(self._recent) > self._recent_max:
            self._recent.pop(0)

    @property
    def avg_s(self) -> float:
        return self.total_s / self.count if self.count > 0 else 0.0

    @property
    def recent_avg_s(self) -> float:
        """Average of recent measurements."""
        if not self._recent:
            return 0.0
        return sum(self._recent) / len(self._recent)

    @property
    def p90_s(self) -> float:
        """90th percentile of recent measurements."""
        if not self._recent:
            return 0.0
        sorted_vals = sorted(self._recent)
        idx = int(len(sorted_vals) * 0.9)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "avg_s": round(self.avg_s, 3),
            "min_s": round(self.min_s, 3) if self.min_s != float("inf") else 0.0,
            "max_s": round(self.max_s, 3),
            "p90_s": round(self.p90_s, 3),
            "recent_avg_s": round(self.recent_avg_s, 3),
            "total_s": round(self.total_s, 2),
        }


class PerfTracker:
    """Centralized performance metrics tracker for bottleneck identification."""

    def __init__(self):
        self._buckets: dict[str, LatencyBucket] = {}
        self._lock = asyncio.Lock()

        self._request_count = 0
        self._request_total_s = 0.0
        self._tier_usage: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "total_s": 0.0, "downgrades": 0}
        )

    def _get_bucket(self, name: str) -> LatencyBucket:
        """Get or create a latency bucket for a named operation."""
        if name not in self._buckets:
            self._buckets[name] = LatencyBucket(name=name)
        return self._buckets[name]

    def record(self, name: str, duration_s: float):
        """Record a timing measurement for a named operation."""
        bucket = self._get_bucket(name)
        bucket.record(duration_s)

    def record_request(self, duration_s: float, tier: str):
        """Record end-to-end request with tier info."""
        self._request_count += 1
        self._request_total_s += duration_s
        self._tier_usage[tier]["count"] += 1
        self._tier_usage[tier]["total_s"] += duration_s

    def record_tier_downgrade(self, from_tier: str, to_tier: str, reason: str):
        """Record when a request was downgraded to a cheaper tier."""
        self._tier_usage[from_tier]["downgrades"] += 1
        logger.info(
            "Tier downgrade: %s -> %s (reason: %s)",
            from_tier, to_tier, reason,
        )

    @asynccontextmanager
    async def measure(self, name: str):
        """Async context manager for timing a code block."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.record(name, duration)

    def get_stats(self) -> dict:
        """Get comprehensive performance statistics."""
        avg_request = (
            self._request_total_s / self._request_count
            if self._request_count > 0
            else 0.0
        )

        # Sort buckets by total time (biggest bottlenecks first)
        sorted_buckets = sorted(
            self._buckets.values(),
            key=lambda b: b.total_s,
            reverse=True,
        )

        return {
            "requests": {
                "total": self._request_count,
                "avg_latency_s": round(avg_request, 3),
                "total_time_s": round(self._request_total_s, 2),
            },
            "tier_usage": {
                tier: {
                    "count": data["count"],
                    "avg_s": round(data["total_s"] / data["count"], 3) if data["count"] > 0 else 0.0,
                    "downgrades": data["downgrades"],
                }
                for tier, data in self._tier_usage.items()
            },
            "operations": {
                bucket.name: bucket.to_dict()
                for bucket in sorted_buckets[:20]  # Top 20 by total time
            },
            "bottlenecks": self._identify_bottlenecks(),
        }

    def _identify_bottlenecks(self) -> list[dict]:
        """Identify operations that are disproportionately slow."""
        bottlenecks = []
        for bucket in self._buckets.values():
            if bucket.count < 3:
                continue

            if bucket.avg_s > 3.0:
                bottlenecks.append({
                    "operation": bucket.name,
                    "avg_s": round(bucket.avg_s, 3),
                    "p90_s": round(bucket.p90_s, 3),
                    "count": bucket.count,
                    "suggestion": self._suggest_fix(bucket),
                })

        bottlenecks.sort(key=lambda b: b["avg_s"], reverse=True)
        return bottlenecks[:5]

    def _suggest_fix(self, bucket: LatencyBucket) -> str:
        """Suggest a performance fix based on operation name and stats."""
        name = bucket.name

        if "llm" in name and "deep" in name:
            return "Consider downgrading to brain tier if task complexity allows"
        if "llm" in name:
            return "Check if response can be cached or if a cheaper tier suffices"
        if "tool.browse_web" in name:
            return "Browser automation is inherently slow; consider chrome extension tools"
        if "tool." in name and bucket.avg_s > 10:
            return "Tool is very slow; consider increasing timeout or breaking into steps"
        if "plan" in name:
            return "Plan orchestration overhead; check if decomposition was necessary"
        return "Review for optimization opportunities"

    def get_summary_line(self) -> str:
        """One-line performance summary."""
        if self._request_count == 0:
            return "No requests processed yet."

        avg = self._request_total_s / self._request_count
        cache_info = ""
        try:
            from jarvis.core.cache import tool_cache
            stats = tool_cache.get_stats()
            cache_info = f", cache: {stats['hit_rate_pct']}% hit rate"
        except Exception:
            pass

        return (
            f"Perf: {self._request_count} requests, "
            f"avg {avg:.2f}s{cache_info}"
        )


perf_tracker = PerfTracker()


def timed(name: str):
    """Decorator that records execution time of async functions."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start
                perf_tracker.record(name, duration)
        return wrapper
    return decorator


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_request_cost(
    input_tokens: int,
    estimated_output_tokens: int,
    tier: str,
) -> float:
    """Estimate LLM request cost in USD for tier routing decisions."""
    from jarvis.config import settings

    tier_to_model = {
        "fast": settings.CLAUDE_FAST_MODEL,
        "brain": settings.CLAUDE_BRAIN_MODEL,
        "deep": settings.CLAUDE_DEEP_MODEL,
    }
    model = tier_to_model.get(tier, settings.CLAUDE_BRAIN_MODEL)
    pricing = settings.CLAUDE_PRICING.get(model, {})
    if not pricing:
        return 0.0

    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (estimated_output_tokens / 1_000_000) * pricing["output"]
    )
    return cost
