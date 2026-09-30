"""HTTP/WebSocket trust decisions shared by the API routes.

Which browser origins are JARVIS clients, whether a connection is a genuine
loopback client, and the ``require_auth`` dependency for remote access.
"""
import ipaddress
import logging
import os
import re

from fastapi import HTTPException, Request

from jarvis.config import settings
from jarvis.core import auth

logger = logging.getLogger("jarvis.server")

# Only the ports JARVIS itself serves on are trusted. start.sh exports the UI
# port it actually chose (it picks a free one when the default is taken), so
# another local app that happens to sit on port 3000 is not a trusted origin.
_cors_origins = [
    f"http://localhost:{settings.UI_PORT}",
    f"http://127.0.0.1:{settings.UI_PORT}",
    f"http://localhost:{settings.API_PORT}",
    f"http://127.0.0.1:{settings.API_PORT}",
]

_tunnel_domain = os.environ.get("JARVIS_TUNNEL_DOMAIN", "")
if _tunnel_domain:
    _cors_origins.append(f"https://{_tunnel_domain}")

# Extra browser origins (e.g. a LAN address for the UI), comma-separated.
_cors_origins.extend(
    o.strip().rstrip("/") for o in os.environ.get("JARVIS_ALLOWED_ORIGINS", "").split(",") if o.strip()
)

_TUNNEL_ORIGIN_RE = re.compile(r"^https://[a-z0-9-]+\.trycloudflare\.com$")


def _origin_allowed(
    origin: str | None,
    *,
    local: bool,
    allow_extension: bool = False,
    allow_null: bool = False,
) -> bool:
    """Return True if a request's Origin header belongs to a JARVIS client.

    Browsers always attach Origin to WebSocket handshakes and cross-origin
    requests, and page scripts cannot forge it. Native clients (the voice
    loop, curl, the Swift overlay's host) send none. A loopback peer address
    alone is NOT proof of trust: any web page open in the user's browser also
    connects from 127.0.0.1, so untrusted origins are rejected outright.

    ``*.trycloudflare.com`` origins are only accepted on forwarded (tunnel)
    connections, which must pass PIN auth anyway. Anyone can mint such a
    subdomain, so on a local connection it would be an auth bypass.
    """
    if not origin:
        return True
    origin = origin.rstrip("/")
    if origin in _cors_origins:
        return True
    if not local and _TUNNEL_ORIGIN_RE.match(origin):
        return True
    if allow_null and origin in ("null", "file://"):
        return True
    if allow_extension and origin.startswith("chrome-extension://"):
        pinned = os.environ.get("JARVIS_EXTENSION_ID", "").strip()
        return not pinned or origin == f"chrome-extension://{pinned}"
    return False


# Set only by a CDN/tunnel edge or a non-Next proxy; any of them means the
# loopback peer address is the proxy — not the real (remote) client.
_REMOTE_PROXY_HEADERS = ("cf-connecting-ip", "true-client-ip", "forwarded")
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "[::1]"}


def _is_loopback_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_loopback


def _header_values(headers, name: str) -> list[str]:
    """Every value of a header; ``headers[name]`` alone would hide a repeated line."""
    if hasattr(headers, "getlist"):
        return list(headers.getlist(name))
    return [headers[name]] if name in headers else []


def _relayed_for_remote_client(headers) -> bool:
    """Return True unless every proxy header says the client is on this machine.

    The web UI reaches the API through the Next.js rewrite, which adds
    ``X-Forwarded-For``/``X-Forwarded-Host`` even for a browser on this Mac. A
    tunnel (Cloudflare -> Next -> backend) arrives from the same loopback peer,
    but the edge sets ``CF-Connecting-IP`` and puts the real client address in
    ``X-Forwarded-For``, which Next appends to rather than replaces. So a
    request is only local when no edge header is present, every address in the
    chain is loopback, and the UI itself was opened under a loopback hostname.
    """
    if any(name in headers for name in _REMOTE_PROXY_HEADERS):
        return True
    for name in ("x-forwarded-for", "x-real-ip"):
        hops = ",".join(_header_values(headers, name)).split(",") if name in headers else []
        if not all(_is_loopback_address(hop) for hop in hops):
            return True
    return any(
        re.sub(r":\d+$", "", host.strip().lower()) not in _LOCAL_HOSTNAMES
        for host in _header_values(headers, "x-forwarded-host")
    )


def _client_is_local(conn) -> bool:
    """Return True only for a genuine loopback client, direct or via the local UI proxy.

    Accepts a Request or WebSocket (both expose ``.client`` and ``.headers``).
    """
    client_host = conn.client.host if conn.client else ""
    return auth.is_local_request(client_host, forwarded=_relayed_for_remote_client(conn.headers))


async def require_auth(request: Request) -> bool:
    """FastAPI dependency for local-bypass / remote-required auth.

    Local connections bypass auth. Remote connections always require PIN auth to
    be enabled and a valid session token via header, cookie, or query param.
    """
    if _client_is_local(request):
        return True

    if not auth.pin_auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Remote access requires PIN authentication. Set JARVIS_PIN_AUTH_ENABLED=true.",
        )

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if auth.validate_token(token):
            return True

    token = request.cookies.get("jarvis_token", "")
    if token and auth.validate_token(token):
        return True

    # Query-string tokens leak via access logs, browser history, and Referer
    # headers, so they are refused by default. Opt in with JARVIS_ALLOW_QUERY_TOKEN
    # for clients that cannot set an Authorization header or cookie.
    if os.getenv("JARVIS_ALLOW_QUERY_TOKEN", "").strip().lower() in {"1", "true", "yes"}:
        token = request.query_params.get("token", "")
        if token and auth.validate_token(token):
            logger.warning("Auth via query param token (less secure; enabled by JARVIS_ALLOW_QUERY_TOKEN).")
            return True

    raise HTTPException(status_code=401, detail="Authentication required. Please log in with your PIN.")
