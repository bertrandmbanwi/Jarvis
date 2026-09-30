"""Apple's on-device Foundation Model (macOS 26+) through a small Swift helper.

Free, private and offline. Used for the fast tier in offline mode; it has
no tool calling here, so tool work goes to the local server model. The
helper (jarvis/native/apple_fm.swift) is compiled with swiftc on first use
into data/bin/jarvis-fm and rebuilt when the source changes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from jarvis.config import settings

logger = logging.getLogger("jarvis.providers.apple_fm")

SOURCE = Path(__file__).resolve().parents[2] / "native" / "apple_fm.swift"
BINARY = settings.DATA_DIR / "bin" / "jarvis-fm"
TIMEOUT_S = 60.0


def flatten(messages: list[dict[str, str]]) -> str:
    """One prompt from the conversation: earlier turns as context, then the request."""
    if not messages:
        return ""
    *history, last = messages
    if not history:
        return last["content"]
    lines = [f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history]
    return "Conversation so far:\n" + "\n".join(lines) + f"\n\nUser: {last['content']}"


class AppleFoundationModel:
    def __init__(self, binary: Path = BINARY, source: Path = SOURCE):
        self._binary = binary
        self._source = source
        self._available: bool | None = None

    def _build(self) -> bool:
        if self._binary.exists() and self._binary.stat().st_mtime >= self._source.stat().st_mtime:
            return True
        swiftc = shutil.which("swiftc")
        if not swiftc or not self._source.exists():
            return False
        import subprocess  # nosec B404

        self._binary.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(  # nosec B603
            [swiftc, "-parse-as-library", "-O", str(self._source), "-o", str(self._binary)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            logger.warning("Building the Apple Foundation Model helper failed: %s", result.stderr[-500:])
            return False
        return True

    def available(self) -> bool:
        """True when the helper builds and Apple Intelligence reports the model ready."""
        if self._available is None:
            try:
                import subprocess  # nosec B404

                if not self._build():
                    self._available = False
                else:
                    out = subprocess.run(  # nosec B603
                        [str(self._binary), "--check"], capture_output=True, text=True, timeout=20
                    ).stdout
                    info = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
                    self._available = bool(info.get("available"))
                    if not self._available:
                        logger.info("Apple Foundation Model unavailable: %s", info.get("reason", "unknown"))
            except Exception as exc:
                logger.info("Apple Foundation Model unavailable: %s", exc)
                self._available = False
        return self._available

    async def _run(self, args: list[str], request: dict[str, Any]) -> asyncio.subprocess.Process:
        process = await asyncio.create_subprocess_exec(
            str(self._binary), *args,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        if process.stdin is None:
            raise RuntimeError("helper stdin unavailable")
        process.stdin.write(json.dumps(request).encode())
        await process.stdin.drain()
        process.stdin.close()
        return process

    async def respond(
        self, instructions: str, messages: list[dict[str, str]], json_schema: dict[str, Any] | None = None
    ) -> str:
        """Full response text, or "" on failure (callers fall back to another model)."""
        if json_schema is not None:
            instructions += (
                "\nRespond with only a JSON object matching this JSON schema, with no other text:\n"
                + json.dumps(json_schema)
            )
        process = await self._run([], {"instructions": instructions, "prompt": flatten(messages)})
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_S)
        except TimeoutError:
            process.kill()
            return ""
        try:
            data = json.loads(stdout.decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            return ""
        text = str(data.get("text", "")).strip()
        if json_schema is not None:
            # The on-device model may wrap JSON in prose or fences; keep only the object.
            start, end = text.find("{"), text.rfind("}")
            text = text[start:end + 1] if start != -1 and end > start else ""
        return text

    async def stream(self, instructions: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        process = await self._run(["--stream"], {"instructions": instructions, "prompt": flatten(messages)})
        if process.stdout is None:
            return
        async for raw in process.stdout:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if "delta" in event:
                yield str(event["delta"])
            elif event.get("done") or "error" in event:
                break
        await process.wait()
