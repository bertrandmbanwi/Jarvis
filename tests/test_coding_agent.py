"""Coding-agent delegation: Codex CLI or Claude Code."""

import stat

import pytest

from jarvis.config import settings
from jarvis.tools import claude_code, coding_agent


@pytest.mark.parametrize(
    ("setting", "provider", "has_codex", "has_claude", "expected"),
    [
        ("codex", "anthropic", False, True, "codex"),
        ("claude", "openai", True, True, "claude"),
        ("auto", "openai", True, True, "codex"),
        ("auto", "anthropic", True, True, "claude"),
        ("auto", "openai", False, True, "claude"),
        ("auto", "openai", False, False, "codex"),
    ],
)
def test_choose_agent(monkeypatch, setting, provider, has_codex, has_claude, expected):
    monkeypatch.setattr(settings, "CODING_AGENT", setting)
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(coding_agent, "find_codex_binary", lambda: "/bin/codex" if has_codex else None)
    monkeypatch.setattr(claude_code, "_find_claude_binary", lambda: "/bin/claude" if has_claude else None)
    assert coding_agent.choose_agent() == expected


def test_codex_command_is_sandboxed_and_ends_options(monkeypatch):
    monkeypatch.setattr(settings, "CODEX_MODEL", "")
    cmd = coding_agent.build_codex_command("/bin/codex", "-rf everything", "/tmp/p", "/tmp/out")
    assert cmd[:2] == ["/bin/codex", "exec"]
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
    assert cmd[-2:] == ["--", "-rf everything"]
    resumed = coding_agent.build_codex_command("/bin/codex", "t", "/tmp", "/o", continue_session=True)
    assert resumed[1:4] == ["exec", "resume", "--last"]


@pytest.mark.asyncio
async def test_run_codex_returns_last_message(monkeypatch, tmp_path):
    fake = tmp_path / "codex"
    fake.write_text(
        "#!/bin/sh\n"
        'while [ "$1" != "--output-last-message" ]; do shift; done\n'
        'echo "Created app.py" > "$2"\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(coding_agent, "find_codex_binary", lambda: str(fake))
    assert await coding_agent.run_codex("make an app", str(tmp_path)) == "Created app.py"


@pytest.mark.asyncio
async def test_run_codex_reports_missing_cli(monkeypatch):
    monkeypatch.setattr(coding_agent, "find_codex_binary", lambda: None)
    assert "Codex CLI not found" in await coding_agent.run_codex("x")
