import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# server.py initializes auth at import time; keep that import from rotating the
# developer's real data/auth PIN file during tests.
os.environ["JARVIS_REGEN_PIN"] = "false"

from jarvis.core import auth, server


class FakeRequest:
    def __init__(
        self,
        host: str = "203.0.113.10",
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ):
        self.client = SimpleNamespace(host=host)
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.query_params = query_params or {}


def test_initialize_pin_is_noop_when_pin_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth.settings, "PIN_AUTH_ENABLED", False)

    assert auth.initialize_pin() == ""
    assert auth.get_current_pin() is None


def test_initialize_pin_regenerates_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setattr(auth.settings, "PIN_AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "PIN_HASH_FILE", tmp_path / "pin.hash")
    monkeypatch.setattr(auth, "PIN_SALT_FILE", tmp_path / "pin.salt")
    monkeypatch.delenv("JARVIS_PIN", raising=False)
    monkeypatch.delenv("JARVIS_REGEN_PIN", raising=False)
    auth._active_sessions.clear()
    auth._failed_attempts.clear()

    assert auth.set_pin("123456") is True

    pin = auth.initialize_pin()

    assert pin.isdigit()
    assert len(pin) == auth.PIN_LENGTH
    assert auth.get_current_pin() == pin
    assert auth.verify_pin("123456") is None
    assert auth.verify_pin(pin)


def test_initialize_pin_can_reuse_saved_pin_when_regen_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setattr(auth.settings, "PIN_AUTH_ENABLED", True)
    monkeypatch.setattr(auth, "PIN_HASH_FILE", tmp_path / "pin.hash")
    monkeypatch.setattr(auth, "PIN_SALT_FILE", tmp_path / "pin.salt")
    monkeypatch.delenv("JARVIS_PIN", raising=False)
    monkeypatch.setenv("JARVIS_REGEN_PIN", "false")
    auth._active_sessions.clear()
    auth._failed_attempts.clear()

    assert auth.set_pin("123456") is True

    assert auth.initialize_pin() == ""
    assert auth.get_current_pin() is None
    assert auth.verify_pin("123456")


async def test_require_auth_rejects_remote_request_when_pin_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    with pytest.raises(HTTPException) as exc_info:
        await server.require_auth(FakeRequest())

    assert exc_info.value.status_code == 403


async def test_auth_status_reports_remote_lock_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    result = await server.auth_status(FakeRequest())

    assert result == {
        "authenticated": False,
        "local": False,
        "auth_required": True,
    }


async def test_auth_login_rejects_remote_when_pin_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    result = await server.auth_login(FakeRequest(), server.PinRequest(pin=""))

    assert result.status_code == 403


async def test_local_auth_still_short_circuits_when_pin_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    assert await server.require_auth(FakeRequest(host="127.0.0.1")) is True

    status = await server.auth_status(FakeRequest(host="127.0.0.1"))
    assert status == {"authenticated": True, "local": True, "auth_required": False}

    login = await server.auth_login(FakeRequest(host="127.0.0.1"), server.PinRequest(pin=""))
    assert login == {"token": None, "expires_in": 0, "auth_required": False}


async def test_auth_status_still_requires_auth_when_pin_auth_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", True)

    result = await server.auth_status(FakeRequest())

    assert result == {
        "authenticated": False,
        "local": False,
        "auth_required": True,
    }
