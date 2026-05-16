"""Tests for weather location defaults."""
import pytest

from jarvis.agent.tools_schema import TOOL_SCHEMAS
from jarvis.config import settings
from jarvis.core import profile
from jarvis.tools import weather


def test_profile_default_location_uses_city_and_state(monkeypatch):
    monkeypatch.setattr(
        profile,
        "_profile",
        {"location_city": "Forney", "location_state": "Texas"},
    )

    assert profile.get_default_location() == "Forney, Texas"


def test_profile_default_location_uses_saved_location_preference(monkeypatch):
    monkeypatch.setattr(
        profile,
        "_profile",
        {
            "location_city": "Forney",
            "location_state": "Texas",
            "preferences": {"location": "Austin, Texas"},
        },
    )

    assert profile.get_default_location() == "Austin, Texas"


def test_weather_tool_location_is_optional():
    schema = next(tool for tool in TOOL_SCHEMAS if tool["name"] == "get_weather")

    assert "location" not in schema["input_schema"].get("required", [])


def test_system_prompt_location_context_uses_profile(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "profile.json").write_text(
        '{"location_city": "Forney", "location_state": "Texas"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "PROFILE_DIR", profile_dir)

    context = settings._get_default_location_context()

    assert "Forney, Texas" in context
    assert "local weather requests" in context


@pytest.mark.asyncio
async def test_weather_uses_profile_location_when_missing(monkeypatch):
    monkeypatch.setattr(
        profile,
        "_profile",
        {"location_city": "Forney", "location_state": "Texas"},
    )
    requested_locations = []

    async def fake_geocode(location: str):
        requested_locations.append(location)
        return (32.7482, -96.4719, "Forney, Texas")

    async def fake_fetch_weather(lat: float, lon: float):
        return {
            "current": {
                "temperature_2m": 73,
                "relative_humidity_2m": 81,
                "wind_speed_10m": 8,
                "weather_code": 3,
            },
            "daily": {
                "time": ["2026-05-16", "2026-05-17"],
                "weather_code": [3, 3],
                "temperature_2m_max": [84, 89],
                "temperature_2m_min": [68, 70],
                "precipitation_probability_max": [0, 0],
            },
        }

    monkeypatch.setattr(weather, "_geocode_location", fake_geocode)
    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch_weather)

    result = await weather.get_weather("")

    assert requested_locations == ["Forney, Texas"]
    assert "Weather for Forney, Texas" in result
    assert "Now: Overcast, 73F" in result


@pytest.mark.asyncio
async def test_weather_keeps_explicit_location(monkeypatch):
    monkeypatch.setattr(
        profile,
        "_profile",
        {"location_city": "Forney", "location_state": "Texas"},
    )
    requested_locations = []

    async def fake_geocode(location: str):
        requested_locations.append(location)
        return (40.7128, -74.0060, "New York, New York")

    async def fake_fetch_weather(lat: float, lon: float):
        return {"current": {"temperature_2m": 61, "weather_code": 1}, "daily": {}}

    monkeypatch.setattr(weather, "_geocode_location", fake_geocode)
    monkeypatch.setattr(weather, "_fetch_weather", fake_fetch_weather)

    result = await weather.get_weather("New York")

    assert requested_locations == ["New York"]
    assert "Weather for New York, New York" in result
