"""
Unit tests for backend/appointment_service.py — conflict detection in dispatch.

These tests focus on the slot re-verification path inside dispatch_appointment
that catches race conditions between availability check and persistence.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


SALON_HOURS = {
    "monday": {"open": "09:00", "close": "17:00"},
    "tuesday": {"open": "09:00", "close": "17:00"},
    "wednesday": {"open": "09:00", "close": "17:00"},
    "thursday": {"open": "09:00", "close": "17:00"},
    "friday": {"open": "09:00", "close": "17:00"},
    "saturday": {"open": "09:00", "close": "17:00"},
    "sunday": {"closed": True},
}

CONFIG = {
    "slot_interval_minutes": 30,
    "slot_capacity": 1,
    "operating_hours": SALON_HOURS,
    "timezone": "UTC",
    "sms_enabled": True,
}

SERVICES = [{"name": "Haircut", "duration_minutes": 30}]


def _sms_success():
    return SimpleNamespace(success=True, message_id="m1")


# ---------------------------------------------------------------------------
# Confirmed bookings: clean slot → status="confirmed", SMS sent
# ---------------------------------------------------------------------------

async def test_dispatch_with_free_slot_confirms_and_sends_sms(async_db, monkeypatch):
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",  # Monday
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Snip Salon", "timezone": "UTC"},
        config=CONFIG,
        services=SERVICES,
        db=async_db,
    )

    assert result["success"] is True
    assert result["slot_conflict"] is False
    assert result["sms_sent"] is True

    appt = await async_db.appointments.find_one({"id": result["appointment_id"]})
    assert appt["status"] == "confirmed"


async def test_dispatch_reports_failure_when_not_persisted():
    """B2-1: with no database handle the booking cannot be saved, so success is
    False and an error reason is surfaced — a lost booking never reports success."""
    from appointment_service import dispatch_appointment

    result = await dispatch_appointment(
        booking={
            "service_name": "Haircut",
            "preferred_date": "2030-06-03",
            "preferred_time": "10:00 AM",
            "customer_name": "Joe",
            "customer_phone": "+15551234567",
        },
        restaurant={"id": "rest_a", "name": "Snip Salon", "timezone": "UTC"},
        config=CONFIG,
        services=SERVICES,
        db=None,
    )

    assert result["success"] is False
    assert result.get("error")


async def test_dispatch_detects_conflict_when_slot_filled_between_check_and_save(async_db, monkeypatch):
    """If another booking occupies the slot before save, status='conflict'; SMS suppressed."""
    from appointment_service import dispatch_appointment

    send_mock = AsyncMock(return_value=_sms_success())
    monkeypatch.setattr("telnyx_service.send_sms", send_mock)

    # Pre-occupy the slot (capacity 1)
    await async_db.appointments.insert_one({
        "id": "earlier",
        "restaurant_id": "rest_a",
        "scheduled_date": "2030-06-03",
        "scheduled_time": "10:00",
        "status": "confirmed",
    })

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Snip Salon", "timezone": "UTC"},
        config=CONFIG,
        services=SERVICES,
        db=async_db,
    )

    assert result["slot_conflict"] is True
    assert result["sms_sent"] is False
    send_mock.assert_not_awaited()

    new_appt = await async_db.appointments.find_one({"id": result["appointment_id"]})
    assert new_appt["status"] == "conflict"


async def test_dispatch_with_higher_capacity_avoids_conflict(async_db, monkeypatch):
    """When slot_capacity=2 and one is taken, the second booking should still succeed."""
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    await async_db.appointments.insert_one({
        "id": "earlier",
        "restaurant_id": "rest_a",
        "scheduled_date": "2030-06-03",
        "scheduled_time": "10:00",
        "status": "confirmed",
    })

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Snip Salon", "timezone": "UTC"},
        config={**CONFIG, "slot_capacity": 2},
        services=SERVICES,
        db=async_db,
    )

    assert result["slot_conflict"] is False
    assert result["sms_sent"] is True


# ---------------------------------------------------------------------------
# Blocked slot: detected as conflict
# ---------------------------------------------------------------------------

async def test_dispatch_detects_blocked_slot_as_conflict(async_db, monkeypatch):
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    await async_db.blocked_slots.insert_one({
        "restaurant_id": "rest_a",
        "date": "2030-06-03",
        "slot_time": "10:00",
    })

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Snip Salon", "timezone": "UTC"},
        config=CONFIG,
        services=SERVICES,
        db=async_db,
    )
    assert result["slot_conflict"] is True


# ---------------------------------------------------------------------------
# Race-check is skipped (non-fatal) when time can't be parsed
# ---------------------------------------------------------------------------

async def test_dispatch_with_unparseable_time_still_saves(async_db, monkeypatch):
    """An unparseable preferred_time skips the conflict check and confirms."""
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "not-a-time",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Snip Salon", "timezone": "UTC"},
        config=CONFIG,
        services=SERVICES,
        db=async_db,
    )
    # Stored as confirmed (race check skipped)
    assert result["success"] is True
    assert result["slot_conflict"] is False
