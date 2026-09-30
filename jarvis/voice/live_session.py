"""Cloud voice mode on OpenAI GPT-Live (full-duplex speech) with client delegation.

GPT-Live handles listening, speaking, turn-taking and interruptions. When the
user asks for something that needs work, it emits a delegation; JARVIS runs
the request through its normal pipeline (tools, memory, approval prompts)
and appends the result, which GPT-Live speaks.

The OpenAI connection lives on the JARVIS server, so the API key never
reaches the browser. Protocol reference: developers.openai.com guides
"Voice over WebSockets (Live)" and "Live delegation".
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from jarvis.config import settings

logger = logging.getLogger("jarvis.voice.live")

LIVE_URL = "wss://api.openai.com/v1/live/sessions"
# Appends are limited to 500 tokens; ~1,500 characters stays safely under that.
MAX_APPEND_CHARS = 1500

LIVE_INSTRUCTIONS = (
    "You are JARVIS, a warm, witty British AI assistant speaking with your user. "
    "Keep replies short and natural for speech. "
    "For anything that needs actions, tools, personal data, current information, "
    "or multi-step work, delegate the task instead of answering from memory. "
    "When a delegated result arrives, tell the user the outcome briefly."
)

Runner = Callable[[str], Awaitable[str]]
Sink = Callable[[dict[str, Any]], Awaitable[None]]


def split_for_append(text: str, limit: int = MAX_APPEND_CHARS) -> list[str]:
    """Split text into appendable pieces, preferring sentence boundaries."""
    text = text.strip()
    pieces: list[str] = []
    while len(text) > limit:
        cut = max(text.rfind(". ", 0, limit), text.rfind("\n", 0, limit))
        cut = cut + 1 if cut > limit // 2 else limit
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        pieces.append(text)
    return pieces


class LiveSession:
    """One GPT-Live conversation relayed between a browser client and OpenAI."""

    def __init__(self, runner: Runner, client_sink: Sink, connect: Callable[..., Any] | None = None):
        self._runner = runner
        self._client_sink = client_sink
        self._connect = connect
        self._ws: Any = None
        self._user_transcript: list[str] = []
        self._tasks: set[asyncio.Task] = set()

    def session_config(self) -> dict[str, Any]:
        return {
            "model": settings.OPENAI_LIVE_MODEL,
            "instructions": LIVE_INSTRUCTIONS,
            "audio": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "output": {"voice": settings.OPENAI_LIVE_VOICE},
            },
            "delegation": {"type": "client"},
        }

    async def open(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set; GPT-Live voice needs it.")
        connect = self._connect
        if connect is None:
            from websockets.asyncio.client import connect as ws_connect

            connect = ws_connect
        self._ws = await connect(
            LIVE_URL, additional_headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        )
        await self._send({"type": "session.start", "session": self.session_config()})

    async def _send(self, event: dict[str, Any]) -> None:
        event.setdefault("event_id", f"evt_{uuid.uuid4().hex[:16]}")
        await self._ws.send(json.dumps(event))

    async def send_audio(self, pcm16_b64: str) -> None:
        """Forward a base64 PCM16 24 kHz mono chunk from the client."""
        await self._send({"type": "session.input_audio.append", "audio": pcm16_b64})

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._ws is not None:
            try:
                await self._send({"type": "session.close"})
            except Exception as exc:
                logger.debug("GPT-Live close failed: %s", exc)
            await self._ws.close()

    async def run(self) -> None:
        """Pump events from OpenAI until the session closes."""
        async for raw in self._ws:
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            await self.handle_event(event)
            if event.get("type") == "session.closed":
                break

    async def handle_event(self, event: dict[str, Any]) -> None:
        kind = event.get("type", "")
        if kind == "session.output_audio.delta":
            await self._client_sink({"type": "audio", "audio": event.get("delta", "")})
        elif kind == "session.input_transcript.delta":
            delta = event.get("delta", "")
            self._user_transcript.append(delta)
            # The user is talking: the client should stop playing the reply.
            await self._client_sink({"type": "user_transcript", "delta": delta})
        elif kind == "session.output_transcript.delta":
            await self._client_sink({"type": "assistant_transcript", "delta": event.get("delta", "")})
        elif kind == "session.delegation.created":
            delegation_id = (event.get("delegation") or {}).get("id", "")
            # The delegation carries no task text, so use what the user said.
            request = "".join(self._user_transcript).strip()
            self._user_transcript = []
            task = asyncio.create_task(self._delegate(delegation_id, request))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        elif kind == "session.started":
            await self._client_sink({"type": "ready"})
        elif kind == "error":
            logger.warning("GPT-Live error: %s", event)
            await self._client_sink({"type": "error", "message": str(event.get("error", event))})
        elif kind == "session.closed":
            await self._client_sink({"type": "closed", "usage": event.get("usage")})

    async def _delegate(self, delegation_id: str, request: str) -> None:
        logger.info("GPT-Live delegation %s: %s", delegation_id, request[:100])
        await self._client_sink({"type": "working", "request": request})
        await self._send({
            "type": "session.thinking.append",
            "delegation_id": delegation_id,
            "content": "JARVIS is working on this now. Nothing has been completed yet.",
        })
        try:
            result = await self._runner(request) if request else "I didn't catch the request."
        except Exception as exc:
            logger.error("Delegated request failed: %s", exc)
            result = "Sorry, I couldn't complete that."
        for piece in split_for_append(result):
            await self._send({
                "type": "session.commentary.append",
                "delegation_id": delegation_id,
                "content": piece,
            })
        await self._client_sink({"type": "result", "text": result})
