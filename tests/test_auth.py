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


# What the Next.js rewrite (/jarvis-api/* -> 127.0.0.1:8741) adds for a browser on this Mac.
NEXT_PROXY_HEADERS = {
    "x-forwarded-for": "127.0.0.1",
    "x-forwarded-host": "localhost:3000",
    "x-forwarded-port": "3000",
    "x-forwarded-proto": "http",
}


@pytest.mark.parametrize(
    ("host", "headers", "expected"),
    [
        ("127.0.0.1", {}, True),  # direct loopback
        ("::1", {}, True),
        ("203.0.113.10", {}, False),  # direct remote
        # Next-proxied request from a browser on this machine.
        ("127.0.0.1", NEXT_PROXY_HEADERS, True),
        ("127.0.0.1", {**NEXT_PROXY_HEADERS, "x-forwarded-for": "::1"}, True),
        ("127.0.0.1", {**NEXT_PROXY_HEADERS, "x-forwarded-for": "::ffff:127.0.0.1"}, True),
        ("127.0.0.1", {**NEXT_PROXY_HEADERS, "x-forwarded-for": "::1, 127.0.0.1"}, True),
        ("127.0.0.1", {**NEXT_PROXY_HEADERS, "x-forwarded-host": "[::1]:3000"}, True),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "x-real-ip": "127.0.0.1"}, True),
        # Cloudflare Tunnel -> Next -> backend: also a loopback peer, but remote.
        (
            "127.0.0.1",
            {
                "x-forwarded-for": "203.0.113.7, 127.0.0.1",
                "cf-connecting-ip": "203.0.113.7",
                "x-forwarded-host": "my-tunnel.trycloudflare.com",
            },
            False,
        ),
        # A client-spoofed loopback XFF does not outweigh the Cloudflare headers.
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "cf-connecting-ip": "203.0.113.7"}, False),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "cf-connecting-ip": "127.0.0.1"}, False),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "true-client-ip": "127.0.0.1"}, False),
        # Any non-loopback hop in the chain means a remote client.
        ("127.0.0.1", {"x-forwarded-for": "203.0.113.7"}, False),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1, 192.168.1.20"}, False),
        ("127.0.0.1", {"x-forwarded-for": "192.168.1.20, 127.0.0.1"}, False),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "x-real-ip": "203.0.113.7"}, False),
        ("127.0.0.1", {"x-real-ip": "203.0.113.7"}, False),
        # Unparseable or empty entries are never assumed to be loopback.
        ("127.0.0.1", {"x-forwarded-for": "unknown"}, False),
        ("127.0.0.1", {"x-forwarded-for": ""}, False),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1,"}, False),
        # The UI was reached under a non-local hostname (another tunnel/proxy).
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "x-forwarded-host": "jarvis.example.com"}, False),
        ("127.0.0.1", {"x-forwarded-for": "127.0.0.1", "x-forwarded-host": "localhost.evil.example"}, False),
        # RFC 7239 Forwarded is not sent by Next; its presence means another proxy.
        ("127.0.0.1", {"forwarded": "for=127.0.0.1"}, False),
        # A loopback chain cannot make a remote peer local.
        ("203.0.113.10", {"x-forwarded-for": "127.0.0.1"}, False),
    ],
)
def test_client_is_local(host, headers, expected):
    assert server._client_is_local(FakeRequest(host=host, headers=headers)) is expected


def test_proxied_loopback_respects_disabled_local_bypass(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_DISABLE_LOCAL_BYPASS", "1")

    assert server._client_is_local(FakeRequest(host="127.0.0.1", headers=NEXT_PROXY_HEADERS)) is False


async def test_next_proxied_local_request_bypasses_pin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server.auth.settings, "PIN_AUTH_ENABLED", True)

    status = await server.auth_status(FakeRequest(host="127.0.0.1", headers=NEXT_PROXY_HEADERS))

    assert status == {"authenticated": True, "local": True, "auth_required": True}
