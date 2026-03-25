"""Weather API using Open-Meteo (free, no API key required)."""
import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger("jarvis.tools.weather")

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    import urllib.request
    import urllib.error


async def get_weather(location: str) -> str:
    """Get current weather and tomorrow's forecast for a location."""
    if not location or not location.strip():
        return "Please provide a location (city name or zip code)."

    location = location.strip()
    logger.info("Weather query for location: '%s'", location)

    try:
        coords = await _geocode_location(location)
        if not coords:
            return f"Could not find location: {location}. Try a different city name or zip code."

        lat, lon, place_name = coords
        logger.info("Geocoded '%s' to %.4f, %.4f (%s)", location, lat, lon, place_name)

        weather_data = await _fetch_weather(lat, lon)
        if not weather_data:
            return f"Could not retrieve weather for {place_name}. Please try again."

        summary = _format_weather_summary(place_name, weather_data)
        return summary

    except Exception as e:
        logger.error("Weather lookup error for '%s': %s", location, e)
        return f"Error retrieving weather: {str(e)[:100]}"


async def _geocode_location(location: str) -> Optional[tuple[float, float, str]]:
    """Convert location name or zip to latitude, longitude, and place name."""
    url = "https://geocoding-api.open-meteo.com/v1/search"

    search_variants = _build_search_variants(location)

    for variant in search_variants:
        params = {
            "name": variant,
            "count": 1,
            "language": "en",
            "format": "json",
        }

        try:
            response_json = await _http_get(url, params)
            if response_json and "results" in response_json:
                results = response_json.get("results", [])
                if results:
                    result = results[0]
                    lat = result.get("latitude")
                    lon = result.get("longitude")
                    name = result.get("name", location)
                    country = result.get("country", "")
                    admin1 = result.get("admin1", "")  # state/region

                    if admin1:
                        place_name = f"{name}, {admin1}"
                    elif country:
                        place_name = f"{name}, {country}"
                    else:
                        place_name = name

                    return (lat, lon, place_name)
        except Exception as e:
            logger.debug("Geocoding attempt '%s' failed: %s", variant, e)
            continue

    logger.warning("No geocoding results for any variant of '%s'", location)
    return None


def _build_search_variants(location: str) -> list[str]:
    """Build a list of search queries to try for geocoding."""
    import re

    location = location.strip()
    variants = []

    us_states = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    }

    match = re.match(r'^(.+?)[,\s]+([A-Z]{2})$', location.strip(), re.IGNORECASE)
    if match:
        city_part = match.group(1).strip()
        state_part = match.group(2).strip().upper()
        if state_part in us_states:
            variants.append(city_part)
            variants.append(location)

    if re.match(r'^\d{5}(-\d{4})?$', location):
        variants.append(location)
    elif not variants:
        variants.append(location)

    return variants


async def _fetch_weather(lat: float, lon: float) -> Optional[dict]:
    """Fetch weather data from Open-Meteo Weather API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "forecast_days": 2,
    }

    try:
        data = await _http_get(url, params)
        return data
    except Exception as e:
        logger.error("Weather API error: %s", e)
        return None


async def _http_get(url: str, params: dict) -> Optional[dict]:
    """Fetch JSON from a URL with query parameters."""
    if HAS_HTTPX:
        return await _http_get_httpx(url, params)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _http_get_urllib, url, params,
        )


async def _http_get_httpx(url: str, params: dict) -> Optional[dict]:
    """Fetch using httpx (async-friendly)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("httpx request error: %s", e)
        return None


def _http_get_urllib(url: str, params: dict) -> Optional[dict]:
    """Fetch using urllib (sync, run in executor)."""
    try:
        import urllib.parse
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        with urllib.request.urlopen(full_url, timeout=10) as response:
            data = response.read()
            return json.loads(data)
    except Exception as e:
        logger.error("urllib request error: %s", e)
        return None


def _format_weather_summary(place_name: str, weather_data: dict) -> str:
    """Format weather data into a speech-friendly summary."""
    lines = [f"Weather for {place_name}:"]

    current = weather_data.get("current", {})
    if current:
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_speed = current.get("wind_speed_10m")
        weather_code = current.get("weather_code")
        condition = _weather_code_to_text(weather_code)

        lines.append(f"Now: {condition}, {temp}F")
        if humidity is not None:
            lines.append(f"Humidity: {humidity}%")
        if wind_speed is not None:
            lines.append(f"Wind: {wind_speed} mph")

    daily = weather_data.get("daily", {})
    if daily:
        times = daily.get("time", [])
        codes = daily.get("weather_code", [])
        temps_max = daily.get("temperature_2m_max", [])
        temps_min = daily.get("temperature_2m_min", [])
        precip_chance = daily.get("precipitation_probability_max", [])

        if len(times) > 1:
            tomorrow_code = codes[1] if len(codes) > 1 else None
            tomorrow_max = temps_max[1] if len(temps_max) > 1 else None
            tomorrow_min = temps_min[1] if len(temps_min) > 1 else None
            tomorrow_precip = precip_chance[1] if len(precip_chance) > 1 else None

            tomorrow_condition = _weather_code_to_text(tomorrow_code)
            lines.append("")
            lines.append(f"Tomorrow: {tomorrow_condition}")

            if tomorrow_max is not None and tomorrow_min is not None:
                lines.append(f"High {tomorrow_max}F, Low {tomorrow_min}F")

            if tomorrow_precip is not None and tomorrow_precip > 0:
                lines.append(f"Precipitation chance: {tomorrow_precip}%")

    return "\n".join(lines)


def _weather_code_to_text(code: Optional[int]) -> str:
    """Convert WMO weather code to human-readable text."""
    if code is None:
        return "Unknown"

    codes: dict[int, str] = {
        0: "Clear sky",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }

    return codes.get(code, f"Weather code {code}")
