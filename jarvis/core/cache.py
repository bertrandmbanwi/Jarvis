"""TTL-based LRU cache for tool results with per-tool expiration and metrics."""
import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("jarvis.core.cache")


@dataclass
class CacheEntry:
    """A single cached result with metadata."""
    key: str
    value: Any
    created_at: float
    ttl_s: float
    tool_name: str
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_s

    @property
    def age_s(self) -> float:
        return time.time() - self.created_at


TOOL_CACHE_TTLS: dict[str, float] = {
    "get_battery_status": 30.0,
    "get_disk_usage": 60.0,
    "get_cpu_usage": 15.0,
    "get_system_info": 120.0,
    "get_volume": 10.0,
    "get_brightness": 10.0,
    "get_upcoming_events": 120.0,
    "list_calendars": 300.0,
    "get_unread_email_count": 60.0,
    "read_inbox": 60.0,
    "list_running_apps": 10.0,
    "get_active_window": 5.0,
    "get_plan_status": 5.0,
    "get_plan_history": 30.0,
    "get_learning_insights": 60.0,
    "get_tool_reliability": 60.0,
    "get_proactive_status": 30.0,
    "get_agent_status": 15.0,
    "get_active_agents": 5.0,
    "get_system_health": 15.0,
    "get_user_profile": 300.0,
    "get_user_preference": 300.0,
    "chrome_extension_status": 30.0,
    "chrome_get_tabs": 10.0,
}

UNCACHEABLE_TOOLS: set[str] = {
    "run_command",
    "run_terminal_command_smart",
    "send_email",
    "create_event",
    "write_file",
    "move_file",
    "copy_file",
    "create_directory",
    "delete_file",
    "set_volume",
    "set_brightness",
    "toggle_dark_mode",
    "show_notification",
    "open_application",
    "close_application",
    "paste_to_app",
    "write_to_app",
    "browse_web",
    "browser_navigate",
    "browser_screenshot",
    "browser_interact",
    "browser_switch_tab",
    "browser_upload_file",
    "close_browser",
    "chrome_navigate",
    "chrome_click",
    "chrome_type",
    "chrome_screenshot",
    "chrome_execute_js",
    "chrome_fill_form",
    "chrome_scroll",
    "sync_browser_sessions",
    "run_claude_code",
    "scaffold_project",
    "search_web",
    "search_and_read",
    "fetch_page_text",
    "search_in_browser",
    "open_url_in_browser",
    "set_proactive_setting",
    "update_user_profile",
    "cancel_active_plan",
    "copy_to_clipboard",
    "read_clipboard",
}


def _make_cache_key(tool_name: str, tool_input: dict) -> str:
    """Generate deterministic cache key from tool name and arguments."""

    sorted_args = json.dumps(tool_input, sort_keys=True, default=str)
    raw = f"{tool_name}:{sorted_args}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class ResultCache:
    """TTL-based LRU cache for tool results with asyncio.Lock and per-tool TTLs."""

    def __init__(self, max_size: int = 200):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._bypasses = 0

    def is_cacheable(self, tool_name: str) -> bool:
        """Check if a tool's results should be cached."""
        if tool_name in UNCACHEABLE_TOOLS:
            return False
        return tool_name in TOOL_CACHE_TTLS

    def get_ttl(self, tool_name: str) -> float:
        """Get the TTL for a tool (0.0 if not cacheable)."""
        return TOOL_CACHE_TTLS.get(tool_name, 0.0)

    async def get(self, tool_name: str, tool_input: dict) -> Optional[Any]:
        """Look up a cached result, removing expired entries."""
        if not self.is_cacheable(tool_name):
            return None

        key = _make_cache_key(tool_name, tool_input)

        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                logger.debug(
                    "Cache expired for %s (age: %.1fs, ttl: %.1fs)",
                    tool_name, entry.age_s, entry.ttl_s,
                )
                return None

            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1

            logger.debug(
                "Cache hit for %s (age: %.1fs, hits: %d)",
                tool_name, entry.age_s, entry.hit_count,
            )
            return entry.value

    async def put(self, tool_name: str, tool_input: dict, value: Any):
        """Store a result in cache with LRU eviction if needed."""
        if not self.is_cacheable(tool_name):
            return

        ttl = self.get_ttl(tool_name)
        if ttl <= 0:
            return

        key = _make_cache_key(tool_name, tool_input)

        async with self._lock:
            while len(self._cache) >= self._max_size:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._evictions += 1
                logger.debug(
                    "Cache evicted %s (tool: %s, age: %.1fs)",
                    evicted_key[:8], evicted_entry.tool_name, evicted_entry.age_s,
                )

            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl_s=ttl,
                tool_name=tool_name,
            )

    async def invalidate(self, tool_name: str = None):
        """Invalidate cache entries for a tool or all entries."""
        async with self._lock:
            if tool_name is None:
                count = len(self._cache)
                self._cache.clear()
                logger.info("Cache cleared: %d entries removed.", count)
            else:
                keys_to_remove = [
                    k for k, v in self._cache.items()
                    if v.tool_name == tool_name
                ]
                for k in keys_to_remove:
                    del self._cache[k]
                if keys_to_remove:
                    logger.debug(
                        "Cache invalidated %d entries for %s.",
                        len(keys_to_remove), tool_name,
                    )

    async def cleanup_expired(self):
        """Remove all expired entries."""
        async with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired
            ]
            for k in expired_keys:
                del self._cache[k]
            if expired_keys:
                logger.debug("Cache cleanup: removed %d expired entries.", len(expired_keys))

    def get_stats(self) -> dict:
        """Get cache performance statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        # Per-tool breakdown
        tool_stats = {}
        for entry in self._cache.values():
            if entry.tool_name not in tool_stats:
                tool_stats[entry.tool_name] = {
                    "entries": 0,
                    "total_hits": 0,
                    "ttl_s": entry.ttl_s,
                }
            tool_stats[entry.tool_name]["entries"] += 1
            tool_stats[entry.tool_name]["total_hits"] += entry.hit_count

        return {
            "total_entries": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
            "evictions": self._evictions,
            "bypasses": self._bypasses,
            "tools_cached": len(tool_stats),
            "per_tool": tool_stats,
        }

    def record_bypass(self):
        """Record that a cache lookup was bypassed."""
        self._bypasses += 1


tool_cache = ResultCache(max_size=200)

INVALIDATION_MAP: dict[str, list[str]] = {
    "send_email": ["get_unread_email_count", "read_inbox"],
    "create_event": ["get_upcoming_events"],
    "set_volume": ["get_volume"],
    "set_brightness": ["get_brightness"],
    "open_application": ["list_running_apps"],
    "close_application": ["list_running_apps"],
    "update_user_profile": ["get_user_profile", "get_user_preference"],
    "set_proactive_setting": ["get_proactive_status"],
    "cancel_active_plan": ["get_plan_status"],
}


async def invalidate_on_mutation(tool_name: str):
    """Invalidate cache entries affected by a mutating tool call."""
    targets = INVALIDATION_MAP.get(tool_name, [])
    for target in targets:
        await tool_cache.invalidate(target)
