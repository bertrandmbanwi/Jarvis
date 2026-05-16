"""
JARVIS FastAPI Server
HTTP + WebSocket API for interacting with JARVIS.
Used by the UI and can also be used by iPhone/external clients.
"""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jarvis.config import settings
from jarvis.core import (
    anthropic_batch,
    auth,
    calendar_accounts,
    calendar_oauth,
    cost_tracker,
    feedback,
    jobs,
    routines,
    team,
    workflow_scheduler,
    workflows,
)
from jarvis.core import profile as user_profile
from jarvis.core.brain import JarvisBrain
from jarvis.core.permissions import TOOL_PERMISSIONS, list_tool_audit, summarize_permissions
from jarvis.core.settings_api import settings_router
from jarvis.core.tracing import get_trace_id, record_event, reset_trace_id, set_trace_id, trace_span
from jarvis.tools import chrome_extension

logger = logging.getLogger("jarvis.server")
EMPTY_CHUNK = ""

# Global brain instance
brain = JarvisBrain()

# Voice components set by run_full for browser TTS triggering
_speaker = None
_listener = None

# Desktop overlay WebSocket clients (lightweight, no auth required for localhost)
_overlay_clients: list[WebSocket] = []
_overlay_state: str = "idle"  # idle, listening, thinking, speaking
_overlay_text: str = ""  # latest assistant response text for overlay display
_overlay_user_text: str = ""  # latest user utterance for overlay display


async def broadcast_overlay_state(
    new_state: str,
    text: str | None = None,
    user_text: str | None = None,
    amplitude_envelope: list[float] | None = None,
    audio_duration: float = 0.0,
    voice_speaking: bool | None = None,
):
    """Broadcast state change to all connected desktop overlay clients.

    Args:
        new_state: One of idle, listening, thinking, speaking.
        text: Optional assistant response text to display on the overlay.
        user_text: Optional user utterance to display on the overlay.
        amplitude_envelope: Optional normalized TTS amplitude samples.
        audio_duration: Duration in seconds for the amplitude envelope.
        voice_speaking: Whether voice playback is currently active.
    """
    global _overlay_state, _overlay_text, _overlay_user_text
    _overlay_state = new_state
    if text is not None:
        _overlay_text = text
    if user_text is not None:
        _overlay_user_text = user_text
    if not _overlay_clients:
        return
    payload: dict = {"state": new_state, "text": _overlay_text, "userText": _overlay_user_text}
    if voice_speaking is not None:
        payload["voiceSpeaking"] = voice_speaking
    if amplitude_envelope and audio_duration > 0:
        payload["amplitudeEnvelope"] = amplitude_envelope
        payload["audioDuration"] = audio_duration
    dead = []
    for ws in _overlay_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _overlay_clients.remove(ws)


def set_voice_components(speaker, listener=None):
    """Register voice speaker/listener for WebSocket TTS triggering."""
    global _speaker, _listener
    _speaker = speaker
    _listener = listener
    logger.info("Voice components registered with server (speaker=%s, listener=%s)",
                type(speaker).__name__ if speaker else None,
                type(listener).__name__ if listener else None)


async def _activate_voice_from_overlay(websocket: WebSocket) -> None:
    """Start one microphone capture from the desktop overlay hotkey."""
    if _speaker:
        with suppress(Exception):
            _speaker.stop_speaking()

    if _listener is None or not hasattr(_listener, "request_activation"):
        await websocket.send_json({
            "activationAccepted": False,
            "error": "Voice listener is not ready.",
        })
        await broadcast_overlay_state("idle")
        return

    with suppress(Exception):
        _listener.set_speaking(False, open_followup=False)

    accepted = bool(_listener.request_activation())
    await websocket.send_json({"activationAccepted": accepted})

    if accepted:
        await broadcast_overlay_state("listening", text="", user_text="")
    else:
        await broadcast_overlay_state("idle")


