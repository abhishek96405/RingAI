"""
Unit tests for backend/scheduler_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_scheduler_globals(monkeypatch):
    import scheduler_service
    monkeypatch.setattr(scheduler_service, "_scheduler_task", None, raising=False)
    monkeypatch.setattr(scheduler_service, "_scheduler_running", False, raising=False)
    yield


# ---------------------------------------------------------------------------
# process_reminders_task
# ---------------------------------------------------------------------------

async def test_process_reminders_task_dispatches_websocket_for_successes(monkeypatch):
    from scheduler_service import process_reminders_task

    mock_db = AsyncMock()
    mock_db.appointments.find_one = AsyncMock(return_value={
        "id": "appt_1",
        "restaurant_id": "rest_a",
        "customer_name": "Joe",
        "service_name": "Haircut",
    })

    monkeypatch.setattr(
        "reminder_service.process_appointment_reminders",
        AsyncMock(return_value={
            "sent": 1, "processed": 1, "failed": 0,
            "appointments": [{"id": "appt_1", "success": True}],
        }),
    )

    notify_mock = AsyncMock()
    monkeypatch.setattr("websocket_notifications.notify_appointment_reminder", notify_mock)

    result = await process_reminders_task(mock_db)
    assert result["sent"] == 1
    notify_mock.assert_awaited_once()


async def test_process_reminders_task_skips_failed_reminders(monkeypatch):
    from scheduler_service import process_reminders_task

    mock_db = AsyncMock()

    monkeypatch.setattr(
        "reminder_service.process_appointment_reminders",
        AsyncMock(return_value={
            "sent": 0, "processed": 1, "failed": 1,
            "appointments": [{"id": "appt_1", "success": False}],
        }),
    )

    notify_mock = AsyncMock()
    monkeypatch.setattr("websocket_notifications.notify_appointment_reminder", notify_mock)

    await process_reminders_task(mock_db)
    notify_mock.assert_not_awaited()


async def test_process_reminders_task_swallows_exceptions(monkeypatch):
    from scheduler_service import process_reminders_task

    mock_db = AsyncMock()
    monkeypatch.setattr(
        "reminder_service.process_appointment_reminders",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    result = await process_reminders_task(mock_db)
    assert "error" in result


# ---------------------------------------------------------------------------
# cleanup_old_notifications_task
# ---------------------------------------------------------------------------

async def test_cleanup_old_notifications_task_returns_ok():
    from scheduler_service import cleanup_old_notifications_task
    mock_db = AsyncMock()
    result = await cleanup_old_notifications_task(mock_db, days_old=30)
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# start_scheduler / stop_scheduler / is_scheduler_running
# ---------------------------------------------------------------------------

async def test_start_scheduler_creates_task(monkeypatch):
    import scheduler_service

    # Replace the loop with an immediate-return coroutine so it doesn't hang.
    async def fake_loop(db, reminder_interval_hours=1):
        scheduler_service._scheduler_running = True
        await asyncio.sleep(0)
        scheduler_service._scheduler_running = False

    monkeypatch.setattr(scheduler_service, "scheduler_loop", fake_loop)

    scheduler_service.start_scheduler(db=None)
    assert scheduler_service._scheduler_task is not None
    await asyncio.sleep(0.01)


async def test_start_scheduler_is_idempotent_when_already_running(monkeypatch):
    import scheduler_service

    # Pretend a task is already running and not done.
    class _FakeTask:
        def done(self):
            return False
        def cancel(self):
            pass

    monkeypatch.setattr(scheduler_service, "_scheduler_task", _FakeTask())

    # Should warn and return without overwriting.
    before = scheduler_service._scheduler_task
    scheduler_service.start_scheduler(db=None)
    assert scheduler_service._scheduler_task is before


def test_stop_scheduler_cancels_task():
    import scheduler_service

    class _FakeTask:
        cancelled = False
        def cancel(self):
            self.cancelled = True

    fake = _FakeTask()
    scheduler_service._scheduler_task = fake
    scheduler_service._scheduler_running = True

    scheduler_service.stop_scheduler()
    assert fake.cancelled is True
    assert scheduler_service._scheduler_running is False


def test_is_scheduler_running_reflects_state():
    import scheduler_service
    scheduler_service._scheduler_running = False
    assert scheduler_service.is_scheduler_running() is False
    scheduler_service._scheduler_running = True
    assert scheduler_service.is_scheduler_running() is True


# ---------------------------------------------------------------------------
# scheduler_loop — short-circuit test (run one tick then stop)
# ---------------------------------------------------------------------------

async def test_scheduler_loop_stops_when_running_flag_cleared(monkeypatch):
    import scheduler_service

    monkeypatch.setattr(
        scheduler_service,
        "process_reminders_task",
        AsyncMock(return_value={"sent": 0, "processed": 0}),
    )
    monkeypatch.setattr(
        scheduler_service,
        "cleanup_old_notifications_task",
        AsyncMock(return_value={"status": "ok"}),
    )

    # Make asyncio.sleep clear the running flag so the loop exits.
    original_sleep = asyncio.sleep
    sleeps = []

    async def short_sleep(seconds):
        sleeps.append(seconds)
        scheduler_service._scheduler_running = False
        await original_sleep(0)

    monkeypatch.setattr(scheduler_service.asyncio, "sleep", short_sleep)

    await scheduler_service.scheduler_loop(db=None, reminder_interval_hours=1)
    assert scheduler_service._scheduler_running is False
    assert sleeps  # at least one sleep call happened
