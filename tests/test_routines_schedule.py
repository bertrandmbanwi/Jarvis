"""Scheduled routines: due-time logic and delivery."""

from datetime import datetime, timedelta

import pytest

from jarvis.core import routines


@pytest.fixture(autouse=True)
def routines_file(tmp_path, monkeypatch):
    monkeypatch.setattr(routines, "ROUTINES_FILE", tmp_path / "routines.json")


def make(schedule_time="07:30", days=None, enabled=True):
    return routines.create_routine("Brief", "brief me", enabled, [], schedule_time, days or [])


MONDAY_0745 = datetime(2026, 9, 28, 7, 45)


def test_default_routines_are_not_scheduled():
    assert all(r["schedule_time"] is None for r in routines.list_routines())
    assert routines.due_routines(MONDAY_0745) == []


def test_routine_is_due_once_after_its_time():
    r = make()
    assert [x["id"] for x in routines.due_routines(MONDAY_0745)] == [r["id"]]
    assert routines.due_routines(MONDAY_0745.replace(hour=7, minute=0)) == []  # too early
    routines.mark_routine_run(r["id"])
    assert routines.due_routines(MONDAY_0745 + timedelta(minutes=5)) == []  # already ran today


def test_weekday_filter_and_lateness_limit():
    make(days=["sat", "sun"])
    assert routines.due_routines(MONDAY_0745) == []
    make()
    assert routines.due_routines(MONDAY_0745.replace(hour=11)) == []  # more than 2h late


def test_disabled_routines_never_run():
    make(enabled=False)
    assert routines.due_routines(MONDAY_0745) == []


def test_schedule_validation():
    assert routines.valid_schedule("07:30", ["mon", "fri"])
    assert routines.valid_schedule(None, [])
    assert not routines.valid_schedule("7:30", [])
    assert not routines.valid_schedule("07:30", ["monday"])
    assert not routines.valid_schedule(None, ["mon"])


@pytest.mark.asyncio
async def test_scheduled_run_delivers_to_ui_and_channels(monkeypatch):
    import os
    from unittest.mock import AsyncMock

    os.environ["JARVIS_REGEN_PIN"] = "false"
    from jarvis.core import notify, server

    r = make()
    monkeypatch.setattr(server.brain, "process", AsyncMock(return_value="Sunny, 2 meetings."))
    monkeypatch.setattr(server.ws_manager, "broadcast_json", AsyncMock())
    sent = []

    async def channel(text):
        sent.append(text)

    notify.add_channel(channel)
    try:
        assert await server.run_scheduled_routine(r) == "Sunny, 2 meetings."
    finally:
        notify.remove_channel(channel)
    assert sent == ["Brief: Sunny, 2 meetings."]
    assert routines.get_routine(r["id"])["last_run_at"] is not None
