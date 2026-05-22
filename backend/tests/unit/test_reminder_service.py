"""
Unit tests for backend/reminder_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def _sms_success(message_id="msg_1"):
    return SimpleNamespace(success=True, message_id=message_id, error_code=None, error_message=None)


def _sms_failure(error_code="X", error_message="boom"):
    return SimpleNamespace(success=False, message_id=None, error_code=error_code, error_message=error_message)


# ---------------------------------------------------------------------------
# get_appointments_due_for_reminder
# ---------------------------------------------------------------------------

async def test_get_appointments_due_filters_by_date_and_status(async_db, frozen_time):
    from reminder_service import get_appointments_due_for_reminder

    # Frozen at 2026-05-21T12:00 UTC → 24h ahead is 2026-05-22
    await async_db.appointments.insert_many([
        {
            "id": "a1",
            "status": "confirmed",
            "scheduled_date": "2026-05-22",
        },
        {
            "id": "a2",
            "status": "confirmed",
            "scheduled_date": "2026-05-22",
            "reminder_sent": True,
        },
        {
            "id": "a3",
            "status": "cancelled",
            "scheduled_date": "2026-05-22",
        },
        {
            "id": "a4",
            "status": "confirmed",
            "scheduled_date": "2026-06-01",  # later
        },
    ])

    found = await get_appointments_due_for_reminder(async_db, hours_ahead=24)
    found_ids = sorted(a["id"] for a in found)
    assert found_ids == ["a1"]


# ---------------------------------------------------------------------------
# send_reminder_sms
# ---------------------------------------------------------------------------

async def test_send_reminder_sms_constructs_body_and_calls_telnyx(monkeypatch):
    from reminder_service import send_reminder_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["to"] = to
        captured["body"] = body
        captured["idempotency_key"] = idempotency_key
        captured["metadata"] = metadata
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    ok = await send_reminder_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        service_name="Haircut",
        scheduled_date="2026-05-22",
        scheduled_time="2:00 PM",
        business_name="Snip Salon",
        duration_minutes=45,
    )

    assert ok is True
    assert captured["to"] == "+15551234567"
    assert "Hi Joe" in captured["body"]
    assert "Haircut" in captured["body"]
    assert "Snip Salon" in captured["body"]
    assert "45" in captured["body"]
    assert captured["idempotency_key"] == "reminder:2026-05-22:2:00 PM:+15551234567"
    assert captured["metadata"]["purpose"] == "appointment_reminder"


async def test_send_reminder_sms_omits_greeting_if_no_name(monkeypatch):
    from reminder_service import send_reminder_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_reminder_sms(
        customer_phone="+15551234567",
        customer_name="",
        service_name="X",
        scheduled_date="2026-05-22",
        scheduled_time="3:00 PM",
        business_name="Biz",
    )
    assert not captured["body"].startswith("Hi ")


async def test_send_reminder_sms_falls_back_to_raw_date_on_parse_failure(monkeypatch):
    from reminder_service import send_reminder_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_reminder_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        service_name="X",
        scheduled_date="not-a-date",
        scheduled_time="3 PM",
        business_name="Biz",
    )
    # The raw value should still appear in the body
    assert "not-a-date" in captured["body"]


# ---------------------------------------------------------------------------
# process_appointment_reminders
# ---------------------------------------------------------------------------

async def test_process_reminders_marks_sent_on_success(async_db, frozen_time, monkeypatch):
    from reminder_service import process_appointment_reminders

    await async_db.restaurants.insert_one({"id": "rest_1", "name": "Snip Salon"})
    await async_db.appointments.insert_one({
        "id": "appt_1",
        "restaurant_id": "rest_1",
        "status": "confirmed",
        "scheduled_date": "2026-05-22",
        "scheduled_time": "2:00 PM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
        "service_name": "Haircut",
        "duration_minutes": 30,
    })

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    result = await process_appointment_reminders(async_db)
    assert result["processed"] == 1
    assert result["sent"] == 1
    assert result["failed"] == 0

    updated = await async_db.appointments.find_one({"id": "appt_1"})
    assert updated["reminder_sent"] is True
    assert updated["reminder_sent_at"]


async def test_process_reminders_counts_failures_without_marking(async_db, frozen_time, monkeypatch):
    from reminder_service import process_appointment_reminders

    await async_db.restaurants.insert_one({"id": "rest_1", "name": "Snip"})
    await async_db.appointments.insert_one({
        "id": "appt_1",
        "restaurant_id": "rest_1",
        "status": "confirmed",
        "scheduled_date": "2026-05-22",
        "scheduled_time": "2:00 PM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
        "service_name": "Haircut",
    })

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_failure()))

    result = await process_appointment_reminders(async_db)
    assert result["sent"] == 0
    assert result["failed"] == 1

    updated = await async_db.appointments.find_one({"id": "appt_1"})
    assert updated.get("reminder_sent") is not True


async def test_process_reminders_returns_error_on_exception(monkeypatch):
    from reminder_service import process_appointment_reminders

    class _BadDb:
        appointments = SimpleNamespace(find=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))

    result = await process_appointment_reminders(_BadDb())
    assert "error" in result


# ---------------------------------------------------------------------------
# send_single_reminder
# ---------------------------------------------------------------------------

async def test_send_single_reminder_marks_sent_on_success(async_db, monkeypatch):
    from reminder_service import send_single_reminder

    await async_db.restaurants.insert_one({"id": "rest_1", "name": "Snip"})
    await async_db.appointments.insert_one({
        "id": "appt_1",
        "restaurant_id": "rest_1",
        "status": "confirmed",
        "scheduled_date": "2026-05-22",
        "scheduled_time": "2:00 PM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
        "service_name": "Haircut",
    })

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    ok = await send_single_reminder(async_db, "appt_1")
    assert ok is True

    updated = await async_db.appointments.find_one({"id": "appt_1"})
    assert updated["reminder_sent"] is True


async def test_send_single_reminder_returns_false_for_missing_appointment(async_db):
    from reminder_service import send_single_reminder
    assert await send_single_reminder(async_db, "missing") is False


async def test_send_single_reminder_returns_false_for_non_confirmed(async_db):
    from reminder_service import send_single_reminder

    await async_db.appointments.insert_one({
        "id": "appt_1",
        "status": "cancelled",
        "scheduled_date": "2026-05-22",
        "scheduled_time": "2:00 PM",
    })
    assert await send_single_reminder(async_db, "appt_1") is False
