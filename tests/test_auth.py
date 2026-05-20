from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
