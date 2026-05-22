"""
Unit tests for backend/calendar_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone, timedelta

import httpx
import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# is_google_calendar_configured / get_google_auth_url
# ---------------------------------------------------------------------------

def test_is_google_calendar_configured_true_when_creds_set(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-1")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-1")
    import importlib, calendar_service
    importlib.reload(calendar_service)
    assert calendar_service.is_google_calendar_configured() is True


def test_is_google_calendar_configured_false_when_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "x")
    import importlib, calendar_service
    importlib.reload(calendar_service)
    assert calendar_service.is_google_calendar_configured() is False


def test_get_google_auth_url_constructs_expected_params(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-xyz")
    import importlib, calendar_service
    importlib.reload(calendar_service)

    url = calendar_service.get_google_auth_url(
        restaurant_id="rest_a",
        redirect_uri="https://app.test/callback",
    )

    parsed = urllib.parse.urlparse(url)
    assert parsed.netloc == "accounts.google.com"
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["client_id"] == ["client-abc"]
    assert qs["redirect_uri"] == ["https://app.test/callback"]
    assert qs["state"] == ["rest_a"]
    assert qs["scope"] == ["https://www.googleapis.com/auth/calendar"]
    assert qs["access_type"] == ["offline"]
    assert qs["prompt"] == ["consent"]


def test_get_google_auth_url_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    import importlib, calendar_service
    importlib.reload(calendar_service)
    with pytest.raises(ValueError, match="not configured"):
        calendar_service.get_google_auth_url("rest_a", "https://x")


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------

async def test_exchange_code_for_tokens_happy_path(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "c")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    import importlib, calendar_service
    importlib.reload(calendar_service)

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await calendar_service.exchange_code_for_tokens("the-code", "https://app.test/cb")
    assert out["access_token"] == "AT"
    assert out["refresh_token"] == "RT"


async def test_exchange_code_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "c")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    import importlib, calendar_service
    importlib.reload(calendar_service)

    async def fake_post(self, url, **kwargs):
        return httpx.Response(400, text="bad code")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(ValueError):
        await calendar_service.exchange_code_for_tokens("bad", "https://app.test/cb")


async def test_exchange_code_raises_when_not_configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    import importlib, calendar_service
    importlib.reload(calendar_service)
    with pytest.raises(ValueError):
        await calendar_service.exchange_code_for_tokens("c", "https://x")


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------

async def test_refresh_access_token_happy_path(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "c")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    import importlib, calendar_service
    importlib.reload(calendar_service)

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"access_token": "newAT", "expires_in": 3600})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await calendar_service.refresh_access_token("RT")
    assert out["access_token"] == "newAT"


async def test_refresh_access_token_raises_on_failure(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "c")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    import importlib, calendar_service
    importlib.reload(calendar_service)

    async def fake_post(self, url, **kwargs):
        return httpx.Response(401, text="expired")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(ValueError):
        await calendar_service.refresh_access_token("RT")


# ---------------------------------------------------------------------------
# get_valid_access_token
# ---------------------------------------------------------------------------

async def test_get_valid_access_token_returns_current_when_not_expired(async_db):
    from calendar_service import get_valid_access_token

    tokens = {
        "access_token": "AT",
        "refresh_token": "RT",
        "expires_at": datetime.now(timezone.utc).timestamp() + 7200,
    }
    assert await get_valid_access_token(tokens, async_db, "rest_a") == "AT"


async def test_get_valid_access_token_refreshes_when_expired(async_db, monkeypatch):
    from calendar_service import get_valid_access_token
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "c")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    import importlib, calendar_service
    importlib.reload(calendar_service)

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"access_token": "newAT", "expires_in": 3600})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await async_db.restaurant_configs.insert_one({"restaurant_id": "rest_a"})

    tokens = {
        "access_token": "stale",
        "refresh_token": "RT",
        "expires_at": datetime.now(timezone.utc).timestamp() - 60,  # already expired
    }
    token = await calendar_service.get_valid_access_token(tokens, async_db, "rest_a")
    assert token == "newAT"

    # And the new token is persisted in DB
    cfg = await async_db.restaurant_configs.find_one({"restaurant_id": "rest_a"})
    assert cfg["google_calendar_tokens"]["access_token"] == "newAT"


async def test_get_valid_access_token_raises_when_expired_without_refresh_token(async_db):
    from calendar_service import get_valid_access_token

    tokens = {
        "access_token": "stale",
        "refresh_token": None,
        "expires_at": datetime.now(timezone.utc).timestamp() - 100,
    }
    with pytest.raises(ValueError, match="no refresh"):
        await get_valid_access_token(tokens, async_db, "rest_a")


# ---------------------------------------------------------------------------
# get_calendar_list / get_free_busy / create / delete events
# ---------------------------------------------------------------------------

async def test_get_calendar_list_happy_path(monkeypatch):
    from calendar_service import get_calendar_list

    async def fake_get(self, url, **kwargs):
        return httpx.Response(200, json={"items": [{"id": "primary"}, {"id": "secondary"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    calendars = await get_calendar_list("AT")
    assert len(calendars) == 2
    assert calendars[0]["id"] == "primary"


async def test_get_calendar_list_raises_on_non_200(monkeypatch):
    from calendar_service import get_calendar_list

    async def fake_get(self, url, **kwargs):
        return httpx.Response(403, text="denied")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ValueError):
        await get_calendar_list("AT")


async def test_get_free_busy_returns_busy_intervals(monkeypatch):
    from calendar_service import get_free_busy

    busy_data = {"calendars": {"primary": {"busy": [{"start": "2026-05-22T14:00:00Z", "end": "2026-05-22T15:00:00Z"}]}}}

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json=busy_data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    busy = await get_free_busy(
        "AT", "primary",
        datetime(2026, 5, 22, tzinfo=timezone.utc),
        datetime(2026, 5, 23, tzinfo=timezone.utc),
    )
    assert len(busy) == 1


async def test_create_calendar_event_happy_path(monkeypatch):
    from calendar_service import create_calendar_event

    async def fake_post(self, url, **kwargs):
        # Verify the event body includes attendee when provided
        assert kwargs["json"]["attendees"] == [{"email": "x@y.com"}]
        return httpx.Response(201, json={"id": "event_123"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await create_calendar_event(
        access_token="AT",
        calendar_id="primary",
        summary="Test",
        description="desc",
        start_time=datetime(2026, 5, 22, 14, tzinfo=timezone.utc),
        end_time=datetime(2026, 5, 22, 15, tzinfo=timezone.utc),
        attendee_email="x@y.com",
    )
    assert out["id"] == "event_123"


async def test_create_calendar_event_omits_attendee_when_missing(monkeypatch):
    from calendar_service import create_calendar_event

    async def fake_post(self, url, **kwargs):
        assert "attendees" not in kwargs["json"]
        return httpx.Response(200, json={"id": "ev"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await create_calendar_event(
        access_token="AT", calendar_id="primary",
        summary="t", description="d",
        start_time=datetime(2026, 5, 22, tzinfo=timezone.utc),
        end_time=datetime(2026, 5, 22, 1, tzinfo=timezone.utc),
    )


async def test_create_calendar_event_raises_on_failure(monkeypatch):
    from calendar_service import create_calendar_event

    async def fake_post(self, url, **kwargs):
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    with pytest.raises(ValueError):
        await create_calendar_event(
            access_token="AT", calendar_id="primary",
            summary="t", description="d",
            start_time=datetime(2026, 5, 22, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 22, 1, tzinfo=timezone.utc),
        )


async def test_delete_calendar_event_success(monkeypatch):
    from calendar_service import delete_calendar_event

    async def fake_delete(self, url, **kwargs):
        return httpx.Response(204)

    monkeypatch.setattr(httpx.AsyncClient, "delete", fake_delete)

    assert await delete_calendar_event("AT", "primary", "ev_1") is True


async def test_delete_calendar_event_failure_returns_false(monkeypatch):
    from calendar_service import delete_calendar_event

    async def fake_delete(self, url, **kwargs):
        return httpx.Response(403, text="denied")

    monkeypatch.setattr(httpx.AsyncClient, "delete", fake_delete)

    assert await delete_calendar_event("AT", "primary", "ev_1") is False


# ---------------------------------------------------------------------------
# calculate_available_slots
# ---------------------------------------------------------------------------

def test_calculate_slots_returns_empty_when_day_closed():
    from calendar_service import calculate_available_slots
    # Pick a Monday
    monday = datetime(2026, 5, 25, tzinfo=timezone.utc)
    slots = calculate_available_slots(
        date=monday,
        operating_hours={"monday": {"closed": True}},
        service_duration_minutes=30,
        buffer_minutes=0,
        busy_periods=[],
    )
    assert slots == []


def test_calculate_slots_generates_grid_when_open():
    from calendar_service import calculate_available_slots
    # Far future to avoid lead-time clipping
    future = datetime(2030, 6, 1, tzinfo=timezone.utc)
    slots = calculate_available_slots(
        date=future,
        operating_hours={"saturday": {"open": "09:00", "close": "11:00"}},
        service_duration_minutes=30,
        buffer_minutes=0,
        busy_periods=[],
        lead_time_hours=0,
        slot_interval_minutes=30,
    )
    # 9:00, 9:30, 10:00, 10:30 (each 30 min, ends by 11:00)
    assert len(slots) == 4
    assert slots[0]["display_time"] == "09:00 AM"


def test_calculate_slots_excludes_conflicting_busy_periods():
    from calendar_service import calculate_available_slots
    future = datetime(2030, 6, 1, tzinfo=timezone.utc)

    slots_no_conflict = calculate_available_slots(
        date=future,
        operating_hours={"saturday": {"open": "09:00", "close": "12:00"}},
        service_duration_minutes=30,
        buffer_minutes=0,
        busy_periods=[],
        lead_time_hours=0,
    )

    busy_start = future.replace(hour=10, minute=0).isoformat()
    busy_end = future.replace(hour=11, minute=0).isoformat()
    slots_with_busy = calculate_available_slots(
        date=future,
        operating_hours={"saturday": {"open": "09:00", "close": "12:00"}},
        service_duration_minutes=30,
        buffer_minutes=0,
        busy_periods=[{"start": busy_start, "end": busy_end}],
        lead_time_hours=0,
    )
    assert len(slots_with_busy) < len(slots_no_conflict)


def test_calculate_slots_handles_invalid_hours_format():
    from calendar_service import calculate_available_slots
    future = datetime(2030, 6, 1, tzinfo=timezone.utc)
    slots = calculate_available_slots(
        date=future,
        operating_hours={"saturday": {"open": "bogus", "close": "17:00"}},
        service_duration_minutes=30,
        buffer_minutes=0,
        busy_periods=[],
    )
    assert slots == []
