"""Session-level visibility for local-first and free-API savings."""
from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any

FREE_DATA_PROVIDERS: dict[str, str] = {
    "get_weather": "Open-Meteo",
    "convert_currency": "Frankfurter/Fawaz",
    "get_crypto_price": "CoinGecko",
    "get_public_holidays": "Nager.Date",
    "get_next_public_holiday": "Nager.Date",
    "is_public_holiday": "Nager.Date",
    "get_country_info": "REST Countries",
    "get_sec_company_filings": "SEC EDGAR",
    "lookup_ip": "ipapi.co",
    "get_spaceflight_news": "Spaceflight News",
    "get_citybike_networks": "CityBikes",
    "check_public_api_status": "Public API Health",
}


class SavingsTracker:
    """Tracks calls that avoided the paid LLM path during this server session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._started_at = time.time()
            self._local_routes = 0
            self._paid_calls_avoided = 0
            self._free_api_calls = 0
            self._cache_hits = 0
            self._by_action: Counter[str] = Counter()
            self._by_provider: Counter[str] = Counter()
            self._last_event: dict[str, Any] | None = None

    def record_local_route(
        self,
        action: str,
        *,
        tool_name: str = "",
        cache_hit: bool = False,
    ) -> None:
        provider = FREE_DATA_PROVIDERS.get(tool_name, "")
        event = {
            "action": action,
            "tool_name": tool_name,
            "provider": provider or "Local",
            "cache_hit": cache_hit,
            "timestamp": time.time(),
        }
        with self._lock:
            self._local_routes += 1
            self._paid_calls_avoided += 1
            self._by_action[action] += 1
            if cache_hit:
                self._cache_hits += 1
            if provider:
                self._free_api_calls += 1
                self._by_provider[provider] += 1
            self._last_event = event

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started_at": self._started_at,
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "local_routes": self._local_routes,
                "paid_calls_avoided": self._paid_calls_avoided,
                "free_api_calls": self._free_api_calls,
                "cache_hits": self._cache_hits,
                "by_action": dict(self._by_action.most_common(12)),
                "by_provider": dict(self._by_provider.most_common(12)),
                "last_event": dict(self._last_event) if self._last_event else None,
            }


savings_tracker = SavingsTracker()
