"""
Unit tests for backend/reservation_service.py — slot generation logic.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# DEFAULT_RESERVATION_SETTINGS / get_reservation_settings
# ---------------------------------------------------------------------------

def test_default_settings_present():
    from reservation_service import DEFAULT_RESERVATION_SETTINGS as defaults
    assert defaults["max_party_size"] >= 1
    assert defaults["min_party_size"] >= 1
    assert defaults["advance_booking_days"] >= 1
    assert "blackout_dates" in defaults


def test_get_reservation_settings_returns_defaults_with_no_overrides():
    from reservation_service import get_reservation_settings, DEFAULT_RESERVATION_SETTINGS
    settings = get_reservation_settings(config={})
    # Reservations are opt-in: with neither config nor restaurant setting it,
    # get_reservation_settings forces reservations_enabled OFF — even though the
    # constant still defaults it True (the constant is read verbatim elsewhere).
    assert settings["reservations_enabled"] is False
    for key, value in DEFAULT_RESERVATION_SETTINGS.items():
        if key == "reservations_enabled":
            continue
        assert settings[key] == value


def test_get_reservation_settings_applies_config_override():
    from reservation_service import get_reservation_settings
    settings = get_reservation_settings(config={"max_party_size": 12})
    assert settings["max_party_size"] == 12


def test_get_reservation_settings_restaurant_overrides_config():
    from reservation_service import get_reservation_settings
    settings = get_reservation_settings(
        config={"max_party_size": 8},
        restaurant={"reservation_party_limit": 20},
    )
    assert settings["max_party_size"] == 20


def test_get_reservation_settings_maps_restaurant_keys():
    from reservation_service import get_reservation_settings
    settings = get_reservation_settings(
        config={},
        restaurant={
            "reservation_slot_duration": 60,
            "reservation_max_per_slot": 5,
            "reservation_advance_booking_days": 7,
        },
    )
    assert settings["slot_interval_minutes"] == 60
    assert settings["capacity_per_slot"] == 5
    assert settings["advance_booking_days"] == 7


# ---------------------------------------------------------------------------
# get_reservation_slots — sandbox / scaffolding
# ---------------------------------------------------------------------------

OPERATING_HOURS_5_TO_10 = {
    "monday": {"open": "17:00", "close": "22:00"},
    "tuesday": {"open": "17:00", "close": "22:00"},
    "wednesday": {"open": "17:00", "close": "22:00"},
    "thursday": {"open": "17:00", "close": "22:00"},
    "friday": {"open": "17:00", "close": "22:00"},
    "saturday": {"open": "17:00", "close": "22:00"},
    "sunday": {"open": "17:00", "close": "22:00"},
}


async def test_returns_empty_when_reservations_disabled(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": False},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    assert slots == []


async def test_returns_empty_on_blackout_date(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True, "blackout_dates": ["2030-06-15"]},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    assert slots == []


async def test_returns_empty_when_day_closed(async_db):
    from reservation_service import get_reservation_slots
    hours = {"saturday": {"closed": True}}
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-01",  # Saturday
        config={"reservations_enabled": True},
        operating_hours=hours,
        db=async_db,
    )
    assert slots == []


async def test_returns_empty_on_invalid_date(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="not-a-date",
        config={"reservations_enabled": True},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    assert slots == []


async def test_generates_slots_at_default_interval(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",  # Saturday in far future
        config={"reservations_enabled": True},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    # default 30-minute interval, 17:00 to 21:00 (close - 1h buffer)
    # 17:00, 17:30, 18:00, ..., 21:00 = 9 slots
    assert len(slots) >= 8
    assert slots[0]["time"] == "17:00"
    assert slots[0]["available"] is True
    assert slots[0]["remaining_capacity"] == 10  # default capacity


async def test_uses_custom_slot_interval(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True, "slot_interval_minutes": 60},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    # 17:00 to 21:00 at 60-min interval = 5 slots
    assert len(slots) <= 6
    if len(slots) >= 2:
        # Verify hour-apart spacing
        h1 = int(slots[0]["time"].split(":")[0])
        h2 = int(slots[1]["time"].split(":")[0])
        assert h2 - h1 == 1


# ---------------------------------------------------------------------------
# Split hours (multiple service periods) — reservations use the POSTED close,
# NOT the kitchen last-call offset (a table booking is a dining-room concept).
# ---------------------------------------------------------------------------

SPLIT_HOURS_SATURDAY = {
    "saturday": {
        "closed": False,
        "last_call_offset_minutes": 30,  # order-taking only — must NOT affect slots
        "periods": [
            {"open": "10:00", "close": "15:00"},
            {"open": "18:00", "close": "22:00"},
        ],
    }
}


async def test_split_hours_generates_slots_for_both_periods(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",  # Saturday in far future (no past-slot filtering)
        config={"reservations_enabled": True},
        operating_hours=SPLIT_HOURS_SATURDAY,
        db=async_db,
    )
    times = {s["time"] for s in slots}
    # Lunch period (10:00 → 15:00, minus 1h buffer → last slot 14:00)
    assert "10:00" in times
    assert "14:00" in times
    # Dinner period (18:00 → 22:00, minus 1h buffer → last slot 21:00). This also
    # proves the 30-min last-call offset is NOT applied here — otherwise the last
    # dinner slot would stop earlier than 21:00.
    assert "18:00" in times
    assert "21:00" in times


async def test_split_hours_excludes_midday_gap(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",  # Saturday
        config={"reservations_enabled": True},
        operating_hours=SPLIT_HOURS_SATURDAY,
        db=async_db,
    )
    times = {s["time"] for s in slots}
    # The midday gap (15:00–18:00) must produce no slots.
    assert "16:00" not in times
    assert "17:00" not in times
    # Slots come back in chronological order across periods.
    ordered = [s["time"] for s in slots]
    assert ordered == sorted(ordered)


async def test_existing_reservations_reduce_capacity(async_db):
    from reservation_service import get_reservation_slots, ReservationStatus

    # Pre-seed two confirmed reservations at 18:00
    for i in range(2):
        await async_db.reservations.insert_one({
            "restaurant_id": "rest_a",
            "reservation_date": "2030-06-15",
            "reservation_time": "18:00",
            "status": ReservationStatus.CONFIRMED,
        })

    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True, "capacity_per_slot": 5},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )

    slot_18 = next(s for s in slots if s["time"] == "18:00")
    assert slot_18["remaining_capacity"] == 3


async def test_full_slot_is_unavailable(async_db):
    from reservation_service import get_reservation_slots, ReservationStatus

    # Pre-seed 10 reservations to fill the slot
    for _ in range(10):
        await async_db.reservations.insert_one({
            "restaurant_id": "rest_a",
            "reservation_date": "2030-06-15",
            "reservation_time": "18:00",
            "status": ReservationStatus.CONFIRMED,
        })

    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True, "capacity_per_slot": 10},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )

    slot_18 = next(s for s in slots if s["time"] == "18:00")
    assert slot_18["available"] is False
    assert slot_18["remaining_capacity"] == 0


async def test_cancelled_reservations_do_not_consume_capacity(async_db):
    from reservation_service import get_reservation_slots, ReservationStatus

    await async_db.reservations.insert_many([
        {"restaurant_id": "rest_a", "reservation_date": "2030-06-15", "reservation_time": "18:00",
         "status": ReservationStatus.CANCELLED},
        {"restaurant_id": "rest_a", "reservation_date": "2030-06-15", "reservation_time": "18:00",
         "status": ReservationStatus.CANCELLED},
    ])

    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True, "capacity_per_slot": 5},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    slot_18 = next(s for s in slots if s["time"] == "18:00")
    assert slot_18["remaining_capacity"] == 5


async def test_blocked_slots_are_marked_blocked(async_db):
    from reservation_service import get_reservation_slots

    await async_db.blocked_slots.insert_one({
        "restaurant_id": "rest_a",
        "date": "2030-06-15",
        "time": "18:00",
    })

    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    slot_18 = next(s for s in slots if s["time"] == "18:00")
    assert slot_18["blocked"] is True
    assert slot_18["available"] is False
    assert slot_18["remaining_capacity"] == 0


async def test_special_hours_override(async_db):
    from reservation_service import get_reservation_slots

    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True, "special_hours": {"2030-06-15": {"closed": True}}},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    assert slots == []


async def test_display_time_format(async_db):
    from reservation_service import get_reservation_slots
    slots = await get_reservation_slots(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        config={"reservations_enabled": True},
        operating_hours=OPERATING_HOURS_5_TO_10,
        db=async_db,
    )
    # 17:00 → "5:00 PM"
    assert slots[0]["display_time"].endswith("PM")
    assert ":" in slots[0]["display_time"]


# ---------------------------------------------------------------------------
# create_reservation_doc
# ---------------------------------------------------------------------------

def test_create_reservation_doc_includes_required_fields():
    from reservation_service import create_reservation_doc, ReservationStatus
    doc = create_reservation_doc(
        restaurant_id="rest_a",
        customer_name="Joe",
        customer_phone="+15551234567",
        party_size=4,
        reservation_date="2030-06-15",
        reservation_time="18:00",
    )
    assert doc["restaurant_id"] == "rest_a"
    assert doc["customer_name"] == "Joe"
    assert doc["party_size"] == 4
    assert doc["status"] == ReservationStatus.CONFIRMED
    assert "id" in doc
    assert doc["confirmation_sent"] is False
    assert doc["reminder_sent"] is False
