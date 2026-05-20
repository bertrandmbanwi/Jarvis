"""Settings API endpoints for JARVIS configuration management.

Provides REST endpoints for querying and updating JARVIS settings, testing
integrations (Anthropic API, Ollama), and checking system status.

All endpoints validate input and reject attempts to execute arbitrary code.
Only safe configuration keys are allowed for updates.
"""
import logging
import os
import time
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from jarvis.config import settings
from jarvis.core.secrets import SecretStoreError, delete_secret, get_secret_backend_status, set_secret

logger = logging.getLogger("jarvis.settings_api")

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

# Safe configuration keys that can be updated via API
SAFE_CONFIG_KEYS = {
    "ANTHROPIC_API_KEY",
    "GOOGLE_CALENDAR_CLIENT_ID",
    "GOOGLE_CALENDAR_CLIENT_SECRET",
    "OUTLOOK_CALENDAR_CLIENT_ID",
    "OUTLOOK_CALENDAR_CLIENT_SECRET",
    "CLAUDE_DEFAULT_TIER",
    "CLAUDE_FAST_MODEL",
    "CLAUDE_BRAIN_MODEL",
    "CLAUDE_DEEP_MODEL",
    "COST_DAILY_ALERT",
    "COST_MONTHLY_ALERT",
    "COST_DAILY_HARD_LIMIT",
    "COST_MONTHLY_HARD_LIMIT",
    "COST_MODE",
    "COST_DEEP_PREMIUM_LIMIT",
    "LOCAL_FIRST_ENABLED",
    "MEMORY_ENABLED",
    "PRIVACY_MODE_DEFAULT",
    "ANTHROPIC_LAZY_HEALTHCHECK",
    "ANTHROPIC_CACHE_TOOLS",
    "ANTHROPIC_PROMPT_CACHE_TTL",
    "ANTHROPIC_BATCH_FOR_BACKGROUND",
    "WORKFLOW_SCHEDULER_ENABLED",
    "CONTEXT_RECENT_MESSAGES",
    "CONTEXT_SUMMARY_MAX_CHARS",
    "TTS_ENGINE",
    "TTS_VOICE",
    "TTS_SPEED",
    "STT_ENGINE",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_FAST_MODEL",
    "PREFER_CLAUDE",
    "API_HOST",
    "API_PORT",
    "UI_PORT",
}

# Start time for uptime calculation
_startup_time = time.time()


class TestApiRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=512)


class TestOllamaRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=300)


def _normalize_updates(raw_updates: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize settings values before writing them to .env."""
    normalized: dict[str, Any] = {}

    for key, value in raw_updates.items():
        if value is None:
            value = ""

        if isinstance(value, str):
            value = value.strip()
            if "\n" in value or "\r" in value or "\x00" in value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid value for {key}: newlines and NUL bytes are not allowed.",
                )

        if key in {"API_PORT", "UI_PORT"}:
            try:
                port = int(value)
            except (TypeError, ValueError) as err:
                raise HTTPException(status_code=400, detail=f"{key} must be a port number.") from err
            if not 1 <= port <= 65535:
                raise HTTPException(status_code=400, detail=f"{key} must be between 1 and 65535.")
            normalized[key] = port
        elif key in {
            "COST_DAILY_ALERT", "COST_MONTHLY_ALERT", "COST_DAILY_HARD_LIMIT",
            "COST_MONTHLY_HARD_LIMIT", "COST_DEEP_PREMIUM_LIMIT",
        }:
            try:
                amount = float(value)
            except (TypeError, ValueError) as err:
                raise HTTPException(status_code=400, detail=f"{key} must be numeric.") from err
            if amount < 0:
                raise HTTPException(status_code=400, detail=f"{key} cannot be negative.")
            normalized[key] = amount
        elif key == "TTS_SPEED":
            try:
                speed = float(value)
            except (TypeError, ValueError) as err:
                raise HTTPException(status_code=400, detail="TTS_SPEED must be numeric.") from err
            if not 0.5 <= speed <= 2.0:
                raise HTTPException(status_code=400, detail="TTS_SPEED must be between 0.5 and 2.0.")
            normalized[key] = speed
        elif key in {"CONTEXT_RECENT_MESSAGES", "CONTEXT_SUMMARY_MAX_CHARS"}:
            try:
                count = int(value)
            except (TypeError, ValueError) as err:
                raise HTTPException(status_code=400, detail=f"{key} must be an integer.") from err
            if count < 1:
                raise HTTPException(status_code=400, detail=f"{key} must be positive.")
            normalized[key] = count
        elif key == "COST_MODE":
            mode = str(value).lower()
            if mode not in {"economy", "balanced", "power"}:
                raise HTTPException(status_code=400, detail="COST_MODE must be economy, balanced, or power.")
            normalized[key] = mode
        elif key == "ANTHROPIC_PROMPT_CACHE_TTL":
            ttl = str(value).lower()
            if ttl not in {"5m", "1h"}:
                raise HTTPException(status_code=400, detail="ANTHROPIC_PROMPT_CACHE_TTL must be 5m or 1h.")
            normalized[key] = ttl
        elif key in {
            "PREFER_CLAUDE", "LOCAL_FIRST_ENABLED", "MEMORY_ENABLED",
            "PRIVACY_MODE_DEFAULT", "ANTHROPIC_LAZY_HEALTHCHECK",
            "ANTHROPIC_CACHE_TOOLS", "ANTHROPIC_BATCH_FOR_BACKGROUND",
            "WORKFLOW_SCHEDULER_ENABLED",
        }:
            if isinstance(value, bool):
                normalized[key] = value
            elif str(value).lower() in {"true", "1", "yes", "on"}:
                normalized[key] = True
            elif str(value).lower() in {"false", "0", "no", "off"}:
                normalized[key] = False
            else:
                raise HTTPException(status_code=400, detail=f"{key} must be boolean.")
        else:
            normalized[key] = value

    return normalized


def _env_value(value: Any) -> str:
    """Serialize a validated value for a simple KEY=value .env file."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
            "daily_hard_limit_usd": settings.COST_DAILY_HARD_LIMIT,
            "monthly_hard_limit_usd": settings.COST_MONTHLY_HARD_LIMIT,
            "mode": settings.COST_MODE,
            "deep_premium_limit_usd": settings.COST_DEEP_PREMIUM_LIMIT,
        },
        "cost_controls": {
            "local_first_enabled": settings.LOCAL_FIRST_ENABLED,
            "memory_enabled": settings.MEMORY_ENABLED,
            "privacy_mode_default": settings.PRIVACY_MODE_DEFAULT,
            "lazy_healthcheck": settings.ANTHROPIC_LAZY_HEALTHCHECK,
            "cache_tools": settings.ANTHROPIC_CACHE_TOOLS,
            "prompt_cache_ttl": settings.ANTHROPIC_PROMPT_CACHE_TTL,
            "batch_for_background": settings.ANTHROPIC_BATCH_FOR_BACKGROUND,
            "workflow_scheduler_enabled": settings.WORKFLOW_SCHEDULER_ENABLED,
            "context_recent_messages": settings.CONTEXT_RECENT_MESSAGES,
            "context_summary_max_chars": settings.CONTEXT_SUMMARY_MAX_CHARS,
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
            "ollama_fast_model": settings.OLLAMA_FAST_MODEL,
            "google_calendar_configured": bool(settings.GOOGLE_CALENDAR_CLIENT_ID),
            "outlook_calendar_configured": bool(settings.OUTLOOK_CALENDAR_CLIENT_ID),
        },
        "secrets": get_secret_backend_status(),
    }


