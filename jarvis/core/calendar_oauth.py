"""OAuth-backed Google and Outlook calendar provider integrations."""
from __future__ import annotations

import json
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from jarvis.config import settings
from jarvis.core import calendar_accounts
from jarvis.core.secrets import SecretStoreError, delete_secret, get_secret, set_secret


@dataclass(frozen=True)
class CalendarProvider:
    key: str
    display_name: str
    auth_url: str
    token_url: str
    api_base_url: str
    scopes: tuple[str, ...]
    client_id_setting: str
    client_secret_name: str
    token_secret_name: str


PROVIDERS: dict[str, CalendarProvider] = {
    "google": CalendarProvider(
        key="google",
        display_name="Google Calendar",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",  # nosec B106
        api_base_url="https://www.googleapis.com/calendar/v3",
        scopes=(
            "https://www.googleapis.com/auth/calendar.events",
        ),
        client_id_setting="GOOGLE_CALENDAR_CLIENT_ID",
        client_secret_name="GOOGLE_CALENDAR_CLIENT_SECRET",
        token_secret_name="GOOGLE_CALENDAR_TOKEN",
    ),
    "outlook": CalendarProvider(
        key="outlook",
        display_name="Outlook Calendar",
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",  # nosec B106
        api_base_url="https://graph.microsoft.com/v1.0",
        scopes=("offline_access", "Calendars.ReadWrite"),
        client_id_setting="OUTLOOK_CALENDAR_CLIENT_ID",
        client_secret_name="OUTLOOK_CALENDAR_CLIENT_SECRET",
        token_secret_name="OUTLOOK_CALENDAR_TOKEN",
    ),
}


def _provider(provider: str) -> CalendarProvider:
    provider_key = provider.strip().lower()
    if provider_key not in PROVIDERS:
        raise ValueError(f"Unsupported calendar provider: {provider}")
    return PROVIDERS[provider_key]


def _connection(provider: str) -> dict[str, Any]:
    provider_key = provider.strip().lower()
    return next((item for item in calendar_accounts.list_connections() if item.get("provider") == provider_key), {})


def _client_id(provider: CalendarProvider) -> str:
    connection = _connection(provider.key)
    configured = str(connection.get("client_id") or "").strip()
    if configured:
        return configured
    return str(getattr(settings, provider.client_id_setting, "") or "").strip()


def _client_secret(provider: CalendarProvider) -> str:
    configured = str(getattr(settings, provider.client_secret_name, "") or "").strip()
    if configured:
        return configured
    return get_secret(provider.client_secret_name)


def _redirect_uri(provider: CalendarProvider, redirect_uri: str = "") -> str:
    if redirect_uri:
        return redirect_uri
    return f"http://localhost:{settings.API_PORT}/calendar/oauth/{provider.key}/callback"


def _load_token(provider: CalendarProvider) -> dict[str, Any]:
    raw = get_secret(provider.token_secret_name)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_token(provider: CalendarProvider, token: dict[str, Any]) -> None:
    set_secret(provider.token_secret_name, json.dumps(token, sort_keys=True))


def save_credentials(provider: str, client_id: str, client_secret: str = "") -> dict[str, Any]:  # nosec B107
    """Store provider OAuth app credentials."""
    config = _provider(provider)
    client_id = " ".join(client_id.strip().split())
    if not client_id:
        raise ValueError("client_id is required.")
    if client_secret:
        set_secret(config.client_secret_name, client_secret.strip())
        setattr(settings, config.client_secret_name, client_secret.strip())
    setattr(settings, config.client_id_setting, client_id)
    connection = calendar_accounts.update_connection(
        config.key,
        {
            "client_id": client_id,
            "status": "needs_auth",
            "enabled": False,
        },
    )
    return get_provider_status(config.key, connection=connection)


