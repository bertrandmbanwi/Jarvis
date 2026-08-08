from __future__ import annotations

from pathlib import Path


def test_mayass_launch_runbook_exists_and_covers_modes() -> None:
    runbook = Path(".hermes/runbooks/mayass-launch-modes.md")
    text = runbook.read_text(encoding="utf-8")

    assert "mayass-server-safe" in text
    assert "mayass-voice-browser" in text
    assert "mayass-work" in text
    assert "mayass-remote" in text
    assert "MAYASS_REMOTE_ENABLED=false" in text
    assert "JARVIS_ENABLE_TUNNEL=false" in text
    assert "remote remains off" in text.lower()


def test_mayass_launch_runbook_is_operator_ready() -> None:
    runbook = Path(".hermes/runbooks/mayass-launch-modes.md")
    text = runbook.read_text(encoding="utf-8").lower()

    assert "how to open" in text
    assert "how to stop" in text
    assert "browser voice" in text
    assert "push-to-talk" in text
    assert "duplicate audio" in text
    assert "do not enable remote" in text
