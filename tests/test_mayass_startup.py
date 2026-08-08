"""Tests for MayAss startup isolation.

Cleanup pass scope: when MayAss owns `/chat`, server startup must not initialize
legacy JarvisBrain/Ollama or proactive hooks that make the runtime look like a
second brain.
"""

import pytest


class FakeProactive:
    def __init__(self):
        self._on_suggestion = None


class FakeBrain:
    def __init__(self):
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self._on_plan_progress = None
        self.proactive = FakeProactive()

    async def initialize(self):
        self.initialize_calls += 1
        return True

    async def shutdown(self):
        self.shutdown_calls += 1


async def idle_loop():
    import asyncio

    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_lifespan_skips_legacy_brain_when_mayass_enabled(monkeypatch):
    from jarvis.core import server

    fake_brain = FakeBrain()
    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", True)
    monkeypatch.setattr(server, "brain", fake_brain)
    monkeypatch.setattr(server.jobs, "init_jobs_db", lambda: None)
    monkeypatch.setattr(server, "_session_cleanup_loop", idle_loop)
    monkeypatch.setattr(server, "_workflow_scheduler_loop", idle_loop)

    async with server.lifespan(server.app):
        pass

    assert fake_brain.initialize_calls == 0
    assert fake_brain.shutdown_calls == 0
    assert fake_brain._on_plan_progress is None
    assert fake_brain.proactive._on_suggestion is None


@pytest.mark.asyncio
async def test_lifespan_keeps_legacy_brain_when_mayass_disabled(monkeypatch):
    from jarvis.core import server

    fake_brain = FakeBrain()
    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", False)
    monkeypatch.setattr(server, "brain", fake_brain)
    monkeypatch.setattr(server.jobs, "init_jobs_db", lambda: None)
    monkeypatch.setattr(server, "_session_cleanup_loop", idle_loop)
    monkeypatch.setattr(server, "_workflow_scheduler_loop", idle_loop)

    async with server.lifespan(server.app):
        pass

    assert fake_brain.initialize_calls == 1
    assert fake_brain.shutdown_calls == 1
    assert fake_brain._on_plan_progress is server.broadcast_plan_progress
    assert fake_brain.proactive._on_suggestion is server._deliver_proactive_suggestion
