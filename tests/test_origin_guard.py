"""Origin checks that stop web pages from driving the loopback API."""

import os

os.environ["JARVIS_REGEN_PIN"] = "false"

import pytest
from fastapi.testclient import TestClient

from jarvis.config import settings
from jarvis.core import server


@pytest.mark.parametrize(
    ("origin", "local", "kwargs", "expected"),
    [
        (None, True, {}, True),  # native client (voice loop, curl)
        ("", True, {}, True),
        (f"http://localhost:{settings.UI_PORT}", True, {}, True),
        (f"http://127.0.0.1:{settings.UI_PORT}/", True, {}, True),
        # Only JARVIS's own UI port is trusted, not any app on a well-known port.
        (f"http://localhost:{settings.UI_PORT + 1}", True, {}, False),
        ("https://evil.example", True, {}, False),
        ("http://localhost.evil.example", True, {}, False),
        # Anyone can mint a trycloudflare subdomain: never trusted on loopback.
        ("https://attacker.trycloudflare.com", True, {}, False),
        ("https://my-tunnel.trycloudflare.com", False, {}, True),
        ("https://x.trycloudflare.com.evil.example", False, {}, False),
        ("chrome-extension://abcdef", True, {}, False),
        ("chrome-extension://abcdef", True, {"allow_extension": True}, True),
        ("null", True, {}, False),
        ("null", True, {"allow_null": True}, True),
    ],
)
def test_origin_allowed(origin, local, kwargs, expected):
    assert server._origin_allowed(origin, local=local, **kwargs) is expected


def test_extension_origin_can_be_pinned(monkeypatch):
    monkeypatch.setenv("JARVIS_EXTENSION_ID", "goodid")
    assert server._origin_allowed("chrome-extension://goodid", local=True, allow_extension=True)
    assert not server._origin_allowed("chrome-extension://otherid", local=True, allow_extension=True)


@pytest.fixture
def client():
    # TestClient connects as host "testclient"; treat it as loopback.
    with TestClient(server.app, client=("127.0.0.1", 50000)) as c:
        yield c


def test_http_request_from_foreign_origin_is_rejected(client):
    resp = client.post("/chat", content=b'{"message":"hi"}', headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    assert resp.json()["error"] == "Origin not allowed."


def test_http_request_without_origin_passes_guard(client):
    resp = client.get("/health/ping")
    assert resp.status_code != 403


def test_ws_from_foreign_origin_is_closed(client):
    from starlette.websockets import WebSocketDisconnect

    for path in ("/ws", "/ws/extension", "/ws/overlay", "/ws/live"):
        with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(
            path, headers={"Origin": "https://evil.example"}
        ) as ws:
            ws.receive_json()
        assert exc.value.code == 4003, path


# Headers the Next.js rewrite adds when the UI is opened on this machine.
NEXT_PROXY_HEADERS = {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost:3000"}


def test_next_proxied_local_request_is_local(client):
    resp = client.get("/auth/status", headers={**NEXT_PROXY_HEADERS, "Origin": "http://localhost:3000"})
    assert resp.json()["local"] is True


def test_tunnel_request_stays_remote(client):
    resp = client.get(
        "/auth/status",
        headers={
            "X-Forwarded-For": "203.0.113.7, 127.0.0.1",
            "CF-Connecting-IP": "203.0.113.7",
            "X-Forwarded-Host": "my-tunnel.trycloudflare.com",
            "Origin": "https://my-tunnel.trycloudflare.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["local"] is False


def test_origin_guard_still_applies_to_next_proxied_local_request(client):
    for origin in ("https://evil.example", "https://attacker.trycloudflare.com"):
        resp = client.post(
            "/chat", content=b'{"message":"hi"}', headers={**NEXT_PROXY_HEADERS, "Origin": origin}
        )
        assert resp.status_code == 403, origin
        assert resp.json()["error"] == "Origin not allowed."


def test_repeated_forwarded_for_header_cannot_hide_a_remote_hop(client):
    resp = client.get(
        "/auth/status",
        headers=[("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-For", "203.0.113.7")],
    )
    assert resp.json()["local"] is False
