"""Secret storage helpers with macOS Keychain support."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("jarvis.secrets")

SERVICE_NAME = "com.jarvis.assistant"
SUPPORTED_SECRETS = {
    "ANTHROPIC_API_KEY",
    "GOOGLE_CALENDAR_CLIENT_SECRET",
    "GOOGLE_CALENDAR_TOKEN",
    "OUTLOOK_CALENDAR_CLIENT_SECRET",
    "OUTLOOK_CALENDAR_TOKEN",
}


class SecretStoreError(RuntimeError):
    """Raised when a secret cannot be persisted securely."""


@dataclass(frozen=True)
class SecretBackendStatus:
    backend: str
    available: bool
    message: str = ""


def _load_keyring():
    try:
        import keyring

        return keyring
    except Exception as exc:
        logger.debug("keyring unavailable: %s", exc)
        return None


def _is_supported(name: str) -> bool:
    return name in SUPPORTED_SECRETS


def get_secret_backend_status() -> dict[str, str | bool]:
    """Return the active secret backend status for the settings UI."""
    keyring = _load_keyring()
    if keyring is None:
        return SecretBackendStatus(
            backend="environment",
            available=False,
            message="keyring package is unavailable; existing environment variables still work.",
        ).__dict__

    try:
        backend = keyring.get_keyring()
        return SecretBackendStatus(backend=backend.__class__.__name__, available=True).__dict__
    except Exception as exc:
        return SecretBackendStatus(backend="unknown", available=False, message=str(exc)).__dict__


def get_secret(name: str) -> str:
    """Read a secret from environment first, then Keychain/keyring."""
    if not _is_supported(name):
        return ""

    env_value = os.getenv(name, "")
    if env_value:
        return env_value

    keyring = _load_keyring()
    if keyring is None:
        return ""

    try:
        return keyring.get_password(SERVICE_NAME, name) or ""
    except Exception as exc:
        logger.debug("Secret lookup failed for %s: %s", name, exc)
        return ""


def set_secret(name: str, value: str) -> None:
    """Persist a supported secret in Keychain/keyring."""
    if not _is_supported(name):
        raise SecretStoreError(f"Unsupported secret: {name}")

    keyring = _load_keyring()
    if keyring is None:
        raise SecretStoreError("The keyring package is not installed; cannot store secrets securely.")

    try:
        keyring.set_password(SERVICE_NAME, name, value)
    except Exception as exc:
        raise SecretStoreError(f"Failed to store {name} in the secure secret backend: {exc}") from exc


def delete_secret(name: str) -> None:
    """Delete a supported secret from Keychain/keyring if it exists."""
    if not _is_supported(name):
        raise SecretStoreError(f"Unsupported secret: {name}")

    keyring = _load_keyring()
    if keyring is None:
        return

    try:
        keyring.delete_password(SERVICE_NAME, name)
    except Exception as exc:
        logger.debug("Secret delete failed for %s: %s", name, exc)
