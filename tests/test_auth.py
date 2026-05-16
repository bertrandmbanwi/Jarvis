from types import SimpleNamespace

import pytest

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


async def test_require_auth_allows_remote_request_when_pin_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    assert await server.require_auth(FakeRequest()) is True


async def test_auth_status_reports_no_pin_requirement_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    result = await server.auth_status(FakeRequest())

    assert result == {
        "authenticated": True,
        "local": False,
        "auth_required": False,
    }


async def test_auth_login_short_circuits_when_pin_auth_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", False)

    result = await server.auth_login(FakeRequest(), server.PinRequest(pin=""))

    assert result == {"token": None, "expires_in": 0, "auth_required": False}


async def test_auth_status_still_requires_auth_when_pin_auth_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", True)

    result = await server.auth_status(FakeRequest())

    assert result == {
        "authenticated": False,
        "local": False,
        "auth_required": True,
    }
