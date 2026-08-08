"""Text-only bridge from MayAss to Hermes/Maymint.

Phase 3 only proves the bridge contract. It does not route `/chat`,
invoke voice, migrate memory, or claim tool ownership.
"""
from __future__ import annotations

import asyncio
import re
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis.config import settings
from jarvis.core import pending_actions
from jarvis.core.mayass_identity import MAYASS_IDENTITY

Runner = Callable[[str, float], Awaitable[str]]


@dataclass(frozen=True)
class MayAssBridgeRequest:
    text: str
    source: str = "mayass"
    mode: str = "realtime"
    session_id: str = ""
    wants_voice: bool = False
    allow_tools: bool = False
    confirmation_policy: str = "safe-only"


@dataclass(frozen=True)
class MayAssBridgeResponse:
    text: str
    backend: str = "hermes"
    mode: str = "realtime"
    ok: bool = True
    error: str = ""
    action_cards: tuple[dict[str, Any], ...] = ()
    pending_action: dict[str, Any] | None = None


@dataclass(frozen=True)
class MayAssActionIntent:
    action_type: str
    risk: str
    summary: str
    affected_targets: tuple[str, ...]
    reversible: bool
    reason: str
    consequence_if_denied: str
    requires_confirmation: bool = True
    execution_supported: bool = False

    @property
    def permanent_policy_key(self) -> str:
        target = self.affected_targets[0] if self.affected_targets else "*"
        return f"{self.action_type}:{target}"

    def action_card(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "risk": self.risk,
            "summary": self.summary,
            "affected_targets": list(self.affected_targets),
            "reversible": self.reversible,
            "reason": self.reason,
            "consequence_if_denied": self.consequence_if_denied,
            "requires_confirmation": self.requires_confirmation,
            "execution_supported": self.execution_supported,
            "permanent_policy_key": self.permanent_policy_key,
        }


class MayAssBridge:
    """Call Hermes through a text-only prompt envelope."""

    def __init__(self, runner: Runner | None = None, timeout: float = 45.0):
        self._runner = runner or _run_hermes
        self._timeout = timeout

    async def process(self, request: MayAssBridgeRequest) -> MayAssBridgeResponse:
        mode = _normalize_mode(request.mode)
        intent = classify_mayass_action_intent(request.text)
        if intent is not None:
            return _planned_action_response(intent, mode)

        prompt = build_prompt_envelope(request, mode)
        try:
            text = _clean_hermes_output(await self._runner(prompt, self._timeout))
        except Exception as exc:
            return MayAssBridgeResponse(text="", mode=mode, ok=False, error=str(exc))

        return MayAssBridgeResponse(text=text, mode=mode)


def classify_mayass_action_intent(text: str) -> MayAssActionIntent | None:
    """Conservative Phase 7A action classifier; plans only, never executes."""
    message = text.strip()
    lowered = message.lower()

    if "อ่านอย่างเดียว" in message and ("สถานะระบบ" in message or "system status" in lowered):
        return MayAssActionIntent(
            action_type="system_status",
            risk="low",
            summary="มายจะตรวจสถานะระบบแบบอ่านอย่างเดียว",
            affected_targets=("local system",),
            reversible=True,
            reason="บอสขอสถานะระบบแบบไม่เปลี่ยนแปลงอะไร",
            consequence_if_denied="มายจะไม่ตรวจสถานะระบบ",
            requires_confirmation=False,
        )

    delete_target = _extract_delete_target(message)
    if delete_target:
        return MayAssActionIntent(
            action_type="delete_file",
            risk="high",
            summary=f"มายกำลังจะลบไฟล์ {delete_target}",
            affected_targets=(delete_target,),
            reversible=False,
            reason="บอสขอให้ลบไฟล์นี้",
            consequence_if_denied="ไฟล์จะยังอยู่เหมือนเดิม",
        )

    shell_command = _extract_shell_command(message)
    if shell_command:
        return MayAssActionIntent(
            action_type="run_shell",
            risk="critical" if _looks_destructive_shell(shell_command) else "high",
            summary=f"มายกำลังจะรันคำสั่ง shell: {shell_command}",
            affected_targets=("local shell",),
            reversible=False,
            reason="บอสขอให้รันคำสั่งผ่าน shell",
            consequence_if_denied="คำสั่งจะไม่ถูกรัน",
        )

    return None


def _planned_action_response(intent: MayAssActionIntent, mode: str) -> MayAssBridgeResponse:
    card = intent.action_card()
    if not intent.requires_confirmation:
        return MayAssBridgeResponse(
            text="สถานะระบบแบบอ่านอย่างเดียว: MayAss/Hermes ownership boundary พร้อมใช้งานค่ะ บอส — ไม่มีการเปลี่ยนแปลงไฟล์หรือรันคำสั่งใด ๆ",
            mode=mode,
            action_cards=(card,),
        )

    action = pending_actions.create_pending_action(
        action_type=intent.action_type,
        summary=intent.summary,
        risk=intent.risk,
        affected_targets=intent.affected_targets,
        reversible=intent.reversible,
        reason=intent.reason,
        consequence_if_denied=intent.consequence_if_denied,
        permanent_policy_key=intent.permanent_policy_key,
    )
    return MayAssBridgeResponse(
        text="มายเตรียม action card ไว้แล้วค่ะ รอให้บอสยืนยันก่อน มายจะยังไม่ execute tool จริงใน Phase 7A นะคะ",
        mode=mode,
        action_cards=(card,),
        pending_action=action.public(),
    )


