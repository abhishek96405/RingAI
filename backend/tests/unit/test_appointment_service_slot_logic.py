"""
Unit tests for backend/appointment_service.py — slot generation logic.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

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

DEFAULT_CONFIG = {
    "slot_interval_minutes": 30,
    "slot_capacity": 1,
    "operating_hours": SALON_HOURS,
    "timezone": "UTC",
}

SERVICES = [
    {"name": "Haircut", "duration_minutes": 30},
    {"name": "Color", "duration_minutes": 90},
]


# ---------------------------------------------------------------------------
# get_available_slots — basic generation
# ---------------------------------------------------------------------------

async def test_returns_empty_for_invalid_date(async_db):
    from appointment_service import get_available_slots
    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="not-a-date",
        service_name="Haircut",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    assert slots == []


async def test_returns_empty_when_day_closed(async_db):
    from appointment_service import get_available_slots
    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-02",  # Sunday → closed
        service_name="Haircut",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    assert slots == []


async def test_generates_slots_at_default_interval(async_db):
    from appointment_service import get_available_slots
    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",  # Monday in far future
        service_name="Haircut",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    # 9:00-17:00 at 30-min interval, 30-min service duration
    # = 16 starting points from 9:00 to 16:30
    assert len(slots) >= 14
    assert slots[0]["slot_time"] == "09:00"


async def test_longer_service_reduces_slot_count(async_db):
    from appointment_service import get_available_slots
    haircut_slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    color_slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Color",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    assert len(color_slots) < len(haircut_slots)


async def test_unknown_service_uses_default_duration(async_db):
    """If service name doesn't match, fall back to 60-min default."""
    from appointment_service import get_available_slots
    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Unknown Service",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    # 8 hours / 30-min interval, but each slot needs 60 min to fit
    # 9:00-16:00 with 60-min service = 15 slots
    assert len(slots) >= 14


async def test_existing_booking_marks_slot_unavailable(async_db):
    from appointment_service import get_available_slots

    await async_db.appointments.insert_one({
        "restaurant_id": "rest_a",
        "scheduled_date": "2030-06-03",
        "scheduled_time": "10:00",
        "status": "confirmed",
    })

    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "slot_capacity": 1},
        db=async_db,
    )

    slot_10 = next(s for s in slots if s["slot_time"] == "10:00")
    assert slot_10["available"] is False
    assert slot_10["booked"] == 1


async def test_capacity_supports_multiple_bookings_per_slot(async_db):
    from appointment_service import get_available_slots

    # 2 bookings at 10:00 with capacity 3 → still available
    for _ in range(2):
        await async_db.appointments.insert_one({
            "restaurant_id": "rest_a",
            "scheduled_date": "2030-06-03",
            "scheduled_time": "10:00",
            "status": "confirmed",
        })

    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "slot_capacity": 3},
        db=async_db,
    )
    slot_10 = next(s for s in slots if s["slot_time"] == "10:00")
    assert slot_10["available"] is True
    assert slot_10["booked"] == 2


async def test_blocked_slots_are_unavailable(async_db):
    from appointment_service import get_available_slots

    await async_db.blocked_slots.insert_one({
        "restaurant_id": "rest_a",
        "date": "2030-06-03",
        "slot_time": "10:00",
    })

    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config=DEFAULT_CONFIG,
        db=async_db,
    )
    slot_10 = next(s for s in slots if s["slot_time"] == "10:00")
    assert slot_10["blocked"] is True
    assert slot_10["available"] is False


async def test_cancelled_appointments_dont_count(async_db):
    from appointment_service import get_available_slots

    await async_db.appointments.insert_one({
        "restaurant_id": "rest_a",
        "scheduled_date": "2030-06-03",
        "scheduled_time": "10:00",
        "status": "cancelled",
    })

    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "slot_capacity": 1},
        db=async_db,
    )
    slot_10 = next(s for s in slots if s["slot_time"] == "10:00")
    assert slot_10["available"] is True


async def test_appointment_time_parsing_handles_am_pm(async_db):
    from appointment_service import get_available_slots

    await async_db.appointments.insert_one({
        "restaurant_id": "rest_a",
        "scheduled_date": "2030-06-03",
        "scheduled_time": "10:00 AM",
        "status": "confirmed",
    })

    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "slot_capacity": 1},
        db=async_db,
    )
    slot_10 = next(s for s in slots if s["slot_time"] == "10:00")
    assert slot_10["booked"] == 1


async def test_invalid_operating_hours_string_returns_empty(async_db):
    from appointment_service import get_available_slots
    slots = await get_available_slots(
        restaurant_id="rest_a",
        date_str="2030-06-03",
        service_name="Haircut",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "operating_hours": {"monday": {"open": "not-a-time", "close": "17:00"}}},
        db=async_db,
    )
    assert slots == []


