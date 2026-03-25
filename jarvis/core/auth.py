"""PIN-based authentication for remote access; local connections bypass auth."""

import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.auth")

AUTH_DIR = settings.DATA_DIR / "auth"
AUTH_DIR.mkdir(parents=True, exist_ok=True)
PIN_HASH_FILE = AUTH_DIR / "pin.hash"
PIN_SALT_FILE = AUTH_DIR / "pin.salt"

PIN_LENGTH = 6
SESSION_TOKEN_EXPIRY = 24 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 60

_active_sessions: dict[str, float] = {}  # Maps token -> expiry timestamp
_failed_attempts: dict[str, list[float]] = {}  # Maps IP -> list of failed attempt timestamps
_current_pin: Optional[str] = None  # Plaintext PIN for display on startup


def _hash_pin(pin: str, salt: bytes) -> str:
    """Hash a PIN with salt."""
    return hashlib.sha256(salt + pin.encode("utf-8")).hexdigest()


def initialize_pin() -> str:
    """Initialize or load PIN from env vars, disk, or generate new."""
    global _current_pin

    custom_pin = os.getenv("JARVIS_PIN", "").strip()
    if custom_pin:
        if not custom_pin.isdigit() or not (4 <= len(custom_pin) <= 8):
            logger.error(
                "JARVIS_PIN must be 4-8 digits. Got: '%s' (%d chars). "
                "Falling back to stored or random PIN.",
                "*" * len(custom_pin), len(custom_pin),
            )
        else:
            salt = secrets.token_bytes(32)
            pin_hash = _hash_pin(custom_pin, salt)
            PIN_HASH_FILE.write_text(pin_hash, encoding="utf-8")
            PIN_SALT_FILE.write_bytes(salt)
            _current_pin = custom_pin
            logger.info("PIN set from JARVIS_PIN environment variable.")
            return custom_pin

    regen = os.getenv("JARVIS_REGEN_PIN", "").lower() in ("true", "1", "yes")

    if PIN_HASH_FILE.exists() and PIN_SALT_FILE.exists() and not regen:
        logger.info("PIN authentication loaded from disk.")
        _current_pin = None
        return ""

    pin = "".join([str(secrets.randbelow(10)) for _ in range(PIN_LENGTH)])
    salt = secrets.token_bytes(32)

    pin_hash = _hash_pin(pin, salt)
    PIN_HASH_FILE.write_text(pin_hash, encoding="utf-8")
    PIN_SALT_FILE.write_bytes(salt)

    _current_pin = pin
    logger.info("New PIN generated for remote access.")
    return pin


def get_current_pin() -> Optional[str]:
    """Get the current PIN if just generated; None if loaded from disk."""
    return _current_pin


def verify_pin(pin: str, client_ip: str = "") -> Optional[str]:
    """Verify PIN and return session token if correct."""
    if client_ip:
        now = time.time()
        attempts = _failed_attempts.get(client_ip, [])
        attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
        _failed_attempts[client_ip] = attempts

        if len(attempts) >= MAX_FAILED_ATTEMPTS:
            logger.warning(
                "Rate limit exceeded for %s (%d attempts in %ds).",
                client_ip, len(attempts), RATE_LIMIT_WINDOW,
            )
            return None

    if not PIN_HASH_FILE.exists() or not PIN_SALT_FILE.exists():
        logger.error("PIN not initialized. Call initialize_pin() first.")
        return None

    stored_hash = PIN_HASH_FILE.read_text(encoding="utf-8").strip()
    salt = PIN_SALT_FILE.read_bytes()

    candidate_hash = _hash_pin(pin, salt)
    if not hmac.compare_digest(candidate_hash, stored_hash):
        if client_ip:
            _failed_attempts.setdefault(client_ip, []).append(time.time())
        logger.warning("Invalid PIN attempt from %s.", client_ip or "unknown")
        return None

    token = secrets.token_hex(32)
    _active_sessions[token] = time.time() + SESSION_TOKEN_EXPIRY

    if client_ip:
        _failed_attempts.pop(client_ip, None)

    logger.info("PIN verified. Session token issued (expires in %dh).",
                SESSION_TOKEN_EXPIRY // 3600)
    return token


def validate_token(token: str) -> bool:
    """Check if session token is valid and not expired."""
    if not token:
        return False

    expiry = _active_sessions.get(token)
    if expiry is None:
        return False

    if time.time() > expiry:
        _active_sessions.pop(token, None)
        return False

    return True


def revoke_token(token: str):
    """Revoke a session token."""
    _active_sessions.pop(token, None)


def is_local_request(client_host: str) -> bool:
    """Check if request is from localhost (which bypasses authentication)."""
    local_hosts = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
    return client_host in local_hosts


def cleanup_expired_sessions():
    """Remove expired session tokens."""
    now = time.time()
    expired = [t for t, exp in _active_sessions.items() if now > exp]
    for t in expired:
        _active_sessions.pop(t, None)
    if expired:
        logger.debug("Cleaned up %d expired session(s).", len(expired))


def set_pin(new_pin: str) -> bool:
    """Set a specific PIN and invalidate existing sessions."""
    global _current_pin

    if not new_pin.isdigit() or not (4 <= len(new_pin) <= 8):
        logger.error("Invalid PIN format. Must be 4-8 digits.")
        return False

    salt = secrets.token_bytes(32)
    pin_hash = _hash_pin(new_pin, salt)
    PIN_HASH_FILE.write_text(pin_hash, encoding="utf-8")
    PIN_SALT_FILE.write_bytes(salt)

    _active_sessions.clear()

    _current_pin = new_pin
    logger.info("PIN updated successfully.")
    return True