def _extract_delete_target(message: str) -> str:
    patterns = (
        r"(?:delete file|remove file)\s+([^\s]+)",
        r"ลบไฟล์(?:สมมติ)?(?:ชื่อ)?\s*([^\s]+)",
        r"ลบ\s+ไฟล์(?:สมมติ)?(?:ชื่อ)?\s*([^\s]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return _clean_target(match.group(1))
    return ""


def _clean_target(target: str) -> str:
    return target.strip("'\".,，。:：")


def _extract_path_after(message: str, markers: list[str]) -> str:
    for marker in markers:
        match = re.search(rf"{re.escape(marker)}\s+([^\s]+)", message, flags=re.IGNORECASE)
        if match:
            return _clean_target(match.group(1))
    return ""


def _extract_shell_command(message: str) -> str:
    match = re.search(r"(?:รันคำสั่ง|run command|shell)\s+(.+?)(?:\s+ให้หน่อย|$)", message, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _looks_destructive_shell(command: str) -> bool:
    return bool(re.search(r"\b(rm\s+-rf|sudo|mkfs|dd\s+if=|chmod\s+-R|chown\s+-R)\b", command))

async def _run_hermes(prompt: str, timeout: float) -> str:
    command = shlex.split(settings.MAYASS_HERMES_COMMAND)
    command = _build_hermes_command(command, prompt)
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"Hermes subprocess timed out after {timeout:.0f}s") from None

    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Hermes subprocess exited with {proc.returncode}")

    return stdout.decode("utf-8", errors="replace").strip()


def build_prompt_envelope(request: MayAssBridgeRequest, mode: str | None = None) -> str:
    active_mode = _normalize_mode(mode or request.mode)
    identity = MAYASS_IDENTITY
    style = (
        "ตอบสั้น อบอุ่น เป็นธรรมชาติ เหมาะกับ realtime UI"
        if active_mode == "realtime"
        else "ตอบเป็นระบบ กระชับ ใช้กับโหมดทำงาน"
    )
    return "\n".join(
        [
            "You are Maymint, user-facing assistant persona for MayAss.",
            f"Thai name: {identity.assistant_short_name}",
            f"Codename: {identity.codename}",
            f"User name: {identity.user_display_name}",
            f"mode={active_mode}",
            f"source={request.source}",
            f"session_id={request.session_id}",
            f"wants_voice={request.wants_voice}",
            f"allow_tools={request.allow_tools}",
            f"confirmation_policy={request.confirmation_policy}",
            f"Style: {style}",
            _hermes_runtime_hint(),
            "Memory quarantine: use MayAss identity and the current conversation only; do not use legacy Jarvis profile, old saved location, old honorifics, or old local memories unless the user explicitly provides them in this chat.",
            "When asked about provider/model/backend, answer from Hermes runtime exactly.",
            "Do not claim to be the old shell identity.",
            "Reply in Thai unless the user asks otherwise.",
            "Use Maymint's warm feminine Thai tone and endings such as ค่ะ or นะคะ; do not use ครับ.",
            "User message:",
            request.text,
        ]
    )


def _normalize_mode(mode: str) -> str:
    value = (mode or "realtime").strip().lower()
    return value if value in {"realtime", "work"} else settings.MAYASS_DEFAULT_MODE


def _hermes_runtime_hint() -> str:
    """Expose non-secret Hermes provider/model config to Maymint."""
    provider = model = max_tokens = "unknown"
    config_path = Path.home() / ".hermes" / "config.yaml"
    try:
        in_model = False
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line == "model:":
                in_model = True
                continue
            if in_model and raw_line and not raw_line.startswith(" "):
                break
            if not in_model or ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip().strip("'\"")
            if key == "provider":
                provider = value or provider
            elif key == "default":
                model = value or model
            elif key == "max_tokens":
                max_tokens = value or max_tokens
    except OSError:
        pass

    return f"Hermes runtime: command={settings.MAYASS_HERMES_COMMAND}; provider={provider}; model={model}; max_tokens={max_tokens}"


def _build_hermes_command(command: list[str], prompt: str) -> list[str]:
    """Build a Hermes command that prints only the final answer when possible."""
    if any("{prompt}" in part for part in command):
        return [part.replace("{prompt}", prompt) for part in command]

    if command[-1:] and command[-1] in {"-z", "--oneshot", "-q", "--query"}:
        return [*command, prompt]

    return [*command, "-z", prompt]


def _clean_hermes_output(output: str) -> str:
    """Reject Hermes control/error output so it never appears as Maymint text."""
    text = output.strip()
    if not text:
        raise RuntimeError("Hermes returned an empty response")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    non_session_lines = [line for line in lines if not line.lower().startswith("session_id:")]
    joined = "\n".join(non_session_lines).strip()

    if not joined:
        raise RuntimeError(f"Hermes returned session metadata instead of a response: {text}")

    if re.search(r"\bHTTP\s+\d{3}\b", joined) or "requires more credits" in joined.lower():
        raise RuntimeError(joined)

    return joined
