"""
Unit tests for backend/appointment_service.py — validation, calendar integration, SMS.

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


SALON_HOURS = {d: {"open": "09:00", "close": "17:00"} for d in
               ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]}
SALON_HOURS["sunday"] = {"closed": True}

CONFIG = {
    "slot_interval_minutes": 30,
    "slot_capacity": 1,
    "operating_hours": SALON_HOURS,
    "timezone": "UTC",
    "sms_enabled": True,
}

SERVICES = [{"name": "Haircut", "duration_minutes": 30}]


# ---------------------------------------------------------------------------
# send_appointment_sms — message construction
# ---------------------------------------------------------------------------

async def test_send_appointment_sms_constructs_message(monkeypatch):
    from appointment_service import send_appointment_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["to"] = to
        captured["body"] = body
        captured["idempotency_key"] = idempotency_key
        captured["metadata"] = metadata
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    ok = await send_appointment_sms(
        caller_number="+15551234567",
        booking={
            "customer_name": "Joe",
            "service_name": "Haircut",
            "preferred_date": "2030-06-03",
            "preferred_time": "10:00 AM",
            "id": "appt_1",
            "restaurant_id": "rest_a",
        },
        business_name="Snip Salon",
        duration_minutes=30,
    )
    assert ok is True
    assert "Hi Joe" in captured["body"]
    assert "Snip Salon" in captured["body"]
    assert "Haircut" in captured["body"]
    assert "10:00 AM" in captured["body"]
    assert captured["metadata"]["purpose"] == "appointment_confirmation"


async def test_send_appointment_sms_omits_greeting_when_no_name(monkeypatch):
    from appointment_service import send_appointment_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_appointment_sms(
        caller_number="+15551234567",
        booking={"service_name": "Haircut", "preferred_date": "2030-06-03", "preferred_time": "10:00 AM"},
        business_name="Biz",
    )
    assert "Hi " not in captured["body"]


async def test_send_appointment_sms_appends_cancel_url(monkeypatch):
    from appointment_service import send_appointment_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_appointment_sms(
        caller_number="+15551234567",
        booking={"customer_name": "Joe", "service_name": "Haircut",
                 "preferred_date": "2030-06-03", "preferred_time": "10:00 AM"},
        business_name="Biz",
        cancel_url="https://app.test/cancel/123",
    )
    assert "https://app.test/cancel/123" in captured["body"]


async def test_send_appointment_sms_failure_returns_false(monkeypatch):
    from appointment_service import send_appointment_sms
    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_failure()))

    ok = await send_appointment_sms(
        caller_number="+15551234567",
        booking={"customer_name": "Joe", "service_name": "Haircut",
                 "preferred_date": "2030-06-03", "preferred_time": "10:00 AM"},
        business_name="Biz",
    )
    assert ok is False


# ---------------------------------------------------------------------------
# dispatch_appointment with calendar integration
# ---------------------------------------------------------------------------

async def test_dispatch_creates_calendar_event_when_calendar_connected(async_db, monkeypatch):
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))
    monkeypatch.setattr("calendar_service.get_valid_access_token", AsyncMock(return_value="AT"))
    create_event_mock = AsyncMock(return_value={"id": "cal_event_xyz"})
    monkeypatch.setattr("calendar_service.create_calendar_event", create_event_mock)

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
        "customer_email": "joe@x.com",
    }
    cfg = {**CONFIG, "google_calendar_tokens": {"access_token": "AT", "refresh_token": "RT"}}
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Salon", "timezone": "UTC"},
        config=cfg,
        services=SERVICES,
        db=async_db,
    )

    assert result["calendar_event_id"] == "cal_event_xyz"
    create_event_mock.assert_awaited_once()


async def test_dispatch_continues_when_calendar_fails(async_db, monkeypatch):
    """A calendar exception must not block appointment creation."""
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))
    monkeypatch.setattr("calendar_service.get_valid_access_token",
                        AsyncMock(side_effect=RuntimeError("token down")))

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    cfg = {**CONFIG, "google_calendar_tokens": {"access_token": "AT"}}
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Salon", "timezone": "UTC"},
        config=cfg,
        services=SERVICES,
        db=async_db,
    )
    assert result["success"] is True
    assert result["calendar_event_id"] is None


# ---------------------------------------------------------------------------
# Missing required fields don't crash dispatch
# ---------------------------------------------------------------------------

async def test_dispatch_with_missing_customer_phone_skips_sms(async_db, monkeypatch):
    from appointment_service import dispatch_appointment

    send_mock = AsyncMock(return_value=_sms_success())
    monkeypatch.setattr("telnyx_service.send_sms", send_mock)

    booking = {
        "service_name": "Haircut",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Salon", "timezone": "UTC"},
        config=CONFIG,
        services=SERVICES,
        db=async_db,
    )
    assert result["success"] is True
    send_mock.assert_not_awaited()


async def test_dispatch_resolves_service_duration_from_services(async_db, monkeypatch):
    """Saved appointment uses the duration from the matching service entry."""
    from appointment_service import dispatch_appointment

    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_success()))

    custom_services = [{"name": "Massage", "duration_minutes": 75}]

    booking = {
        "service_name": "Massage",
        "preferred_date": "2030-06-03",
        "preferred_time": "10:00 AM",
        "customer_name": "Joe",
        "customer_phone": "+15551234567",
    }
    result = await dispatch_appointment(
        booking=booking,
        restaurant={"id": "rest_a", "name": "Spa", "timezone": "UTC"},
        config=CONFIG,
        services=custom_services,
        db=async_db,
    )
    doc = await async_db.appointments.find_one({"id": result["appointment_id"]})
    assert doc["duration_minutes"] == 75


# ---------------------------------------------------------------------------
# extract_booking_from_transcript — happy and failure paths
# ---------------------------------------------------------------------------

async def test_extract_booking_returns_none_without_api_key(monkeypatch):
    from appointment_service import extract_booking_from_transcript

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)

    result = await extract_booking_from_transcript(
        transcript=[{"role": "customer", "text": "Book me for tomorrow"}],
        services=[{"name": "Haircut"}],
    )
    assert result is None


async def test_extract_booking_returns_data_on_success(monkeypatch):
    from appointment_service import extract_booking_from_transcript
    from types import SimpleNamespace
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    class _FakeChoices:
        def __init__(self, content):
            self.message = SimpleNamespace(content=content)

    class _FakeResp:
        def __init__(self, content):
            self.choices = [_FakeChoices(content)]
            self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    class _FakeCompletions:
        def __init__(self, content):
            self.content = content
        def create(self, **kwargs):
            return _FakeResp(self.content)

    class _FakeChat:
        def __init__(self, content):
            self.completions = _FakeCompletions(content)

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _FakeChat(
                '{"booking_confirmed": true, "service_name": "Haircut", "preferred_date": "2030-06-03",'
                ' "preferred_time": "10:00 AM", "customer_name": "Joe", "customer_phone": "", '
                '"customer_email": "", "special_instructions": ""}'
            )

    import openai
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    result = await extract_booking_from_transcript(
        transcript=[{"role": "ai", "text": "Your appointment is confirmed for 10:00 AM."}],
        services=[{"name": "Haircut"}],
    )
    assert result is not None
    assert result["booking_confirmed"] is True
    assert result["service_name"] == "Haircut"
    assert result["customer_name"] == "Joe"


async def test_extract_booking_returns_none_when_not_confirmed(monkeypatch):
    from appointment_service import extract_booking_from_transcript
    from types import SimpleNamespace
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            inner = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **k: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content='{"booking_confirmed": false}'))],
                        usage=None,
                    )
                )
            )
            self.chat = inner

    import openai
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    result = await extract_booking_from_transcript(
        transcript=[{"role": "customer", "text": "Maybe later"}],
        services=[{"name": "Haircut"}],
    )
    assert result is None


async def test_extract_booking_returns_none_on_malformed_json(monkeypatch):
    from appointment_service import extract_booking_from_transcript
    from types import SimpleNamespace
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            inner = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **k: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="not json at all"))],
                        usage=None,
                    )
                )
            )
            self.chat = inner

    import openai
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    result = await extract_booking_from_transcript(
        transcript=[{"role": "customer", "text": "Hi"}],
        services=[],
    )
    assert result is None
