"""Spoken confirmation for high-risk tool calls in voice mode.

When the executor needs approval for a high-risk tool, one registered channel is
this spoken prompt: Jarvis reads back the action and captures a yes/no. Anything
ambiguous, silent, or negative is treated as a denial (fail safe).
"""
import logging
import re
from typing import Any, Protocol

from jarvis.core import pending_actions

logger = logging.getLogger("jarvis.voice.confirm")

VOICE_CONFIRM_TIMEOUT_S = 12.0

_AFFIRMATIVE_WORDS = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
    "confirmed", "affirmative", "proceed", "approved", "approve",
}
_AFFIRMATIVE_PHRASES = ("go ahead", "do it", "send it", "please do", "go for it")
_NEGATIVE_WORDS = {"no", "nope", "nah", "cancel", "stop", "negative", "abort", "deny"}
_NEGATIVE_PHRASES = ("do not", "don't", "never mind", "nevermind", "hold off", "not now")


def parse_affirmative(text: str) -> bool:
    """Return True only for a clear yes; deny on negative, ambiguous, or empty."""
    lowered = text.strip().lower()
    if not lowered:
        return False
    words = set(re.findall(r"[a-z']+", lowered))
    if words & _NEGATIVE_WORDS or any(phrase in lowered for phrase in _NEGATIVE_PHRASES):
        return False
    return bool(words & _AFFIRMATIVE_WORDS) or any(phrase in lowered for phrase in _AFFIRMATIVE_PHRASES)


class _Speaker(Protocol):
    async def speak(self, text: str, **kwargs: Any) -> Any: ...


class _Listener(Protocol):
    async def capture_reply(self, timeout: float = ...) -> str: ...


async def run_voice_confirmation(
    speaker: _Speaker,
    listener: _Listener,
    action_id: str,
    summary: str,
    *,
    timeout: float = VOICE_CONFIRM_TIMEOUT_S,
) -> None:
    """Speak the action back, capture a yes/no, and resolve the confirmation.

    If nothing intelligible is heard, the action is left unresolved so another
    channel (or request_confirmation's own timeout) can settle it.
    """
    await speaker.speak(f"{summary}. Shall I proceed? Say yes or no.")
    reply = await listener.capture_reply(timeout=timeout)
    if not reply:
        logger.info("No spoken reply for confirmation %s; leaving it for other channels.", action_id)
        return
    approved = parse_affirmative(reply)
    logger.info("Spoken confirmation for %s: '%s' -> %s", action_id, reply, approved)
    pending_actions.resolve(action_id, approved)