@settings_router.post("/test-api")
async def test_anthropic_api(
    body: Annotated[TestApiRequest | None, Body()] = None,
) -> dict:
    """
    Test if Anthropic API key is valid.

    Args:
        api_key: Optional API key to test; uses ANTHROPIC_API_KEY if not provided

    Returns:
        Dict with valid (bool), model (str), error (str|null)
    """
    key_to_test = (body.api_key if body else None) or settings.ANTHROPIC_API_KEY

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
async def test_ollama(
    body: Annotated[TestOllamaRequest | None, Body()] = None,
) -> dict:
    """
    Test if Ollama is reachable and list available models.

    Returns:
        Dict with valid (bool), models (list[str]), error (str|null)
    """
    base_url = ((body.base_url if body else None) or settings.OLLAMA_BASE_URL).rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{base_url}/api/tags",
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
    except Exception as e:
        logger.debug("Ollama status check failed: %s", e)

    # Count memory entries (approximate)
    memory_count = 0
    try:
        if settings.MEMORY_DIR.exists():
            memory_count = len(list(settings.MEMORY_DIR.glob("*")))
    except Exception as e:
        logger.debug("Memory directory count failed: %s", e)

    uptime = time.time() - _startup_time

    return {
        "anthropic": anthropic_valid,
        "ollama": ollama_valid,
        "tts": settings.TTS_ENGINE,
        "stt": settings.STT_ENGINE,
        "memory_count": memory_count,
        "uptime_seconds": round(uptime, 1),
        "secrets": get_secret_backend_status(),
    }


@settings_router.post("/update")
async def update_settings(
    body: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict:
    """
    Update JARVIS settings. Non-secret values are written to .env; secrets are
    stored in the secure backend (macOS Keychain via keyring when available).

    Args:
        updates: Dict of safe configuration keys to update

    Returns:
        Dict with success (bool), updated (list[str]), error (str|null)
    """
    body = body or {}
    updates = body.get("updates", body)

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

    updates = _normalize_updates(updates)

    try:
        env_path = settings.JARVIS_HOME / ".env"

        # Read existing .env
        env_content = {}
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
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
            if key in {
                "ANTHROPIC_API_KEY",
                "GOOGLE_CALENDAR_CLIENT_SECRET",
                "OUTLOOK_CALENDAR_CLIENT_SECRET",
            }:
                secret_value = str(value)
                env_content.pop(key, None)
                if secret_value:
                    set_secret(key, secret_value)
                    os.environ[key] = secret_value
                else:
                    delete_secret(key)
                    os.environ.pop(key, None)
                if hasattr(settings, key):
                    setattr(settings, key, secret_value)
            else:
                env_content[key] = _env_value(value)
                os.environ[key] = _env_value(value)
                if hasattr(settings, key):
                    setattr(settings, key, value)
            updated.append(key)

        # Write back to .env
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# JARVIS Configuration\n")
            f.write("# Auto-generated; edits may be overwritten\n")
            f.write("# Secrets such as ANTHROPIC_API_KEY are stored in macOS Keychain.\n\n")
            for key, value in sorted(env_content.items()):
                f.write(f"{key}={value}\n")

        logger.info("Settings updated: %s", updated)

        return {
            "success": True,
            "updated": updated,
            "error": None,
        }

    except SecretStoreError as e:
        logger.error("Secret update failed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update secret: {str(e)}",
        ) from e
    except Exception as e:
        logger.error("Settings update failed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update settings: {str(e)}",
        ) from e