def delete_credentials(provider: str) -> dict[str, Any]:
    config = _provider(provider)
    with suppress(SecretStoreError):
        delete_secret(config.client_secret_name)
    setattr(settings, config.client_secret_name, "")
    setattr(settings, config.client_id_setting, "")
    calendar_accounts.update_connection(config.key, {"client_id": "", "status": "not_connected", "enabled": False})
    return get_provider_status(config.key)


def get_provider_status(provider: str, connection: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _provider(provider)
    connection = connection if connection is not None else _connection(config.key)
    token = _load_token(config)
    return {
        "provider": config.key,
        "name": config.display_name,
        "configured": bool(_client_id(config) and _client_secret(config)),
        "client_id_configured": bool(_client_id(config)),
        "client_secret_configured": bool(_client_secret(config)),
        "connected": bool(token.get("access_token") or token.get("refresh_token")),
        "enabled": bool(connection.get("enabled", False)),
        "status": connection.get("status", "not_connected"),
        "token_expires_at": float(token.get("expires_at", 0) or 0),
        "scopes": list(connection.get("scopes") or config.scopes),
        "last_error": connection.get("last_error", ""),
    }


def build_authorization_url(provider: str, *, redirect_uri: str = "") -> dict[str, Any]:
    """Build an OAuth authorization URL and store a short-lived state nonce."""
    config = _provider(provider)
    client_id = _client_id(config)
    client_secret = _client_secret(config)
    if not client_id or not client_secret:
        raise ValueError(f"{config.display_name} OAuth client ID and secret are required.")

    redirect = _redirect_uri(config, redirect_uri)
    state = calendar_accounts.create_oauth_state(config.key, redirect)
    if state is None:
        raise ValueError(f"Unsupported calendar provider: {provider}")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
    }
    if config.key == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    else:
        params["response_mode"] = "query"
        params["prompt"] = "select_account"

    return {
        "provider": config.key,
        "authorization_url": f"{config.auth_url}?{urlencode(params)}",
        "redirect_uri": redirect,
        "state": state,
        "expires_in": 600,
    }


