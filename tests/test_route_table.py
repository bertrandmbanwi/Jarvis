"""Every HTTP route rejects unauthenticated remote clients unless it is explicitly public.

Behavioural on purpose: FastAPI's internal representation of included
routers changes between versions, but a request either gets through or not.
"""

import os
import re

os.environ["JARVIS_REGEN_PIN"] = "false"

import pytest
from fastapi.testclient import TestClient

from jarvis.core import server

PUBLIC_PATHS = {"/auth/login", "/auth/status", "/auth/logout", "/health/ping"}
# A request relayed by the tunnel: loopback peer, but forwarded -> treated as remote.
REMOTE_HEADERS = {"x-forwarded-for": "203.0.113.7", "x-jarvis-client": "test"}


def _operations():
    for path, methods in server.app.openapi()["paths"].items():
        for method in methods:
            if path not in PUBLIC_PATHS:
                yield method.upper(), path


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app, client=("127.0.0.1", 50000))


def test_openapi_lists_the_split_routers():
    paths = set(server.app.openapi()["paths"])
    assert {"/workflows/overview", "/product/overview", "/calendar/policy", "/team/members", "/chat"} <= paths


@pytest.mark.parametrize(("method", "path"), sorted(set(_operations())))
def test_route_rejects_unauthenticated_remote_client(client, method, path):
    concrete = re.sub(r"\{[^}]+\}", "x", path)
    resp = client.request(method, concrete, headers=REMOTE_HEADERS, json={})
    assert resp.status_code in (401, 403), f"{method} {path} -> {resp.status_code}"
