"""Every HTTP route requires auth unless it is explicitly public."""

import os

os.environ["JARVIS_REGEN_PIN"] = "false"

from fastapi.routing import APIRoute

from jarvis.core import server
from jarvis.core.http_security import require_auth

PUBLIC_PATHS = {
    "/auth/login", "/auth/status", "/auth/logout", "/health/ping",
    "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc",
}


def _requires_auth(route: APIRoute) -> bool:
    return any(dep.call is require_auth for dep in route.dependant.dependencies)


def test_all_non_public_http_routes_require_auth():
    unprotected = sorted(
        route.path
        for route in server.app.routes
        if isinstance(route, APIRoute) and route.path not in PUBLIC_PATHS and not _requires_auth(route)
    )
    assert unprotected == []


def test_split_routers_are_mounted():
    paths = {getattr(route, "path", "") for route in server.app.routes}
    assert {"/workflows/overview", "/product/overview", "/calendar/policy", "/team/members", "/chat"} <= paths