class ClientInfo:
    """Metadata about a connected WebSocket client."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.device_type: str = "unknown"  # "phone", "tablet", "desktop", "unknown"
        self.device_name: str = ""         # user-friendly name, e.g. "iPhone 15"
        self.wants_audio: bool = True      # whether this client wants TTS audio
        self.connected_at: float = time.time()
        self.last_activity: float = time.time()

    def to_dict(self) -> dict:
        """Serialize client info for API responses."""
        return {
            "device_type": self.device_type,
            "device_name": self.device_name,
            "wants_audio": self.wants_audio,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "uptime_seconds": round(time.time() - self.connected_at, 1),
        }


class ConnectionManager:
    """Tracks active WebSocket clients with device metadata for smart routing.

    Each client can register with device type and audio preferences.
    Supports device-targeted audio routing, audio interruption, and
    connection health monitoring.
    """

    def __init__(self):
        self.active: list[WebSocket] = []
        self._clients: dict[WebSocket, ClientInfo] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        await self._prune_stale()
        self.active.append(ws)
        self._clients[ws] = ClientInfo(ws)
        logger.info("WebSocket client connected. Total: %d", len(self.active))

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        self._clients.pop(ws, None)
        logger.info("WebSocket client disconnected. Total: %d", len(self.active))

    def register_client(self, ws: WebSocket, info: dict):
        """Update client metadata after a registration message.

        Expected fields in info:
            device_type: "phone" | "tablet" | "desktop"
            device_name: human-readable name (optional)
            wants_audio: bool (default True)
        """
        client = self._clients.get(ws)
        if not client:
            return
        if "device_type" in info:
            client.device_type = str(info["device_type"])
        if "device_name" in info:
            client.device_name = str(info["device_name"])
        if "wants_audio" in info:
            client.wants_audio = bool(info["wants_audio"])
        logger.info(
            "Client registered: type=%s, name='%s', wants_audio=%s",
            client.device_type, client.device_name, client.wants_audio,
        )

    def get_client_info(self, ws: WebSocket) -> ClientInfo | None:
        """Get metadata for a connected client."""
        return self._clients.get(ws)

    def get_audio_clients(self, exclude: WebSocket | None = None) -> list[WebSocket]:
        """Return all clients that want audio, optionally excluding one."""
        return [
            ws for ws, info in self._clients.items()
            if info.wants_audio and ws is not exclude and ws in self.active
        ]

    def get_connected_devices(self) -> list[dict]:
        """Return a summary of all connected devices."""
        return [info.to_dict() for info in self._clients.values()]

    def touch(self, ws: WebSocket):
        """Update last_activity timestamp for a client."""
        client = self._clients.get(ws)
        if client:
            client.last_activity = time.time()

    async def _prune_stale(self):
        """Remove connections that are no longer alive."""
        stale = []
        for ws in self.active:
            try:
                await ws.send_json({"ping": True})
            except Exception:
                stale.append(ws)
        for ws in stale:
            if ws in self.active:
                self.active.remove(ws)
            self._clients.pop(ws, None)
        if stale:
            logger.info("Pruned %d stale WebSocket connection(s). Active: %d",
                        len(stale), len(self.active))

    async def broadcast_json(self, data: dict, exclude: WebSocket | None = None):
        """Send a JSON message to all connected clients.

        Args:
            data: JSON-serializable dict to send
            exclude: Optional WebSocket to skip (used for device-targeted routing)
        """
        disconnected = []
        for ws in self.active:
            if ws is exclude:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def broadcast_to_audio_clients(
        self, data: dict, exclude: WebSocket | None = None
    ):
        """Send a JSON message only to clients that want audio.

        Used for terminal-originated voice responses where we want to send
        audio to all clients that opted in, but skip animation-only clients.
        """
        disconnected = []
        for ws, info in list(self._clients.items()):
            if ws is exclude or not info.wants_audio or ws not in self.active:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, data: dict):
        """Send a JSON message to a specific client only."""
        try:
            await ws.send_json(data)
        except Exception:
            self.disconnect(ws)


ws_manager = ConnectionManager()


async def broadcast_voice_interaction(user_text: str, response: str):
    """
    Called by the voice pipeline to push voice interactions to the UI.
    Sends the complete response immediately (no word-by-word simulation)
    since the voice is already speaking it aloud.
    """
    if not ws_manager.active:
        logger.info("No active WebSocket clients; skipping voice broadcast.")
        return

    logger.info("Broadcasting voice interaction to %d UI client(s).", len(ws_manager.active))

    await ws_manager.broadcast_json({
        "voice_user_message": user_text,
    })

    await asyncio.sleep(0.05)

    await ws_manager.broadcast_json({
        "token": response,
        "done": False,
    })

    await asyncio.sleep(0.02)

    await ws_manager.broadcast_json({
        "token": EMPTY_CHUNK,
        "done": True,
        "full_response": response,
        "backend": brain.llm.active_backend,
        "session_cost": brain.llm.get_cost_summary(),
        "source": "voice",
    })


async def broadcast_voice_state(
    speaking: bool,
    amplitude_envelope: list[float] | None = None,
    audio_duration: float = 0.0,
    audio_base64: str | None = None,
    target_ws: WebSocket | None = None,
    audio_format: str = "audio/wav",
):
    """Signal to the UI whether TTS is actively speaking aloud.

    Called before speaker.speak() starts (speaking=True) and after
    it finishes (speaking=False). The UI uses this to keep the
    orb in the speaking animation for the full duration of the voice.

    When speaking=True, optionally includes:
    - amplitude_envelope: for audio-reactive visualization
    - audio_base64: WAV audio encoded as base64 for browser playback

    Device-targeted audio routing (smart routing):
    - voice_speaking + amplitude_envelope are broadcast to ALL clients (orb animation)
    - voice_audio (the heavy WAV payload) routing depends on the origin:
      1. Browser-originated (target_ws set): audio to requesting client only
      2. Terminal-originated (target_ws=None): audio to all clients that
         registered with wants_audio=True (respects per-device preferences)
    """
    await broadcast_overlay_state(
        "speaking" if speaking else "idle",
        text=None if speaking else "",
        user_text=None if speaking else "",
        amplitude_envelope=amplitude_envelope if speaking else None,
        audio_duration=audio_duration if speaking else 0.0,
        voice_speaking=speaking,
    )

    if not ws_manager.active:
        return

    base_payload: dict = {"voice_speaking": speaking}
    if speaking and amplitude_envelope:
        base_payload["amplitude_envelope"] = amplitude_envelope
        base_payload["audio_duration"] = audio_duration

    if speaking and audio_base64 and target_ws:
        audio_size_kb = len(audio_base64) // 1024
        logger.info(
            "Sending voice_audio (%d KB) to target client. "
            "Broadcasting animation to %d other client(s).",
            audio_size_kb, len(ws_manager.active) - 1,
        )
        audio_payload = {**base_payload, "voice_audio": audio_base64, "audio_format": audio_format}
        await ws_manager.send_to(target_ws, audio_payload)
        await ws_manager.broadcast_json(base_payload, exclude=target_ws)
    elif speaking and audio_base64:
        audio_size_kb = len(audio_base64) // 1024
        audio_clients = ws_manager.get_audio_clients()
        non_audio_count = len(ws_manager.active) - len(audio_clients)

        if audio_clients and non_audio_count > 0:
            logger.info(
                "Sending voice_audio (%d KB) to %d audio client(s), "
                "animation to %d non-audio client(s).",
                audio_size_kb, len(audio_clients), non_audio_count,
            )
            audio_payload = {**base_payload, "voice_audio": audio_base64, "audio_format": audio_format}
            for ws in audio_clients:
                await ws_manager.send_to(ws, audio_payload)
            for ws in ws_manager.active:
                if ws not in audio_clients:
                    await ws_manager.send_to(ws, base_payload)
        else:
            logger.info(
                "Broadcasting voice_audio (%d KB) to ALL %d client(s) (terminal voice).",
                audio_size_kb, len(ws_manager.active),
            )
            base_payload["voice_audio"] = audio_base64
            base_payload["audio_format"] = audio_format
            await ws_manager.broadcast_json(base_payload)
    else:
        await ws_manager.broadcast_json(base_payload)


async def broadcast_voice_chunk(
    chunk_base64: str,
    chunk_index: int,
    is_last: bool,
    chunk_envelope: list[float],
    chunk_duration: float,
    target_ws: WebSocket | None = None,
    audio_format: str = "audio/wav",
):
    """Send a streamed audio chunk to browser clients.

    Called by the speaker as each chunk of audio becomes available,
    enabling faster time-to-first-audio. The browser queues chunks
    and plays them sequentially.

    Args:
        chunk_base64: audio chunk encoded as base64 (WAV or Opus/WebM)
        chunk_index: sequential chunk number (0-based)
        is_last: True if this is the final chunk
        chunk_envelope: amplitude envelope for this chunk
        chunk_duration: duration of this chunk in seconds
        target_ws: send only to this client (browser-originated), or all if None
        audio_format: MIME type of the audio (e.g., "audio/wav", "audio/webm;codecs=opus")
    """
    if chunk_envelope and chunk_duration > 0:
        await broadcast_overlay_state(
            "speaking",
            amplitude_envelope=chunk_envelope,
            audio_duration=chunk_duration,
            voice_speaking=True,
        )

    if not ws_manager.active:
        return

    payload = {
        "voice_audio_chunk": {
            "audio": chunk_base64,
            "index": chunk_index,
            "is_last": is_last,
            "envelope": chunk_envelope,
            "duration": chunk_duration,
            "format": audio_format,
        }
    }

    if target_ws:
        await ws_manager.send_to(target_ws, payload)
    else:
        # Terminal-originated: send to audio-enabled clients only
        audio_clients = ws_manager.get_audio_clients()
        if audio_clients:
            for ws in audio_clients:
                await ws_manager.send_to(ws, payload)
        else:
            await ws_manager.broadcast_json(payload)


async def broadcast_plan_progress(event: dict):
    """Broadcast a task plan progress event to all connected UI clients.

    Called by JarvisBrain when a plan is created, subtasks start/complete/fail,
    or the overall plan finishes. The UI can render a progress indicator.

    Event types:
        plan_created, subtask_started, subtask_completed,
        subtask_failed, subtask_skipped, plan_completed
    """
    if not ws_manager.active:
        return
    payload = {"plan_progress": event}
    await ws_manager.broadcast_json(payload)


async def _deliver_proactive_suggestion(suggestion):
    """Deliver a proactive suggestion from the background engine.

    Broadcasts the suggestion text to all connected UI clients via WebSocket.
    Optionally speaks it aloud via TTS if the suggestion is marked as spoken
    and a voice speaker is available.
    """

    if not ws_manager.active:
        logger.debug("No WebSocket clients for proactive suggestion; skipping.")
        return

    logger.info(
        "Delivering proactive suggestion [%s]: %s",
        suggestion.category.value,
        suggestion.message[:80],
    )

    await ws_manager.broadcast_json({
        "proactive_suggestion": {
            "category": suggestion.category.value,
            "message": suggestion.message,
            "priority": suggestion.priority,
            "spoken": suggestion.spoken,
            "timestamp": suggestion.timestamp,
        }
    })

    if suggestion.spoken and _speaker:
        try:
            async def on_audio_ready(envelope, duration, audio_b64=None):
                await broadcast_voice_state(
                    True,
                    amplitude_envelope=envelope,
                    audio_duration=duration,
                    audio_base64=audio_b64,
                )

            await _speaker.speak(
                suggestion.message,
                on_audio_ready=on_audio_ready,
            )
            await broadcast_voice_state(False)
        except Exception as e:
            logger.error("TTS failed for proactive suggestion: %s", e)
            await broadcast_voice_state(False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting JARVIS server...")
    jobs.init_jobs_db()
    success = await brain.initialize()
    if not success:
        logger.warning(
            "Brain initialization incomplete. Some features may be unavailable."
        )
    brain._on_plan_progress = broadcast_plan_progress
    brain.proactive._on_suggestion = _deliver_proactive_suggestion
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    scheduler_task = asyncio.create_task(_workflow_scheduler_loop())

    yield

    cleanup_task.cancel()
    scheduler_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task
    with suppress(asyncio.CancelledError):
        await scheduler_task
    with suppress(Exception):
        await asyncio.wait_for(brain.shutdown(), timeout=5)
    logger.info("JARVIS server shut down.")


app = FastAPI(
    title="J.A.R.V.I.S.",
    description="Just A Rather Very Intelligent System",
    version="0.3.0",
    lifespan=lifespan,
)

_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3741",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3741",
    f"http://localhost:{settings.API_PORT}",
    f"http://127.0.0.1:{settings.API_PORT}",
]

_tunnel_domain = os.environ.get("JARVIS_TUNNEL_DOMAIN", "")
if _tunnel_domain:
    _cors_origins.append(f"https://{_tunnel_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.trycloudflare\.com",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type", "x-requested-with", "x-jarvis-client", "x-trace-id"],
)


@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    """Attach a trace ID to every HTTP request and response."""
    incoming_trace_id = request.headers.get("x-trace-id", "")
    token = set_trace_id(incoming_trace_id or None)
    try:
        with trace_span("http.request", method=request.method, path=request.url.path):
            response = await call_next(request)
        response.headers["X-Trace-ID"] = get_trace_id()
        return response
    finally:
        reset_trace_id(token)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all HTTP responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws://localhost:* wss://localhost:* ws://127.0.0.1:* wss://127.0.0.1:*; "
        "media-src 'self' blob:; "
        "frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    return response


_CSRF_EXEMPT_PATHS = {"/auth/login", "/auth/status", "/auth/logout", "/voice/transcribe"}

@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Require X-JARVIS-Client header on state-changing requests from non-local origins."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.url.path not in _CSRF_EXEMPT_PATHS:
        client_host = request.client.host if request.client else ""
        if not auth.is_local_request(client_host):
            jarvis_header = request.headers.get("x-jarvis-client", "")
            if not jarvis_header:
                return JSONResponse(
                    status_code=403,
                    content={"error": "Missing X-JARVIS-Client header. CSRF protection."},
                )
    return await call_next(request)


_startup_pin = auth.initialize_pin()


class PinRequest(BaseModel):
    pin: str


class SetPinRequest(BaseModel):
    current_pin: str
    new_pin: str


async def require_auth(request: Request) -> bool:
    """FastAPI dependency for PIN auth. Local connections bypass auth.

    Remote connections require valid session token via header, cookie, or query param.
    """
    client_host = request.client.host if request.client else ""

    if auth.is_local_request(client_host):
        return True

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if auth.validate_token(token):
            return True

    token = request.cookies.get("jarvis_token", "")
    if token and auth.validate_token(token):
        return True

    token = request.query_params.get("token", "")
    if token and auth.validate_token(token):
        logger.warning("Auth via query param token (less secure). Use Authorization header or cookie instead.")
        return True

    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Authentication required. Please log in with your PIN.")


# Mount settings API router after auth is defined so configuration reads/writes
# use the same local-bypass / remote-token policy as the rest of the API.
app.include_router(settings_router, dependencies=[Depends(require_auth)])


@app.post("/auth/login")
async def auth_login(request: Request, body: PinRequest):
    """Verify the PIN and return a session token.

    This endpoint is always accessible (no auth required).
    Rate-limited by client IP.
    """
    client_host = request.client.host if request.client else ""
    token = auth.verify_pin(body.pin, client_ip=client_host)

    if token is None:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid PIN or rate limit exceeded."},
        )

    response = JSONResponse(content={"token": token, "expires_in": auth.SESSION_TOKEN_EXPIRY})
    response.set_cookie(
        key="jarvis_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=auth.SESSION_TOKEN_EXPIRY,
    )
    return response


@app.get("/auth/status")
async def auth_status(request: Request):
    """Check whether the current request is authenticated."""
    client_host = request.client.host if request.client else ""

    if auth.is_local_request(client_host):
        return {"authenticated": True, "local": True}

    for token_source in [
        request.headers.get("authorization", "").removeprefix("Bearer "),
        request.cookies.get("jarvis_token", ""),
        request.query_params.get("token", ""),
    ]:
        if token_source and auth.validate_token(token_source):
            return {"authenticated": True, "local": False}

    return {"authenticated": False, "local": False}


@app.post("/auth/logout")
async def auth_logout(request: Request):
    """Revoke the current session token."""
    # Find and revoke the token from any source
    for token_source in [
        request.headers.get("authorization", "").removeprefix("Bearer "),
        request.cookies.get("jarvis_token", ""),
        request.query_params.get("token", ""),
    ]:
        if token_source:
            auth.revoke_token(token_source)

    response = JSONResponse(content={"status": "logged out"})
    response.delete_cookie("jarvis_token")
    return response


@app.post("/auth/set-pin", dependencies=[Depends(require_auth)])
async def auth_set_pin(request: Request, body: SetPinRequest):
    """Change the PIN. Requires current PIN verification first."""
    client_host = request.client.host if request.client else ""

    token = auth.verify_pin(body.current_pin, client_ip=client_host)
    if token is None:
        return JSONResponse(
            status_code=401,
            content={"error": "Current PIN is incorrect."},
        )
    auth.revoke_token(token)

    if not auth.set_pin(body.new_pin):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid PIN format. Must be 4-8 digits."},
        )

    return {"status": "PIN updated. All sessions invalidated. Please log in again."}


def get_startup_pin() -> str:
    """Return the PIN generated at startup, or empty if loaded from previous session."""
    return _startup_pin


async def _session_cleanup_loop():
    while True:
        await asyncio.sleep(300)
        auth.cleanup_expired_sessions()


async def _workflow_scheduler_loop():
    while True:
        await asyncio.sleep(60)
        if not settings.WORKFLOW_SCHEDULER_ENABLED:
            continue
        try:
            runs = await workflow_scheduler.run_due_workflows(runner=brain.process)
            if runs:
                logger.info("Scheduled workflows completed: %d", len(runs))
        except Exception as exc:
            logger.error("Workflow scheduler tick failed: %s", exc)


# ============================================================
# Request/Response Models
# ============================================================
class ChatRequest(BaseModel):
    message: str
    tier: str = ""


class JobRequest(BaseModel):
    message: str
    kind: str = "chat"


class CostEstimateRequest(BaseModel):
    message: str
    tier: str = "brain"


class RoutineRequest(BaseModel):
    name: str
    prompt: str
    enabled: bool = True
    tags: list[str] = []


class RoutineRunRequest(BaseModel):
    background: bool = False


class FeedbackRequest(BaseModel):
    text: str
    category: str = "correction"


class BatchRequest(BaseModel):
    prompts: list[str]
    tier: str = "brain"


class PrivacyRequest(BaseModel):
    enabled: bool


class WorkflowRequest(BaseModel):
    name: str
    description: str = ""
    trigger: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    enabled: bool = True
    tags: list[str] = []
    owner_id: str = "local-owner"
    visibility: str = "private"
    permissions: list[str] = []
    actor_id: str = "local-owner"
    version_note: str = ""
    active_release_channel: str | None = None


class WorkflowTemplateRequest(BaseModel):
    template_id: str
    owner_id: str = "local-owner"
    actor_id: str = "local-owner"


class WorkflowRunRequest(BaseModel):
    background: bool = False
    dry_run: bool = False
    release_channel: str | None = None


class WorkflowReplayRequest(BaseModel):
    dry_run: bool = True


class WorkflowAssertionRunRequest(BaseModel):
    run_id: str = ""


class WorkflowApprovalRequest(BaseModel):
    actor: str = "local-owner"
    note: str = ""


class WorkflowVersionRestoreRequest(BaseModel):
    actor_id: str = "local-owner"
    note: str = ""


class WorkflowPublishRequest(BaseModel):
    channel: str = "stable"
    actor_id: str = "local-owner"
    note: str = ""
    activate: bool = True
    require_approval: bool | None = None


class SchedulerRunRequest(BaseModel):
    dry_run: bool = True


class TeamMemberRequest(BaseModel):
    name: str
    email: str = ""
    role: str = "member"
    member_id: str = ""
    status: str = "active"


class CalendarConnectionRequest(BaseModel):
    provider: str
    account_label: str = ""
    enabled: bool = False
    status: str = "not_connected"
    scopes: list[str] = []


class CalendarOAuthCredentialsRequest(BaseModel):
    client_id: str
    client_secret: str = ""


class CalendarOAuthStartRequest(BaseModel):
    redirect_uri: str = ""


class CalendarProviderEventsRequest(BaseModel):
    title: str
    start: str
    end: str
    timezone: str = "UTC"
    location: str = ""
    notes: str = ""
    calendar_id: str = ""
    attendees: list[str] = []


class CalendarPolicyRequest(BaseModel):
    timezone: str | None = None
    working_hours: dict[str, Any] | None = None
    default_duration_minutes: int | None = None
    conflict_strategy: str | None = None
    auto_create_events: bool | None = None
    require_confirmation_for_guests: bool | None = None
    buffer_minutes: int | None = None


class ScheduleAssessmentRequest(BaseModel):
    title: str
    start: str = ""
    end: str = ""
    attendees: list[str] = []
    provider: str = ""


class ChatResponse(BaseModel):
    response: str
    elapsed_ms: float
    tier_used: str
    backend: str


class StatusResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    active_backend: str
    active_model: str
    memory_stats: dict
    conversation_turns: int
    session_cost: dict


def _serialize_job(job: jobs.JobRecord) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "trace_id": job.trace_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


async def _run_chat_job(job_id: str, message: str) -> None:
    job = jobs.get_job(job_id)
    if job is None or job.status == jobs.JobStatus.CANCELLED.value:
        return

    token = set_trace_id(job.trace_id)
    try:
        jobs.mark_running(job_id)
        record_event("job.started", job_id=job_id, kind=job.kind)
        with trace_span("job.chat", job_id=job_id):
            result = await brain.process(message)
        latest = jobs.get_job(job_id)
        if latest is not None and latest.status == jobs.JobStatus.CANCELLED.value:
            record_event("job.cancelled", job_id=job_id)
            return
        jobs.mark_completed(job_id, result)
        record_event("job.completed", job_id=job_id)
    except Exception as exc:
        logger.exception("Background job %s failed", job_id)
        jobs.mark_failed(job_id, str(exc))
        record_event("job.failed", job_id=job_id, error=str(exc))
    finally:
        reset_trace_id(token)


async def _run_workflow_job(
    job_id: str,
    workflow_id: str,
    dry_run: bool = False,
    release_channel: str | None = None,
) -> None:
    job = jobs.get_job(job_id)
    if job is None or job.status == jobs.JobStatus.CANCELLED.value:
        return

    token = set_trace_id(job.trace_id)
    try:
        jobs.mark_running(job_id)
        record_event("job.started", job_id=job_id, kind=job.kind, workflow_id=workflow_id)
        run = await workflows.run_workflow(
            workflow_id,
            runner=brain.process if not dry_run else None,
            triggered_by="background",
            dry_run=dry_run,
            release_channel=release_channel,
        )
        latest = jobs.get_job(job_id)
        if latest is not None and latest.status == jobs.JobStatus.CANCELLED.value:
            record_event("job.cancelled", job_id=job_id)
            return
        if run is None:
            jobs.mark_failed(job_id, "Workflow not found.")
            return
        jobs.mark_completed(job_id, json.dumps(run, sort_keys=True, default=str))
        record_event("job.completed", job_id=job_id, workflow_id=workflow_id)
    except Exception as exc:
        logger.exception("Workflow job %s failed", job_id)
        jobs.mark_failed(job_id, str(exc))
        record_event("job.failed", job_id=job_id, error=str(exc))
    finally:
        reset_trace_id(token)


_start_time = time.time()


@app.get("/", response_model=StatusResponse, dependencies=[Depends(require_auth)])
async def status():
    """Health check and status."""
    return StatusResponse(
        status="online",
        version="0.3.0",
        uptime_seconds=round(time.time() - _start_time, 1),
        active_backend=brain.llm.active_backend,
        active_model=brain.llm.get_active_model(),
        memory_stats=brain.memory.get_stats(),
        conversation_turns=len(brain.conversation),
        session_cost=brain.llm.get_cost_summary(),
    )


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_auth)])
async def chat(request: ChatRequest):
    """Send a text message and get a response."""
    if len(request.message) > 50000:
        return JSONResponse(
            status_code=400,
            content={"error": "Message too long (max 50,000 characters)."},
        )
    start = time.time()
    response = await brain.process(request.message)
    elapsed = (time.time() - start) * 1000

    tier_used = "unknown"
    if brain.conversation:
        last = brain.conversation[-1]
        if last.role == "assistant":
            tier_used = last.tier_used or "brain"

    return ChatResponse(
        response=response,
        elapsed_ms=round(elapsed, 1),
        tier_used=tier_used,
        backend=brain.llm.active_backend,
    )


@app.post("/jobs", dependencies=[Depends(require_auth)])
async def create_background_job(request: JobRequest):
    """Queue a durable background chat job and return immediately."""
    if request.kind != "chat":
        return JSONResponse(
            status_code=400,
            content={"error": "Only kind='chat' background jobs are supported right now."},
        )
    if len(request.message) > 50000:
        return JSONResponse(
            status_code=400,
            content={"error": "Message too long (max 50,000 characters)."},
        )
    job = jobs.create_job(request.kind, {"message": request.message}, trace_id=get_trace_id())
    asyncio.create_task(_run_chat_job(job.id, request.message))
    return _serialize_job(job)


@app.get("/jobs", dependencies=[Depends(require_auth)])
async def list_background_jobs(limit: int = 50, status: str = ""):
    """List durable background jobs."""
    records = jobs.list_jobs(limit=limit, status=status)
    return {"jobs": [_serialize_job(job) for job in records], "count": len(records)}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_auth)])
async def get_background_job(job_id: str):
    """Get one durable background job."""
    job = jobs.get_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "Job not found."})
    return _serialize_job(job)


@app.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_auth)])
async def cancel_background_job(job_id: str):
    """Cancel a queued/running durable background job."""
    job = jobs.cancel_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "Job not found."})
    return _serialize_job(job)


@app.get("/routines", dependencies=[Depends(require_auth)])
async def list_routines():
    """List saved routines."""
    return {"routines": routines.list_routines()}


@app.post("/routines", dependencies=[Depends(require_auth)])
async def create_routine(request: RoutineRequest):
    """Create a repeatable routine."""
    if not request.name.strip() or not request.prompt.strip():
        return JSONResponse(status_code=400, content={"error": "Name and prompt are required."})
    return routines.create_routine(request.name, request.prompt, request.enabled, request.tags)


@app.put("/routines/{routine_id}", dependencies=[Depends(require_auth)])
async def update_routine(routine_id: str, request: RoutineRequest):
    """Update a routine."""
    routine = routines.update_routine(
        routine_id,
        {
            "name": request.name.strip(),
            "prompt": request.prompt.strip(),
            "enabled": request.enabled,
            "tags": request.tags,
        },
    )
    if routine is None:
        return JSONResponse(status_code=404, content={"error": "Routine not found."})
    return routine


@app.delete("/routines/{routine_id}", dependencies=[Depends(require_auth)])
async def delete_routine(routine_id: str):
    """Delete a routine."""
    if not routines.delete_routine(routine_id):
        return JSONResponse(status_code=404, content={"error": "Routine not found."})
    return {"status": "deleted"}


@app.post("/routines/{routine_id}/run", dependencies=[Depends(require_auth)])
async def run_routine(routine_id: str, request: RoutineRunRequest):
    """Run a routine now, either inline or as a background job."""
    routine = routines.get_routine(routine_id)
    if routine is None:
        return JSONResponse(status_code=404, content={"error": "Routine not found."})
    routines.mark_routine_run(routine_id)
    prompt = str(routine.get("prompt", ""))
    if request.background:
        job = jobs.create_job("routine", {"message": prompt, "routine_id": routine_id}, trace_id=get_trace_id())
        asyncio.create_task(_run_chat_job(job.id, prompt))
        return {"routine": routines.get_routine(routine_id), "job": _serialize_job(job)}
    start = time.time()
    response = await brain.process(prompt)
    return {
        "routine": routines.get_routine(routine_id),
        "response": response,
        "elapsed_ms": round((time.time() - start) * 1000, 1),
    }


@app.get("/workflows/overview", dependencies=[Depends(require_auth)])
async def workflow_overview():
    """Get workflow-builder foundation status."""
    return {
        **workflows.get_overview(),
        "scheduler": workflow_scheduler.get_scheduler_status(),
    }


@app.get("/workflows/scheduler/status", dependencies=[Depends(require_auth)])
async def workflow_scheduler_status():
    """Get scheduled workflow runner status."""
    return workflow_scheduler.get_scheduler_status()


@app.post("/workflows/scheduler/run-due", dependencies=[Depends(require_auth)])
async def run_due_workflows(request: SchedulerRunRequest):
    """Run workflows due in the current minute.

    Defaults to dry-run so the UI can preview due work without spending API
    budget. Pass dry_run=false for an explicit manual execution.
    """
    runs = await workflow_scheduler.run_due_workflows(
        runner=brain.process if not request.dry_run else None,
        dry_run=request.dry_run,
    )
    return {"runs": runs, "count": len(runs)}


@app.get("/workflows/templates", dependencies=[Depends(require_auth)])
async def workflow_templates():
    """List starter workflow templates."""
    return {"templates": workflows.list_templates()}


@app.get("/workflows", dependencies=[Depends(require_auth)])
async def list_workflows(include_disabled: bool = True):
    """List saved workflows."""
    items = workflows.list_workflows(include_disabled=include_disabled)
    return {"workflows": items, "count": len(items)}


@app.post("/workflows", dependencies=[Depends(require_auth)])
async def create_workflow(request: WorkflowRequest):
    """Create a workflow definition for the workflow builder."""
    if not request.name.strip():
        return JSONResponse(status_code=400, content={"error": "Workflow name is required."})
    workflow = workflows.create_workflow(
        name=request.name,
        description=request.description,
        trigger=request.trigger,
        actions=request.actions,
        assertions=request.assertions,
        enabled=request.enabled,
        tags=request.tags,
        owner_id=request.owner_id,
        visibility=request.visibility,
        permissions=request.permissions,
        actor_id=request.actor_id,
        note=request.version_note,
    )
    return workflow


@app.post("/workflows/from-template", dependencies=[Depends(require_auth)])
async def create_workflow_from_template(request: WorkflowTemplateRequest):
    """Create a workflow from a starter template."""
    workflow = workflows.create_workflow_from_template(
        request.template_id,
        owner_id=request.owner_id,
        actor_id=request.actor_id,
    )
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow template not found."})
    return workflow


@app.get("/workflows/runs", dependencies=[Depends(require_auth)])
async def list_workflow_runs(
    workflow_id: str = "",
    limit: int = 50,
    status: str = "",
    dry_run: bool | None = None,
    release_channel: str = "",
    workflow_version_id: str = "",
    workflow_version: int | None = None,
    started_after: float | None = None,
    started_before: float | None = None,
):
    """List workflow execution history."""
    runs = workflows.list_runs(
        workflow_id=workflow_id,
        limit=limit,
        status=status,
        dry_run=dry_run,
        release_channel=release_channel,
        workflow_version_id=workflow_version_id,
        workflow_version=workflow_version,
        started_after=started_after,
        started_before=started_before,
    )
    return {"runs": runs, "count": len(runs)}


@app.get("/workflows/analytics", dependencies=[Depends(require_auth)])
async def workflow_run_analytics(
    workflow_id: str = "",
    started_after: float | None = None,
    started_before: float | None = None,
    limit: int = 500,
):
    """Summarize workflow run health, latency, and failure patterns."""
    return workflows.get_run_analytics(
        workflow_id=workflow_id,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
    )


@app.get("/workflows/runs/{run_id}", dependencies=[Depends(require_auth)])
async def get_workflow_run(run_id: str):
    """Get one workflow run with its timeline/audit trace."""
    run = workflows.get_run(run_id)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "Workflow run not found."})
    return run


@app.post("/workflows/runs/{run_id}/replay", dependencies=[Depends(require_auth)])
async def replay_workflow_run(run_id: str, request: WorkflowReplayRequest):
    """Replay a previous workflow run, preferring its original version snapshot."""
    result = await workflows.replay_run(
        run_id,
        runner=brain.process if not request.dry_run else None,
        dry_run=request.dry_run,
    )
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Workflow run not found."})
    if result.get("replay_run") is None:
        return JSONResponse(status_code=400, content={"error": "; ".join(result.get("warnings", [])), **result})
    return result


@app.get("/workflows/approvals", dependencies=[Depends(require_auth)])
async def list_workflow_approvals(status: str = "pending", limit: int = 50):
    """List workflow approvals waiting for a user decision."""
    approvals = workflows.list_approvals(status=status, limit=limit)
    return {"approvals": approvals, "count": len(approvals)}


@app.post("/workflows/approvals/{approval_id}/approve", dependencies=[Depends(require_auth)])
async def approve_workflow_approval(approval_id: str, request: WorkflowApprovalRequest):
    """Approve a pending workflow action and execute supported actions."""
    approval = await workflows.approve_approval(approval_id, actor=request.actor, note=request.note)
    if approval is None:
        return JSONResponse(status_code=404, content={"error": "Approval not found."})
    return approval


@app.post("/workflows/approvals/{approval_id}/reject", dependencies=[Depends(require_auth)])
async def reject_workflow_approval(approval_id: str, request: WorkflowApprovalRequest):
    """Reject a pending workflow action."""
    approval = workflows.reject_approval(approval_id, actor=request.actor, note=request.note)
    if approval is None:
        return JSONResponse(status_code=404, content={"error": "Approval not found."})
    return approval


@app.get("/workflows/releases", dependencies=[Depends(require_auth)])
async def list_workflow_releases(workflow_id: str = "", channel: str = "", limit: int = 50):
    """List workflow release channel history."""
    releases = workflows.list_workflow_releases(workflow_id=workflow_id, channel=channel, limit=limit)
    return {"releases": releases, "count": len(releases)}


@app.get("/workflows/release-policies", dependencies=[Depends(require_auth)])
async def workflow_release_policies():
    """List workflow release promotion policies."""
    return {"policies": workflows.get_release_policies()}


@app.get("/workflows/{workflow_id}/versions", dependencies=[Depends(require_auth)])
async def list_workflow_versions(workflow_id: str, limit: int = 50):
    """List version history for one workflow."""
    workflow = workflows.get_workflow(workflow_id)
    versions = workflows.list_workflow_versions(workflow_id, limit=limit)
    if workflow is None and not versions:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    versions = [
        {
            **version,
            "release_readiness": workflows.get_release_readiness(
                workflow_id,
                str(version.get("id") or ""),
                channel="stable",
                note="Promoted from workflow history.",
            ),
        }
        for version in versions
    ]
    return {"versions": versions, "count": len(versions)}


@app.get("/workflows/{workflow_id}/versions/{version_id}", dependencies=[Depends(require_auth)])
async def get_workflow_version(workflow_id: str, version_id: str):
    """Get one workflow version snapshot."""
    version = workflows.get_workflow_version(workflow_id, version_id)
    if version is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return version


@app.get("/workflows/{workflow_id}/versions/{version_id}/readiness", dependencies=[Depends(require_auth)])
async def get_workflow_version_readiness(workflow_id: str, version_id: str, channel: str = "stable", note: str = ""):
    """Get release gate readiness for one workflow version."""
    readiness = workflows.get_release_readiness(workflow_id, version_id, channel=channel, note=note)
    if readiness["status"] == "missing_version":
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return readiness


@app.post("/workflows/{workflow_id}/versions/{version_id}/dry-run", dependencies=[Depends(require_auth)])
async def dry_run_workflow_version(workflow_id: str, version_id: str):
    """Dry-run a specific workflow version as release gate evidence."""
    run = await workflows.run_workflow_version(workflow_id, version_id, dry_run=True)
    if run is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return {"run": run}


@app.post("/workflows/{workflow_id}/versions/{version_id}/assertions/run", dependencies=[Depends(require_auth)])
async def run_workflow_version_assertions(
    workflow_id: str,
    version_id: str,
    request: WorkflowAssertionRunRequest,
):
    """Run release assertions against a workflow version's latest dry run."""
    result = workflows.run_workflow_assertion_suite(workflow_id, version_id, run_id=request.run_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    if not result.get("passed") and result.get("status") in {"missing_run", "wrong_workflow"}:
        return JSONResponse(status_code=400, content={"error": result.get("message", "Assertions could not run."), "result": result})
    return {"result": result}


@app.post("/workflows/{workflow_id}/versions/{version_id}/restore", dependencies=[Depends(require_auth)])
async def restore_workflow_version(workflow_id: str, version_id: str, request: WorkflowVersionRestoreRequest):
    """Restore a workflow from a version snapshot."""
    workflow = workflows.restore_workflow_version(
        workflow_id,
        version_id,
        actor_id=request.actor_id,
        note=request.note,
    )
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow version not found."})
    return workflow


@app.post("/workflows/{workflow_id}/versions/{version_id}/publish", dependencies=[Depends(require_auth)])
async def publish_workflow_version(workflow_id: str, version_id: str, request: WorkflowPublishRequest):
    """Request or execute a workflow version release promotion."""
    result = workflows.request_workflow_release_approval(
        workflow_id,
        version_id,
        channel=request.channel,
        actor_id=request.actor_id,
        note=request.note,
        activate=request.activate,
        require_approval=request.require_approval,
    )
    if result is None:
        assessment = workflows.assess_release_request(
            workflow_id,
            version_id,
            channel=request.channel,
            note=request.note,
        )
        blockers = assessment.get("blockers", [])
        status_code = 400 if blockers else 404
        return JSONResponse(
            status_code=status_code,
            content={"error": "; ".join(blockers) or "Workflow version not found."},
        )
    return result


@app.get("/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
async def get_workflow(workflow_id: str):
    """Get one workflow definition."""
    workflow = workflows.get_workflow(workflow_id)
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return workflow


@app.put("/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
async def update_workflow(workflow_id: str, request: WorkflowRequest):
    """Update a workflow definition."""
    updates = {
        "name": request.name,
        "description": request.description,
        "trigger": request.trigger,
        "actions": request.actions,
        "assertions": request.assertions,
        "enabled": request.enabled,
        "tags": request.tags,
        "visibility": request.visibility,
        "permissions": request.permissions,
    }
    if request.active_release_channel is not None:
        updates["active_release_channel"] = request.active_release_channel
    workflow = workflows.update_workflow(
        workflow_id,
        updates,
        actor_id=request.actor_id,
        note=request.version_note,
    )
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return workflow


@app.delete("/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
async def delete_workflow(workflow_id: str, actor_id: str = "local-owner", note: str = ""):
    """Delete a workflow definition."""
    if not workflows.delete_workflow(workflow_id, actor_id=actor_id, note=note):
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    return {"status": "deleted"}


@app.post("/workflows/{workflow_id}/run", dependencies=[Depends(require_auth)])
async def run_workflow(workflow_id: str, request: WorkflowRunRequest):
    """Run a workflow now, either inline or in a durable background job."""
    workflow = workflows.get_workflow(workflow_id)
    if workflow is None:
        return JSONResponse(status_code=404, content={"error": "Workflow not found."})
    if request.background:
        job = jobs.create_job(
            "workflow",
            {"workflow_id": workflow_id, "dry_run": request.dry_run, "release_channel": request.release_channel},
            trace_id=get_trace_id(),
        )
        asyncio.create_task(_run_workflow_job(job.id, workflow_id, request.dry_run, request.release_channel))
        return {"workflow": workflow, "job": _serialize_job(job)}
    run = await workflows.run_workflow(
        workflow_id,
        runner=brain.process if not request.dry_run else None,
        triggered_by="manual",
        dry_run=request.dry_run,
        release_channel=request.release_channel,
    )
    return {"workflow": workflows.get_workflow(workflow_id), "run": run}


@app.get("/feedback", dependencies=[Depends(require_auth)])
async def list_feedback(limit: int = 50, category: str = ""):
    """List stored feedback/corrections."""
    return {"feedback": feedback.list_feedback(limit=limit, category=category)}


@app.post("/feedback", dependencies=[Depends(require_auth)])
async def create_feedback(request: FeedbackRequest):
    """Create a feedback/correction item."""
    if not request.text.strip():
        return JSONResponse(status_code=400, content={"error": "Feedback text is required."})
    return feedback.add_feedback(request.text, category=request.category)


@app.delete("/feedback/{feedback_id}", dependencies=[Depends(require_auth)])
async def delete_feedback(feedback_id: str):
    """Delete a feedback item."""
    if not feedback.delete_feedback(feedback_id):
        return JSONResponse(status_code=404, content={"error": "Feedback item not found."})
    return {"status": "deleted"}


@app.post("/anthropic/batches", dependencies=[Depends(require_auth)])
async def create_anthropic_batch(request: BatchRequest):
    """Create an Anthropic Message Batch for non-urgent work."""
    if not request.prompts:
        return JSONResponse(status_code=400, content={"error": "At least one prompt is required."})
    try:
        return await anthropic_batch.create_batch(request.prompts, tier=request.tier)
    except Exception as exc:
        logger.warning("Batch creation failed: %s", exc)
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/anthropic/batches/{batch_id}", dependencies=[Depends(require_auth)])
async def get_anthropic_batch(batch_id: str):
    """Get Anthropic Message Batch status."""
    try:
        return await anthropic_batch.get_batch(batch_id)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/anthropic/batches/{batch_id}/cancel", dependencies=[Depends(require_auth)])
async def cancel_anthropic_batch(batch_id: str):
    """Cancel an Anthropic Message Batch."""
    try:
        return await anthropic_batch.cancel_batch(batch_id)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/clear", dependencies=[Depends(require_auth)])
async def clear_conversation():
    """Clear the current conversation."""
    brain.clear_conversation()
    return {"status": "conversation cleared"}


@app.get("/health/ping")
async def health_ping():
    """Lightweight unauthenticated liveness probe.

    Used by the Chrome extension's alarm-based keepalive to detect
    whether the server is running before attempting a WebSocket connection.
    Returns minimal data to avoid leaking internal state.
    """
    return {"status": "ok"}


@app.get("/health", dependencies=[Depends(require_auth)])
async def health():
    """Simple health check for monitoring."""
    from jarvis.core.cache import tool_cache
    from jarvis.core.hardening import get_health_report
    from jarvis.core.perf import perf_tracker
    return {
        "healthy": brain.llm.active_backend != "none",
        "backend": brain.llm.active_backend,
        "model": brain.llm.get_active_model(),
        "memory": brain.memory.get_stats(),
        "hardening": get_health_report(),
        "perf_summary": perf_tracker.get_summary_line(),
        "cache": tool_cache.get_stats(),
        "jobs": {"recent": len(jobs.list_jobs(limit=10))},
    }


@app.get("/perf", dependencies=[Depends(require_auth)])
async def perf():
    """Get performance metrics and latency data."""
    from jarvis.core.perf import perf_tracker
    return perf_tracker.get_stats()


@app.get("/cache", dependencies=[Depends(require_auth)])
async def cache_stats():
    """Get tool result cache statistics."""
    from jarvis.core.cache import tool_cache
    return tool_cache.get_stats()


@app.post("/cache/clear", dependencies=[Depends(require_auth)])
async def cache_clear():
    """Clear the entire tool result cache."""
    from jarvis.core.cache import tool_cache
    await tool_cache.invalidate()
    return {"status": "ok", "message": "Cache cleared."}


@app.get("/devices", dependencies=[Depends(require_auth)])
async def connected_devices():
    """Get list of connected WebSocket clients with device info."""
    return {
        "count": len(ws_manager.active),
        "devices": ws_manager.get_connected_devices(),
    }


@app.post("/audio/stop", dependencies=[Depends(require_auth)])
async def stop_audio():
    """Stop all active TTS playback on all devices."""
    if _speaker:
        _speaker.stop_speaking()
    await ws_manager.broadcast_json({"voice_stop": True})
    await broadcast_voice_state(False)
    if _listener and _listener._is_speaking:
        _listener.set_speaking(False, open_followup=False)
    return {"status": "ok", "message": "Audio stopped on all devices."}


@app.get("/costs", dependencies=[Depends(require_auth)])
async def costs():
    """Get cost tracking data."""
    return {
        "session": brain.llm.get_cost_summary(),
        "today": cost_tracker.get_today_summary(),
        "month": cost_tracker.get_month_summary(),
        "insights": cost_tracker.get_cost_insights(),
        "hard_limits": cost_tracker.hard_limit_status(),
        "privacy_mode": brain._privacy_mode,
    }


@app.post("/costs/estimate", dependencies=[Depends(require_auth)])
async def estimate_cost(request: CostEstimateRequest):
    """Estimate request tokens and cost before sending to Claude."""
    from jarvis.agent.tool_selector import select_tools_for_request
    from jarvis.agent.tools_schema import TOOL_SCHEMAS
    from jarvis.core.perf import estimate_request_cost

    tools = select_tools_for_request(request.message, TOOL_SCHEMAS)
    token_info = await brain.llm.count_input_tokens(
        request.message,
        conversation_history=[
            {"role": turn.role, "content": turn.content}
            for turn in brain.conversation[-settings.CONTEXT_RECENT_MESSAGES:]
        ],
        tier=request.tier,
        tools=tools,
    )
    input_tokens = int(token_info.get("input_tokens", 0) or 0)
    return {
        **token_info,
        "selected_tool_count": len(tools),
        "estimated_cost_usd": round(estimate_request_cost(input_tokens, 512, request.tier), 6),
    }


@app.get("/privacy", dependencies=[Depends(require_auth)])
async def get_privacy_mode():
    """Get current privacy mode state."""
    return {"enabled": brain._privacy_mode, "memory_enabled": settings.MEMORY_ENABLED}


@app.post("/privacy", dependencies=[Depends(require_auth)])
async def set_privacy_mode(request: PrivacyRequest):
    """Enable or disable runtime privacy mode."""
    brain._privacy_mode = request.enabled
    return {"enabled": brain._privacy_mode}


@app.get("/models", dependencies=[Depends(require_auth)])
async def models():
    """Get available model tiers and their configuration."""
    from jarvis.core.llm import TIER_CONFIG
    return {
        "active_backend": brain.llm.active_backend,
        "tiers": {
            tier: {
                "model": config["model"],
                "max_tokens": config["max_tokens"],
                "temperature": config["temperature"],
            }
            for tier, config in TIER_CONFIG.items()
        },
        "ollama_model": settings.OLLAMA_MODEL,
        "prefer_claude": settings.PREFER_CLAUDE,
    }


class ProfileUpdateRequest(BaseModel):
    key: str
    value: str


@app.get("/profile", dependencies=[Depends(require_auth)])
async def get_profile():
    """Get the full user profile."""
    return user_profile.get_profile()


_ALLOWED_PROFILE_KEYS = {
    "name", "nickname", "location", "timezone", "language",
    "communication_style", "interests", "occupation",
    "wake_time", "sleep_time", "theme", "voice",
}


@app.put("/profile", dependencies=[Depends(require_auth)])
async def update_profile_endpoint(body: ProfileUpdateRequest):
    """Update a profile field or preference."""
    if body.key not in _ALLOWED_PROFILE_KEYS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown profile key: '{body.key}'. Allowed: {sorted(_ALLOWED_PROFILE_KEYS)}"},
        )
    updated = user_profile.update_profile({body.key: body.value})
    return {"status": "updated", "profile": updated}


@app.get("/profile/{key}", dependencies=[Depends(require_auth)])
async def get_profile_preference(key: str):
    """Get a single profile preference."""
    value = user_profile.get_preference(key)
    if value is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Preference '{key}' not found."},
        )
    return {"key": key, "value": value}


@app.get("/plan", dependencies=[Depends(require_auth)])
async def get_active_plan():
    """Get the active task plan status, if any."""
    plan = brain.planner.get_active_plan()
    if plan is None:
        return {"active": False, "plan": None}
    return {
        "active": True,
        "plan": plan.to_dict(),
        "progress": plan.progress_pct,
        "summary": plan.progress_summary(),
    }


@app.get("/plan/history", dependencies=[Depends(require_auth)])
async def get_plan_history():
    """Get recent completed task plans."""
    plans = brain.planner.tracker.load_recent_plans(limit=10)
    return {"plans": plans, "count": len(plans)}


@app.get("/learning", dependencies=[Depends(require_auth)])
async def get_learning_insights():
    """Get a comprehensive summary of learning loop insights."""
    return brain.learning.get_insights_summary()


@app.get("/learning/tools", dependencies=[Depends(require_auth)])
async def get_tool_reliability():
    """Get tool reliability scores and statistics."""
    return {
        "tools": brain.learning.get_tool_reliability_report(),
        "unreliable": brain.learning.get_unreliable_tools(),
    }


@app.get("/tools/permissions", dependencies=[Depends(require_auth)])
async def get_tool_permissions():
    """Get the formal permission catalog for all registered tools."""
    return {
        "summary": summarize_permissions(),
        "tools": {
            name: {
                "capabilities": sorted(capability.value for capability in permission.capabilities),
                "risk": permission.risk.value,
                "requires_confirmation": permission.requires_confirmation,
                "reason": permission.reason,
            }
            for name, permission in sorted(TOOL_PERMISSIONS.items())
        },
    }


@app.get("/tools/audit", dependencies=[Depends(require_auth)])
async def get_tool_audit(limit: int = 50):
    """Get recent redacted tool audit rows."""
    rows = list_tool_audit(limit=limit)
    return {"audit": rows, "count": len(rows)}


@app.get("/learning/failures", dependencies=[Depends(require_auth)])
async def get_failure_patterns():
    """Get common failure patterns identified by the learning loop."""
    return {
        "patterns": brain.learning.get_common_failure_patterns(limit=10),
        "plan_stats": brain.learning.get_plan_success_rate(),
    }


@app.get("/team", dependencies=[Depends(require_auth)])
async def get_team():
    """Get local team mode, members, and role capability matrix."""
    return team.get_team()


@app.get("/team/members", dependencies=[Depends(require_auth)])
async def list_team_members():
    """List team members."""
    members = team.list_members()
    return {"members": members, "count": len(members)}


@app.put("/team/members", dependencies=[Depends(require_auth)])
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


@app.delete("/team/members/{member_id}", dependencies=[Depends(require_auth)])
async def delete_team_member(member_id: str):
    """Delete a team member, except the local owner."""
    if not team.delete_member(member_id):
        return JSONResponse(status_code=404, content={"error": "Member not found or cannot be deleted."})
    return {"status": "deleted"}


@app.get("/team/permissions", dependencies=[Depends(require_auth)])
async def team_permissions():
    """Get role capability mappings."""
    return {"roles": team.permission_matrix()}


@app.get("/calendar/connections", dependencies=[Depends(require_auth)])
async def get_calendar_connections():
    """Get calendar provider connection metadata and scheduling policy."""
    return calendar_accounts.get_state()


@app.put("/calendar/connections", dependencies=[Depends(require_auth)])
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


@app.delete("/calendar/connections/{provider}", dependencies=[Depends(require_auth)])
async def delete_calendar_connection(provider: str):
    """Remove calendar provider connection metadata."""
    if not calendar_accounts.remove_connection(provider):
        return JSONResponse(status_code=404, content={"error": "Calendar connection not found."})
    return {"status": "deleted"}


@app.get("/calendar/oauth/{provider}/status", dependencies=[Depends(require_auth)])
async def get_calendar_oauth_status(provider: str):
    """Get OAuth configuration and token status for a provider."""
    try:
        return calendar_oauth.get_provider_status(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.put("/calendar/oauth/{provider}/credentials", dependencies=[Depends(require_auth)])
async def save_calendar_oauth_credentials(provider: str, request: CalendarOAuthCredentialsRequest):
    """Save OAuth app credentials for Google or Outlook Calendar."""
    try:
        return calendar_oauth.save_credentials(provider, request.client_id, request.client_secret)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.delete("/calendar/oauth/{provider}/credentials", dependencies=[Depends(require_auth)])
async def delete_calendar_oauth_credentials(provider: str):
    """Remove OAuth app credentials for a provider."""
    try:
        return calendar_oauth.delete_credentials(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/calendar/oauth/{provider}/start", dependencies=[Depends(require_auth)])
async def start_calendar_oauth(provider: str, request: CalendarOAuthStartRequest):
    """Build a provider OAuth authorization URL."""
    try:
        return calendar_oauth.build_authorization_url(provider, redirect_uri=request.redirect_uri)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/calendar/oauth/{provider}/callback", dependencies=[Depends(require_auth)])
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


@app.post("/calendar/oauth/{provider}/disconnect", dependencies=[Depends(require_auth)])
async def disconnect_calendar_oauth(provider: str):
    """Disconnect a provider calendar account."""
    try:
        return calendar_oauth.disconnect(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/calendar/providers/{provider}/events", dependencies=[Depends(require_auth)])
async def list_provider_events(provider: str, days: int = 1, limit: int = 20, calendar_id: str = ""):
    """List events from an OAuth-backed calendar provider."""
    try:
        return await calendar_oauth.list_events(provider, days=days, limit=limit, calendar_id=calendar_id)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/calendar/providers/{provider}/events", dependencies=[Depends(require_auth)])
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


@app.put("/calendar/policy", dependencies=[Depends(require_auth)])
async def update_calendar_policy(request: CalendarPolicyRequest):
    """Update safe scheduling policy."""
    updates = request.model_dump(exclude_none=True)
    return calendar_accounts.update_policy(updates)


@app.post("/calendar/scheduling/assess", dependencies=[Depends(require_auth)])
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


@app.get("/calendar", dependencies=[Depends(require_auth)])
async def get_calendar_today():
    """Quick access to today's calendar events."""
    from jarvis.tools.calendar_email import get_upcoming_events
    events = await get_upcoming_events(days=1)
    return {"events": events}


@app.get("/mail/unread", dependencies=[Depends(require_auth)])
async def get_mail_unread():
    """Quick access to unread email count."""
    from jarvis.tools.calendar_email import get_unread_count
    count = await get_unread_count()
    return {"unread": count}


class ProactiveSettingsRequest(BaseModel):
    enabled: bool | None = None
    category: str | None = None
    category_enabled: bool | None = None


@app.get("/proactive", dependencies=[Depends(require_auth)])
async def get_proactive_status():
    """Get the proactive suggestions engine status."""
    return brain.proactive.get_status()


@app.get("/agents", dependencies=[Depends(require_auth)])
async def get_agents_status():
    """Get the multi-agent coordinator status and all agent profiles."""
    return brain.coordinator.get_status()


@app.get("/agents/active", dependencies=[Depends(require_auth)])
async def get_active_agents():
    """Get currently running agent tasks."""
    return {
        "active": brain.coordinator.get_active_agents(),
        "count": len(brain.coordinator.get_active_agents()),
    }


@app.get("/agents/history", dependencies=[Depends(require_auth)])
async def get_agent_history():
    """Get recent agent execution history."""
    return {
        "history": brain.coordinator.get_execution_history(limit=20),
    }


@app.post("/proactive/settings", dependencies=[Depends(require_auth)])
async def update_proactive_settings(body: ProactiveSettingsRequest):
    """Update proactive engine settings.

    Toggle the entire engine on/off, or enable/disable specific categories.
    """
    from jarvis.core.proactive import SuggestionCategory

    if body.enabled is not None:
        brain.proactive.set_enabled(body.enabled)

    if body.category and body.category_enabled is not None:
        try:
            cat = SuggestionCategory(body.category)
            brain.proactive.set_category_enabled(cat, body.category_enabled)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Unknown category: {body.category}. "
                    f"Valid: {[c.value for c in SuggestionCategory]}"
                },
            )

    return brain.proactive.get_status()


_whisper_model = None
_whisper_lock = asyncio.Lock()


async def _get_whisper_model():
    """Lazy-load the Whisper model for browser voice transcription."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    async with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model

        try:
            from faster_whisper import WhisperModel
            loop = asyncio.get_event_loop()
            _whisper_model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    settings.WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",
                ),
            )
            logger.info("Whisper model loaded for browser transcription: %s", settings.WHISPER_MODEL)
        except ImportError:
            logger.error("faster-whisper not installed. Browser voice input disabled.")
        except Exception as e:
            logger.error("Failed to load Whisper model: %s", e)

        return _whisper_model


@app.post("/voice/transcribe", dependencies=[Depends(require_auth)])
async def transcribe_audio(audio: Annotated[UploadFile, File(...)]):
    """Transcribe uploaded audio from the browser microphone.

    Accepts WebM/WAV/OGG audio files from MediaRecorder.
    Returns the transcribed text.
    """
    import tempfile


    model = await _get_whisper_model()
    if model is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Speech-to-text model not available"},
        )

    allowed_types = {"audio/webm", "audio/wav", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-wav"}
    # Strip codec parameters (e.g. "audio/webm;codecs=opus" -> "audio/webm")
    base_content_type = (audio.content_type or "").split(";")[0].strip()
    if base_content_type and base_content_type not in allowed_types:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported audio format: {audio.content_type}. Accepted: webm, wav, ogg, mp3, mp4."},
        )

    max_audio_size = 25 * 1024 * 1024  # 25 MB
    suffix = ".webm" if "webm" in (audio.content_type or "") else ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await audio.read()
        if len(content) > max_audio_size:
            return JSONResponse(
                status_code=413,
                content={"error": f"Audio file too large (max {max_audio_size // 1024 // 1024} MB)."},
            )
        tmp.write(content)
        tmp_path = tmp.name

    try:
        wav_path = tmp_path + ".wav"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", tmp_path,
            "-ar", "16000", "-ac", "1", "-f", "wav", wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if proc.returncode != 0:
            return JSONResponse(
                status_code=400,
                content={"error": "Failed to process audio file"},
            )

        loop = asyncio.get_event_loop()

        def run_transcribe():
            segments, info = model.transcribe(
                wav_path,
                language=settings.WHISPER_LANGUAGE,
                beam_size=3,
                vad_filter=False,
            )
            parts = []
            for seg in segments:
                seg_text = seg.text if isinstance(seg.text, str) else " ".join(seg.text)
                parts.append(seg_text)
            return " ".join(parts).strip()

        text = await loop.run_in_executor(None, run_transcribe)

        logger.info("Browser voice transcription: '%s'", text[:100] if text else "(empty)")
        return {"text": text, "language": settings.WHISPER_LANGUAGE}

    except Exception as e:
        logger.error("Transcription failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Transcription failed. Check server logs for details."},
        )
    finally:
        import os
        for p in [tmp_path, tmp_path + ".wav"]:
            with suppress(OSError):
                os.unlink(p)


@app.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat with token streaming."""
    client_host = websocket.client.host if websocket.client else ""
    is_local = auth.is_local_request(client_host)

    if not is_local:
        ws_token = websocket.query_params.get("token", "")
        if not ws_token or not auth.validate_token(ws_token):
            await websocket.close(code=4001, reason="Authentication required")
            return

    await ws_manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()

            if "client_register" in data:
                ws_manager.register_client(websocket, data["client_register"])
                await websocket.send_json({
                    "client_registered": True,
                    "connected_devices": ws_manager.get_connected_devices(),
                })
                continue

            if "audio_preference" in data:
                pref = data["audio_preference"]
                client_info = ws_manager.get_client_info(websocket)
                if client_info:
                    client_info.wants_audio = bool(pref.get("wants_audio", True))
                    logger.info(
                        "Client audio preference updated: wants_audio=%s",
                        client_info.wants_audio,
                    )
                await websocket.send_json({
                    "audio_preference_updated": True,
                    "wants_audio": client_info.wants_audio if client_info else True,
                })
                continue

            if data.get("stop_audio"):
                logger.info("Audio stop requested by client")
                if _speaker:
                    _speaker.stop_speaking()
                await ws_manager.broadcast_json({"voice_stop": True})
                await broadcast_voice_state(False)
                await broadcast_overlay_state("idle")
                if _listener and _listener._is_speaking:
                    _listener.set_speaking(False, open_followup=False)
                continue

            if "browser_mic" in data:
                recording = data["browser_mic"]
                await broadcast_overlay_state("listening" if recording else "idle")
                if _listener:
                    _listener.set_speaking(recording, open_followup=False)
                    logger.info("Browser mic %s, terminal listener %s",
                                "started" if recording else "stopped",
                                "paused" if recording else "resumed")
                continue

            ws_manager.touch(websocket)

            message = data.get("message", "")

            if not message:
                await websocket.send_json({"error": "Empty message"})
                continue

            if len(message) > 50000:
                await websocket.send_json({"error": "Message too long (max 50,000 characters)"})
                continue

            await broadcast_overlay_state("thinking", user_text=message)

            if _listener:
                _listener.set_speaking(True)

            full_response = []
            async for token in brain.process_stream(message):
                full_response.append(token)
                await websocket.send_json({
                    "token": token,
                    "done": False,
                })

            complete = "".join(full_response)
            await websocket.send_json({
                "token": EMPTY_CHUNK,
                "done": True,
                "full_response": complete,
                "backend": brain.llm.active_backend,
                "session_cost": brain.llm.get_cost_summary(),
            })

            if _speaker and complete.strip():
                await broadcast_overlay_state("speaking", text=complete, user_text=message)
                try:
                    requesting_ws = websocket

                    async def on_audio_ready(envelope, duration, audio_b64=None, target_ws=requesting_ws):
                        await broadcast_voice_state(
                            True,
                            amplitude_envelope=envelope,
                            audio_duration=duration,
                            audio_base64=audio_b64,
                            target_ws=target_ws,
                        )

                    async def on_audio_chunk(chunk_b64, idx, is_last, env, dur, target_ws=requesting_ws):
                        await broadcast_voice_chunk(
                            chunk_b64, idx, is_last, env, dur,
                            target_ws=target_ws,
                        )

                    await _speaker.speak(
                        complete,
                        on_audio_ready=on_audio_ready,
                        on_audio_chunk=on_audio_chunk,
                        skip_local_playback=True,
                    )
                    await broadcast_voice_state(False)
                    await broadcast_overlay_state("idle")
                except Exception as e:
                    logger.error("TTS failed for browser message: %s", e)
                    await broadcast_voice_state(False)
                    await broadcast_overlay_state("idle")
            else:
                await broadcast_overlay_state("idle", text=complete, user_text=message)

            if _listener:
                _listener.set_speaking(False, open_followup=False)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        ws_manager.disconnect(websocket)


@app.websocket("/ws/extension")
async def websocket_extension(websocket: WebSocket):
    """WebSocket endpoint for JARVIS Chrome Extension browser automation."""
    client_host = websocket.client.host if websocket.client else ""
    is_local = auth.is_local_request(client_host)

    if not is_local:
        ws_token = websocket.query_params.get("token", "")
        if not ws_token or not auth.validate_token(ws_token):
            await websocket.close(code=4001, reason="Authentication required")
            return

    await websocket.accept()
    logger.info("Chrome extension connected from %s", client_host)

    chrome_extension.set_extension_ws(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            await chrome_extension.handle_extension_message(data)

    except WebSocketDisconnect:
        logger.info("Chrome extension disconnected.")
    except Exception as e:
        logger.error("Chrome extension WebSocket error: %s", e)
    finally:
        chrome_extension.clear_extension_ws()


@app.websocket("/ws/overlay")
async def websocket_overlay(websocket: WebSocket):
    """Lightweight WebSocket for desktop overlay state (localhost only, no auth).

    Sends JSON messages: {"state": "idle"|"listening"|"thinking"|"speaking"}
    The overlay uses these to animate the particle orb.
    """
    client_host = websocket.client.host if websocket.client else ""
    if not auth.is_local_request(client_host):
        await websocket.close(code=4003, reason="Overlay only available locally")
        return

    await websocket.accept()
    _overlay_clients.append(websocket)
    logger.info("Desktop overlay connected. Sending current state: %s", _overlay_state)

    # Send current state immediately on connect
    with suppress(Exception):
        await websocket.send_json({
            "state": _overlay_state,
            "text": _overlay_text,
            "userText": _overlay_user_text,
        })

    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command") or data.get("type")
            if command == "activate_voice":
                await _activate_voice_from_overlay(websocket)
            elif command == "ping":
                await websocket.send_json({"pong": True})
    except WebSocketDisconnect:
        logger.info("Desktop overlay disconnected.")
    except Exception as e:
        logger.debug("Desktop overlay receive loop ended: %s", e)
    finally:
        if websocket in _overlay_clients:
            _overlay_clients.remove(websocket)