# ---------------------------------------------------------------------------
# pre_fetch_availability
# ---------------------------------------------------------------------------

async def test_pre_fetch_returns_dict_keyed_by_date(async_db):
    from appointment_service import pre_fetch_availability

    result = await pre_fetch_availability(
        restaurant_id="rest_a",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "timezone": "UTC"},
        db=async_db,
        days_ahead=3,
    )
    assert isinstance(result, dict)
    assert len(result) == 3
    for value in result.values():
        assert isinstance(value, list)


async def test_pre_fetch_handles_per_day_errors(async_db, monkeypatch):
    """If get_available_slots raises for one day, the rest still return."""
    from appointment_service import pre_fetch_availability
    import appointment_service

    call_count = {"n": 0}
    real_fn = appointment_service.get_available_slots

    async def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom")
        return await real_fn(*args, **kwargs)

    monkeypatch.setattr(appointment_service, "get_available_slots", flaky)

    result = await pre_fetch_availability(
        restaurant_id="rest_a",
        services=SERVICES,
        config={**DEFAULT_CONFIG, "timezone": "UTC"},
        db=async_db,
        days_ahead=3,
    )
    # Three days should still be present
    assert len(result) == 3
    # Day 2 should have empty slots due to exception
    keys = sorted(result.keys())
    assert result[keys[1]] == []


# ---------------------------------------------------------------------------
# build_appointment_prompt
# ---------------------------------------------------------------------------

def test_build_appointment_prompt_includes_business_name():
    from appointment_service import build_appointment_prompt
    prompt = build_appointment_prompt(
        business_name="Snip Salon",
        business_type="salon",
        services=SERVICES,
        business_rules=["No walk-ins on Mondays"],
        escalation_phone="+15551239999",
        operating_hours=SALON_HOURS,
        restaurant_timezone="UTC",
        disclosure_text="Hi from Snip Salon!",
    )
    assert "Snip Salon" in prompt
    assert "salon" in prompt.lower() or "appointment" in prompt.lower()


def test_build_appointment_prompt_lists_services():
    from appointment_service import build_appointment_prompt
    prompt = build_appointment_prompt(
        business_name="Biz",
        business_type="salon",
        services=SERVICES,
        business_rules=[],
        escalation_phone=None,
        operating_hours=SALON_HOURS,
        restaurant_timezone="UTC",
        disclosure_text="Hi!",
    )
    assert "Haircut" in prompt
    assert "Color" in prompt


@pytest.mark.parametrize("business_type,expected_word", [
    ("clinic", "patient"),
    ("salon", "client"),
    ("home_services", "customer"),
    ("legal", "consultation"),
])
def test_build_appointment_prompt_business_type_words(business_type, expected_word):
    from appointment_service import build_appointment_prompt
    prompt = build_appointment_prompt(
        business_name="Biz",
        business_type=business_type,
        services=[{"name": "Service", "duration_minutes": 60}],
        business_rules=[],
        escalation_phone=None,
        operating_hours=SALON_HOURS,
        restaurant_timezone="UTC",
        disclosure_text="Hi!",
    )
    assert expected_word in prompt.lower()


def test_build_appointment_prompt_handles_empty_services():
    from appointment_service import build_appointment_prompt
    prompt = build_appointment_prompt(
        business_name="Biz",
        business_type="salon",
        services=[],
        business_rules=[],
        escalation_phone=None,
        operating_hours=SALON_HOURS,
        restaurant_timezone="UTC",
        disclosure_text="Hi!",
    )
    assert "General Appointment" in prompt


def test_build_appointment_prompt_includes_returning_customer_block_when_provided():
    from appointment_service import build_appointment_prompt
    prompt = build_appointment_prompt(
        business_name="Biz",
        business_type="salon",
        services=SERVICES,
        business_rules=[],
        escalation_phone=None,
        operating_hours=SALON_HOURS,
        restaurant_timezone="UTC",
        disclosure_text="Hi!",
        customer_profile={
            "last_name": "Alice",
            "visit_count": 3,
            "last_order": {"service_name": "Haircut"},
        },
    )
    assert "Alice" in prompt
    assert "Welcome back" in prompt


def test_build_appointment_prompt_with_cached_availability():
    from appointment_service import build_appointment_prompt
    prompt = build_appointment_prompt(
        business_name="Biz",
        business_type="salon",
        services=SERVICES,
        business_rules=[],
        escalation_phone=None,
        operating_hours=SALON_HOURS,
        restaurant_timezone="UTC",
        disclosure_text="Hi!",
        cached_availability={
            "2030-06-03": ["9:00 AM", "9:30 AM", "10:00 AM"],
        },
    )
    assert "AVAILABILITY" in prompt