async def exchange_code(provider: str, *, code: str, state: str) -> dict[str, Any]:
    """Exchange an OAuth authorization code for provider tokens."""
    config = _provider(provider)
    state_record = calendar_accounts.consume_oauth_state(config.key, state)
    if state_record is None:
        raise ValueError("Invalid or expired OAuth state.")

    redirect_uri = str(state_record.get("redirect_uri") or _redirect_uri(config))
    data = {
        "client_id": _client_id(config),
        "client_secret": _client_secret(config),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(config.token_url, data=data)
        response.raise_for_status()
        token = response.json()

    token = _normalize_token(token, config)
    _save_token(config, token)
    connection = calendar_accounts.mark_oauth_connected(
        config.key,
        account_label=config.display_name,
        scopes=str(token.get("scope") or " ".join(config.scopes)).split(),
        token_expires_at=float(token.get("expires_at", 0) or 0),
    )
    return get_provider_status(config.key, connection=connection)


def disconnect(provider: str) -> dict[str, Any]:
    config = _provider(provider)
    with suppress(SecretStoreError):
        delete_secret(config.token_secret_name)
    updates: dict[str, Any] = {"status": "not_connected", "enabled": False}
    updates["token_expires_at"] = int(False)
    calendar_accounts.update_connection(config.key, updates)
    return get_provider_status(config.key)


def _normalize_token(token: dict[str, Any], provider: CalendarProvider, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = previous or {}
    expires_in = int(token.get("expires_in", 3600) or 3600)
    normalized = {
        **previous,
        **token,
        "provider": provider.key,
        "expires_at": time.time() + max(60, expires_in - 60),
    }
    if "refresh_token" not in normalized and previous.get("refresh_token"):
        normalized["refresh_token"] = previous["refresh_token"]
    return normalized


async def get_access_token(provider: str) -> str:
    """Return a valid access token, refreshing it when needed."""
    config = _provider(provider)
    token = _load_token(config)
    if not token:
        raise ValueError(f"{config.display_name} is not connected.")
    if token.get("access_token") and float(token.get("expires_at", 0) or 0) > time.time() + 30:
        return str(token["access_token"])
    refresh_token = str(token.get("refresh_token") or "")
    if not refresh_token:
        calendar_accounts.mark_connection_error(config.key, "Access token expired and no refresh token is available.")
        raise ValueError(f"{config.display_name} needs to be reconnected.")

    data = {
        "client_id": _client_id(config),
        "client_secret": _client_secret(config),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(config.token_url, data=data)
        response.raise_for_status()
        refreshed = response.json()

    token = _normalize_token(refreshed, config, previous=token)
    _save_token(config, token)
    calendar_accounts.mark_oauth_connected(
        config.key,
        account_label=config.display_name,
        scopes=str(token.get("scope") or " ".join(config.scopes)).split(),
        token_expires_at=float(token.get("expires_at", 0) or 0),
    )
    return str(token["access_token"])


async def list_events(provider: str, *, days: int = 1, limit: int = 20) -> dict[str, Any]:
    """Read events from Google Calendar or Outlook via OAuth."""
    config = _provider(provider)
    token = await get_access_token(config.key)
    days = max(1, min(days, 31))
    limit = max(1, min(limit, 50))
    start = datetime.now(UTC)
    end = start + timedelta(days=days)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        if config.key == "google":
            response = await client.get(
                f"{config.api_base_url}/calendars/primary/events",
                headers=headers,
                params={
                    "timeMin": _iso_z(start),
                    "timeMax": _iso_z(end),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": str(limit),
                },
            )
        else:
            response = await client.get(
                f"{config.api_base_url}/me/calendarView",
                headers=headers,
                params={
                    "startDateTime": start.isoformat(),
                    "endDateTime": end.isoformat(),
                    "$orderby": "start/dateTime",
                    "$top": str(limit),
                },
            )
        response.raise_for_status()
        payload = response.json()

    events = _normalize_events(config.key, payload)
    return {"provider": config.key, "events": events, "count": len(events)}


async def create_event(
    provider: str,
    *,
    title: str,
    start: str,
    end: str,
    timezone: str = "UTC",
    location: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Create a provider calendar event. Caller is responsible for approval policy."""
    config = _provider(provider)
    token = await get_access_token(config.key)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        if config.key == "google":
            body = {
                "summary": title,
                "description": notes,
                "location": location,
                "start": {"dateTime": start, "timeZone": timezone},
                "end": {"dateTime": end, "timeZone": timezone},
            }
            response = await client.post(f"{config.api_base_url}/calendars/primary/events", headers=headers, json=body)
        else:
            body = {
                "subject": title,
                "body": {"contentType": "text", "content": notes},
                "location": {"displayName": location},
                "start": {"dateTime": start, "timeZone": timezone},
                "end": {"dateTime": end, "timeZone": timezone},
            }
            response = await client.post(f"{config.api_base_url}/me/events", headers=headers, json=body)
        response.raise_for_status()
        event = response.json()
    return {"provider": config.key, "event": _normalize_event(config.key, event)}


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _normalize_events(provider: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if provider == "google":
        return [_normalize_event(provider, item) for item in payload.get("items", [])]
    return [_normalize_event(provider, item) for item in payload.get("value", [])]


def _normalize_event(provider: str, item: dict[str, Any]) -> dict[str, Any]:
    if provider == "google":
        return {
            "id": item.get("id", ""),
            "title": item.get("summary", "(Untitled)"),
            "start": item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", ""),
            "end": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date", ""),
            "location": item.get("location", ""),
            "url": item.get("htmlLink", ""),
        }
    return {
        "id": item.get("id", ""),
        "title": item.get("subject", "(Untitled)"),
        "start": item.get("start", {}).get("dateTime", ""),
        "end": item.get("end", {}).get("dateTime", ""),
        "location": item.get("location", {}).get("displayName", ""),
        "url": item.get("webLink", ""),
    }
