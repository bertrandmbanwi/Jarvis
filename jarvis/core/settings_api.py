"""Settings API endpoints for JARVIS configuration management.

Provides REST endpoints for querying and updating JARVIS settings, testing
integrations (Anthropic API, Ollama), and checking system status.

All endpoints validate input and reject attempts to execute arbitrary code.
Only safe configuration keys are allowed for updates.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException

from jarvis.config import settings

logger = logging.getLogger("jarvis.settings_api")

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

# Safe configuration keys that can be updated via API
SAFE_CONFIG_KEYS = {
    "ANTHROPIC_API_KEY",
    "CLAUDE_DEFAULT_TIER",
    "CLAUDE_FAST_MODEL",
    "CLAUDE_BRAIN_MODEL",
    "CLAUDE_DEEP_MODEL",
    "COST_DAILY_ALERT",
    "COST_MONTHLY_ALERT",
    "TTS_ENGINE",
    "TTS_VOICE",
    "TTS_SPEED",
    "STT_ENGINE",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "PREFER_CLAUDE",
    "API_HOST",
    "API_PORT",
    "UI_PORT",
}

# Start time for uptime calculation
_startup_time = time.time()


@settings_router.get("")
async def get_settings() -> dict:
    """
    Get current JARVIS settings (safe subset, no API keys).

    Returns:
        Dict with model tiers, cost thresholds, voice config, feature flags
    """
    return {
        "models": {
            "fast": settings.CLAUDE_FAST_MODEL,
            "brain": settings.CLAUDE_BRAIN_MODEL,
            "deep": settings.CLAUDE_DEEP_MODEL,
            "default": settings.CLAUDE_DEFAULT_TIER,
        },
        "costs": {
            "daily_alert_usd": settings.COST_DAILY_ALERT,
            "monthly_alert_usd": settings.COST_MONTHLY_ALERT,
        },
        "voice": {
            "tts_engine": settings.TTS_ENGINE,
            "tts_voice": settings.TTS_VOICE,
            "tts_speed": settings.TTS_SPEED,
            "stt_engine": settings.STT_ENGINE,
        },
        "integrations": {
            "prefer_claude": settings.PREFER_CLAUDE,
            "ollama_url": settings.OLLAMA_BASE_URL,
            "ollama_model": settings.OLLAMA_MODEL,
        },
    }


@settings_router.post("/test-api")
async def test_anthropic_api(api_key: Optional[str] = None) -> dict:
    """
    Test if Anthropic API key is valid.

    Args:
        api_key: Optional API key to test; uses ANTHROPIC_API_KEY if not provided

    Returns:
        Dict with valid (bool), model (str), error (str|null)
    """
    key_to_test = api_key or settings.ANTHROPIC_API_KEY

    if not key_to_test:
        return {"valid": False, "model": None, "error": "No API key provided"}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key_to_test)

        # Make a minimal call to verify the key works
        response = client.messages.create(
            model=settings.CLAUDE_FAST_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "ok"}],
        )

        return {
            "valid": True,
            "model": response.model,
            "error": None,
        }

    except Exception as e:
        logger.warning("Anthropic API test failed: %s", str(e))
        return {
            "valid": False,
            "model": None,
            "error": str(e),
        }


@settings_router.post("/test-ollama")
async def test_ollama() -> dict:
    """
    Test if Ollama is reachable and list available models.

    Returns:
        Dict with valid (bool), models (list[str]), error (str|null)
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.OLLAMA_BASE_URL}/api/tags",
            )
            response.raise_for_status()

            data = response.json()
            models = [m["name"] for m in data.get("models", [])]

            return {
                "valid": True,
                "models": models,
                "error": None,
            }

    except Exception as e:
        logger.warning("Ollama test failed: %s", str(e))
        return {
            "valid": False,
            "models": [],
            "error": str(e),
        }


@settings_router.get("/status")
async def get_status() -> dict:
    """
    Get integration status and system info.

    Returns:
        Dict with anthropic (bool), ollama (bool), tts (str), stt (str),
        memory_count (int), uptime_seconds (float)
    """
    # Test Anthropic
    anthropic_valid = bool(settings.ANTHROPIC_API_KEY)

    # Test Ollama
    ollama_valid = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f"{settings.OLLAMA_BASE_URL}/api/tags",
            )
            ollama_valid = response.status_code == 200
    except Exception:
        pass

    # Count memory entries (approximate)
    memory_count = 0
    try:
        if settings.MEMORY_DIR.exists():
            memory_count = len(list(settings.MEMORY_DIR.glob("*")))
    except Exception:
        pass

    uptime = time.time() - _startup_time

    return {
        "anthropic": anthropic_valid,
        "ollama": ollama_valid,
        "tts": settings.TTS_ENGINE,
        "stt": settings.STT_ENGINE,
        "memory_count": memory_count,
        "uptime_seconds": round(uptime, 1),
    }


@settings_router.post("/update")
async def update_settings(updates: dict) -> dict:
    """
    Update JARVIS settings and write to .env file.

    Args:
        updates: Dict of safe configuration keys to update

    Returns:
        Dict with success (bool), updated (list[str]), error (str|null)
    """
    if not updates:
        return {"success": True, "updated": [], "error": None}

    # Validate that only safe keys are being updated
    unsafe_keys = set(updates.keys()) - SAFE_CONFIG_KEYS
    if unsafe_keys:
        logger.warning("Attempt to update unsafe keys: %s", unsafe_keys)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update these keys: {unsafe_keys}",
        )

    try:
        env_path = settings.JARVIS_HOME / ".env"

        # Read existing .env
        env_content = {}
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        env_content[key.strip()] = value.strip()

        # Update with new values
        updated = []
        for key, value in updates.items():
            env_content[key] = str(value)
            updated.append(key)

        # Write back to .env
        with open(env_path, "w") as f:
            f.write("# JARVIS Configuration\n")
            f.write("# Auto-generated; edits may be overwritten\n\n")
            for key, value in sorted(env_content.items()):
                f.write(f"{key}={value}\n")

        logger.info("Settings updated: %s", updated)

        return {
            "success": True,
            "updated": updated,
            "error": None,
        }

    except Exception as e:
        logger.error("Settings update failed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update settings: {str(e)}",
        )
