"""Team members, calendar connections/OAuth/scheduling, and mail shortcuts."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jarvis.core import calendar_accounts, calendar_oauth, team
from jarvis.core.api_models import (
    CalendarConnectionRequest,
    CalendarOAuthCredentialsRequest,
    CalendarOAuthStartRequest,
    CalendarPolicyRequest,
    CalendarProviderEventsRequest,
    ScheduleAssessmentRequest,
    TeamMemberRequest,
)
from jarvis.core.http_security import require_auth

router = APIRouter()


@router.get("/team", dependencies=[Depends(require_auth)])
async def get_team():
    """Get local team mode, members, and role capability matrix."""
    return team.get_team()


@router.get("/team/members", dependencies=[Depends(require_auth)])
async def list_team_members():
    """List team members."""
    members = team.list_members()
    return {"members": members, "count": len(members)}


@router.put("/team/members", dependencies=[Depends(require_auth)])
async def upsert_team_member(request: TeamMemberRequest):
    """Create or update a team member record."""
    if not request.name.strip():
        return JSONResponse(status_code=400, content={"error": "Member name is required."})
    member = team.upsert_member(
        name=request.name,
        email=request.email,
        role=request.role,
        member_id=request.member_id,
        status=request.status,
    )
    return member


@router.delete("/team/members/{member_id}", dependencies=[Depends(require_auth)])
async def delete_team_member(member_id: str):
    """Delete a team member, except the local owner."""
    if not team.delete_member(member_id):
        return JSONResponse(status_code=404, content={"error": "Member not found or cannot be deleted."})
    return {"status": "deleted"}


@router.get("/team/permissions", dependencies=[Depends(require_auth)])
async def team_permissions():
    """Get role capability mappings."""
    return {"roles": team.permission_matrix()}


@router.get("/calendar/connections", dependencies=[Depends(require_auth)])
async def get_calendar_connections():
    """Get calendar provider connection metadata and scheduling policy."""
    return calendar_accounts.get_state()


@router.put("/calendar/connections", dependencies=[Depends(require_auth)])
async def upsert_calendar_connection(request: CalendarConnectionRequest):
    """Create or update calendar provider connection metadata."""
    connection = calendar_accounts.upsert_connection(
        provider=request.provider,
        account_label=request.account_label,
        enabled=request.enabled,
        status=request.status,
        scopes=request.scopes,
    )
    if connection is None:
        return JSONResponse(status_code=400, content={"error": "Unsupported calendar provider."})
    return connection


@router.delete("/calendar/connections/{provider}", dependencies=[Depends(require_auth)])
async def delete_calendar_connection(provider: str):
    """Remove calendar provider connection metadata."""
    if not calendar_accounts.remove_connection(provider):
        return JSONResponse(status_code=404, content={"error": "Calendar connection not found."})
    return {"status": "deleted"}


@router.get("/calendar/oauth/{provider}/status", dependencies=[Depends(require_auth)])
async def get_calendar_oauth_status(provider: str):
    """Get OAuth configuration and token status for a provider."""
    try:
        return calendar_oauth.get_provider_status(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.put("/calendar/oauth/{provider}/credentials", dependencies=[Depends(require_auth)])
async def save_calendar_oauth_credentials(provider: str, request: CalendarOAuthCredentialsRequest):
    """Save OAuth app credentials for Google or Outlook Calendar."""
    try:
        return calendar_oauth.save_credentials(provider, request.client_id, request.client_secret)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.delete("/calendar/oauth/{provider}/credentials", dependencies=[Depends(require_auth)])
async def delete_calendar_oauth_credentials(provider: str):
    """Remove OAuth app credentials for a provider."""
    try:
        return calendar_oauth.delete_credentials(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.post("/calendar/oauth/{provider}/start", dependencies=[Depends(require_auth)])
async def start_calendar_oauth(provider: str, request: CalendarOAuthStartRequest):
    """Build a provider OAuth authorization URL."""
    try:
        return calendar_oauth.build_authorization_url(provider, redirect_uri=request.redirect_uri)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.get("/calendar/oauth/{provider}/callback", dependencies=[Depends(require_auth)])
async def calendar_oauth_callback(provider: str, code: str = "", state: str = "", error: str = ""):
    """OAuth redirect callback for Google or Outlook Calendar."""
    if error:
        calendar_accounts.mark_connection_error(provider, error)
        return JSONResponse(status_code=400, content={"error": error})
    if not code or not state:
        return JSONResponse(status_code=400, content={"error": "OAuth callback requires code and state."})
    try:
        status = await calendar_oauth.exchange_code(provider, code=code, state=state)
        return {"status": "connected", "provider": provider, "connection": status}
    except Exception as exc:
        calendar_accounts.mark_connection_error(provider, str(exc))
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.post("/calendar/oauth/{provider}/disconnect", dependencies=[Depends(require_auth)])
async def disconnect_calendar_oauth(provider: str):
    """Disconnect a provider calendar account."""
    try:
        return calendar_oauth.disconnect(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.get("/calendar/providers/{provider}/events", dependencies=[Depends(require_auth)])
async def list_provider_events(provider: str, days: int = 1, limit: int = 20, calendar_id: str = ""):
    """List events from an OAuth-backed calendar provider."""
    try:
        return await calendar_oauth.list_events(provider, days=days, limit=limit, calendar_id=calendar_id)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.post("/calendar/providers/{provider}/events", dependencies=[Depends(require_auth)])
async def create_provider_event(provider: str, request: CalendarProviderEventsRequest):
    """Create an event through an OAuth-backed calendar provider."""
    assessment = calendar_accounts.assess_scheduling_request(
        title=request.title,
        start=request.start,
        end=request.end,
        attendees=request.attendees,
        provider=provider,
    )
    if assessment["requires_confirmation"]:
        return JSONResponse(status_code=409, content={"error": "Scheduling requires confirmation.", "assessment": assessment})
    try:
        return await calendar_oauth.create_event(
            provider,
            title=request.title,
            start=request.start,
            end=request.end,
            timezone=request.timezone,
            location=request.location,
            notes=request.notes,
            attendees=request.attendees,
            calendar_id=request.calendar_id,
        )
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.put("/calendar/policy", dependencies=[Depends(require_auth)])
async def update_calendar_policy(request: CalendarPolicyRequest):
    """Update safe scheduling policy."""
    updates = request.model_dump(exclude_none=True)
    return calendar_accounts.update_policy(updates)


@router.post("/calendar/scheduling/assess", dependencies=[Depends(require_auth)])
async def assess_calendar_scheduling(request: ScheduleAssessmentRequest):
    """Assess whether a calendar event can be safely auto-scheduled."""
    if not request.title.strip():
        return JSONResponse(status_code=400, content={"error": "Event title is required."})
    return calendar_accounts.assess_scheduling_request(
        title=request.title,
        start=request.start,
        end=request.end,
        attendees=request.attendees,
        provider=request.provider,
    )


@router.get("/calendar", dependencies=[Depends(require_auth)])
async def get_calendar_today():
    """Quick access to today's calendar events."""
    from jarvis.tools.calendar_email import get_upcoming_events
    events = await get_upcoming_events(days=1)
    return {"events": events}


@router.get("/mail/unread", dependencies=[Depends(require_auth)])
async def get_mail_unread():
    """Quick access to unread email count."""
    from jarvis.tools.calendar_email import get_unread_count
    count = await get_unread_count()
    return {"unread": count}
