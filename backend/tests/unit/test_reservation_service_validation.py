"""
Unit tests for backend/reservation_service.py — validation, availability checks, dispatch.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def _sms_success():
    return SimpleNamespace(success=True, message_id="m1")


def _sms_failure():
    return SimpleNamespace(success=False, message_id=None, error_code="X", error_message="boom")


OPERATING_HOURS = {
    "monday": {"open": "17:00", "close": "22:00"},
    "tuesday": {"open": "17:00", "close": "22:00"},
    "wednesday": {"open": "17:00", "close": "22:00"},
    "thursday": {"open": "17:00", "close": "22:00"},
    "friday": {"open": "17:00", "close": "22:00"},
    "saturday": {"open": "17:00", "close": "22:00"},
    "sunday": {"open": "17:00", "close": "22:00"},
}


# ---------------------------------------------------------------------------
# check_reservation_availability
# ---------------------------------------------------------------------------

async def test_party_size_too_large_rejected(async_db):
    from reservation_service import check_reservation_availability

    result = await check_reservation_availability(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        time_str="18:00",
        party_size=20,
        config={"max_party_size": 8},
        operating_hours=OPERATING_HOURS,
        db=async_db,
    )
    assert result["available"] is False
    assert result["max_party_size"] == 8


async def test_returns_unavailable_when_date_has_no_slots(async_db):
    from reservation_service import check_reservation_availability

    closed_hours = {"saturday": {"closed": True}}
    result = await check_reservation_availability(
        restaurant_id="rest_a",
        date_str="2030-06-15",  # Saturday
        time_str="18:00",
        party_size=2,
        config={},
        operating_hours=closed_hours,
        db=async_db,
    )
    assert result["available"] is False


async def test_returns_available_when_slot_free(async_db):
    from reservation_service import check_reservation_availability

    result = await check_reservation_availability(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        time_str="18:00",
        party_size=4,
        config={},
        operating_hours=OPERATING_HOURS,
        db=async_db,
    )
    assert result["available"] is True
    assert result["slot"]["time"] == "18:00"


async def test_suggests_alternatives_when_requested_time_not_found(async_db):
    from reservation_service import check_reservation_availability

    # Request a time outside the generated grid
    result = await check_reservation_availability(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        time_str="03:00",
        party_size=2,
        config={},
        operating_hours=OPERATING_HOURS,
        db=async_db,
    )
    assert result["available"] is False
    assert "suggested_times" in result


async def test_suggests_nearby_when_slot_full(async_db):
    from reservation_service import check_reservation_availability, ReservationStatus

    # Fill 18:00 to capacity (default 10)
    for _ in range(10):
        await async_db.reservations.insert_one({
            "restaurant_id": "rest_a",
            "reservation_date": "2030-06-15",
            "reservation_time": "18:00",
            "status": ReservationStatus.CONFIRMED,
        })

    result = await check_reservation_availability(
        restaurant_id="rest_a",
        date_str="2030-06-15",
        time_str="18:00",
        party_size=2,
        config={},
        operating_hours=OPERATING_HOURS,
        db=async_db,
    )
    assert result["available"] is False
    assert "suggested_times" in result
    assert len(result["suggested_times"]) >= 1


# ---------------------------------------------------------------------------
# dispatch_reservation
# ---------------------------------------------------------------------------

async def test_dispatch_reservation_creates_and_sends_sms(async_db, monkeypatch):
    from reservation_service import dispatch_reservation

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    result = await dispatch_reservation(
        reservation_data={
            "customer_name": "Joe",
            "customer_phone": "+15551234567",
            "party_size": 4,
            "reservation_date": "2030-06-15",
            "reservation_time": "18:00",
        },
        restaurant={"id": "rest_a", "name": "Tasty Bistro", "address": "123 Main"},
        config={"sms_enabled": True},
        db=async_db,
    )
    assert result["success"] is True
    assert result["reservation_id"]
    assert result["sms_sent"] is True

    # Verify persisted to DB and marked confirmed
    doc = await async_db.reservations.find_one({"id": result["reservation_id"]})
    assert doc["customer_name"] == "Joe"
    assert doc["confirmation_sent"] is True


async def test_dispatch_reservation_skips_sms_when_disabled(async_db, monkeypatch):
    from reservation_service import dispatch_reservation

    send_mock = AsyncMock(return_value=_sms_success())
    monkeypatch.setattr("telnyx_service.send_sms", send_mock)

    result = await dispatch_reservation(
        reservation_data={
            "customer_name": "Joe",
            "customer_phone": "+15551234567",
            "party_size": 2,
            "reservation_date": "2030-06-15",
            "reservation_time": "18:00",
        },
        restaurant={"id": "rest_a", "name": "Tasty"},
        config={"sms_enabled": False},
        db=async_db,
    )
    assert result["success"] is True
    assert result["sms_sent"] is False
    send_mock.assert_not_awaited()


async def test_dispatch_reservation_marks_failure_silently_when_sms_fails(async_db, monkeypatch):
    from reservation_service import dispatch_reservation

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_failure()))

    result = await dispatch_reservation(
        reservation_data={
            "customer_name": "Joe",
            "customer_phone": "+15551234567",
            "party_size": 2,
            "reservation_date": "2030-06-15",
            "reservation_time": "18:00",
        },
        restaurant={"id": "rest_a", "name": "Tasty"},
        config={"sms_enabled": True},
        db=async_db,
    )
    # Reservation is still saved, only sms_sent flag is false
    assert result["success"] is True
    assert result["sms_sent"] is False


# ---------------------------------------------------------------------------
# send_reservation_sms — message construction
# ---------------------------------------------------------------------------

async def test_send_reservation_sms_constructs_body(monkeypatch):
    from reservation_service import send_reservation_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        captured["idempotency_key"] = idempotency_key
        captured["metadata"] = metadata
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    ok = await send_reservation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        party_size=4,
        reservation_date="2030-06-15",
        reservation_time="18:00",
        restaurant_address="123 Main St",
    )
    assert ok is True
    assert "Hi Joe" in captured["body"]
    assert "Tasty" in captured["body"]
    assert "Party of 4" in captured["body"]
    assert "123 Main St" in captured["body"]
    assert "CANCEL" in captured["body"]
    assert captured["metadata"]["purpose"] == "reservation_confirmation"


async def test_send_reservation_sms_handles_unparseable_dates(monkeypatch):
    from reservation_service import send_reservation_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_reservation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        party_size=2,
        reservation_date="not-a-date",
        reservation_time="not-a-time",
    )
    # Should not crash; raw values are interpolated
    assert "not-a-date" in captured["body"]


# ---------------------------------------------------------------------------
# build_reservation_prompt_block
# ---------------------------------------------------------------------------

def test_prompt_block_returns_empty_when_disabled():
    from reservation_service import build_reservation_prompt_block
    out = build_reservation_prompt_block(
        settings={"reservations_enabled": False},
        available_slots=[],
    )
    assert out == ""


def test_prompt_block_includes_party_size_and_advance_window():
    from reservation_service import build_reservation_prompt_block
    out = build_reservation_prompt_block(
        settings={
            "reservations_enabled": True,
            "max_party_size": 8,
            "advance_booking_days": 30,
        },
        available_slots=[],
    )
    assert "8 guests" in out
    assert "30 days" in out


# ---------------------------------------------------------------------------
# extract_reservation_from_transcript
# ---------------------------------------------------------------------------

async def test_extract_reservation_returns_none_without_client(monkeypatch):
    from reservation_service import extract_reservation_from_transcript
    monkeypatch.setattr("gemini_service._get_client", lambda: None)

    result = await extract_reservation_from_transcript(
        transcript=[{"role": "customer", "text": "book a table for 4 please"}],
        menu_index=None,
    )
    assert result is None


async def test_extract_reservation_returns_none_without_reservation_signal(monkeypatch):
    from reservation_service import extract_reservation_from_transcript
    from types import SimpleNamespace

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise AssertionError("Should not be called without reservation signal")

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    result = await extract_reservation_from_transcript(
        transcript=[{"role": "customer", "text": "do you have spaghetti"}],
        menu_index=None,
    )
    assert result is None


async def test_extract_reservation_happy_path(monkeypatch):
    from reservation_service import extract_reservation_from_transcript
    from types import SimpleNamespace

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=
                            '{"reservation_confirmed": true, "customer_name": "Alice", '
                            '"party_size": 4, "date": "2030-06-15", "time": "7:00 PM", '
                            '"special_requests": "window seat"}'
                        ))],
                        usage=None,
                    )

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    result = await extract_reservation_from_transcript(
        transcript=[
            {"role": "customer", "text": "book a table for 4"},
            {"role": "ai", "text": "Your reservation is confirmed."},
        ],
        menu_index=None,
    )
    assert result is not None
    assert result["customer_name"] == "Alice"
    assert result["party_size"] == 4
    assert result["reservation_date"] == "2030-06-15"
    assert result["reservation_time"] == "7:00 PM"
    assert result["special_requests"] == "window seat"


async def test_extract_reservation_returns_none_when_not_confirmed(monkeypatch):
    from reservation_service import extract_reservation_from_transcript
    from types import SimpleNamespace

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(
                            content='{"reservation_confirmed": false}'
                        ))],
                        usage=None,
                    )

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    result = await extract_reservation_from_transcript(
        transcript=[{"role": "customer", "text": "book a table maybe later"}],
        menu_index=None,
    )
    assert result is None


async def test_extract_reservation_returns_none_on_malformed_json(monkeypatch):
    from reservation_service import extract_reservation_from_transcript

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    from types import SimpleNamespace as SN
                    return SN(
                        choices=[SN(message=SN(content="not json"))],
                        usage=None,
                    )

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    result = await extract_reservation_from_transcript(
        transcript=[{"role": "customer", "text": "book a table"}],
        menu_index=None,
    )
    assert result is None


def test_prompt_block_lists_available_slots():
    from reservation_service import build_reservation_prompt_block
    out = build_reservation_prompt_block(
        settings={"reservations_enabled": True},
        available_slots=[
            {"display_time": "6:00 PM", "available": True},
            {"display_time": "6:30 PM", "available": False},
            {"display_time": "7:00 PM", "available": True},
        ],
    )
    assert "6:00 PM" in out
    assert "7:00 PM" in out
