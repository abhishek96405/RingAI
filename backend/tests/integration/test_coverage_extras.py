"""Additional coverage tests targeting specific uncovered branches in server.py.

These tests are pure coverage padding for branches that don't fit cleanly into
the per-resource integration files: the business migration startup helper,
the calendar/book Google integration branch, Stripe billing-portal/refund SMS
non-paths, etc.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# migrate_businesses_to_typed_collections — startup hook, body only runs
# when there are pre-existing typed-business docs in db.restaurants.
# ---------------------------------------------------------------------------


async def test_business_migration_moves_clinic_docs_to_clinics_collection(
    client, patched_server_db
):
    """Seed a clinic document into db.restaurants (where the old code wrote it)
    and assert the migration relocates it to db.clinics."""
    await patched_server_db.restaurants.insert_one(
        {
            "id": "clinic_test_001",
            "name": "Test Clinic",
            "business_type": "clinic",
        }
    )

    import server

    await server.migrate_businesses_to_typed_collections()

    # Should now be in clinics, removed from restaurants.
    moved = await patched_server_db.clinics.find_one(
        {"id": "clinic_test_001"}, {"_id": 0}
    )
    assert moved is not None
    leftover = await patched_server_db.restaurants.find_one({"id": "clinic_test_001"})
    assert leftover is None


async def test_business_migration_handles_pre_existing_target_doc(
    client, patched_server_db
):
    """If the typed-collection already has the doc, the migration only deletes
    the duplicate from db.restaurants."""
    await patched_server_db.restaurants.insert_one(
        {
            "id": "salon_test_001",
            "name": "Salon",
            "business_type": "salon",
        }
    )
    await patched_server_db.salons.insert_one(
        {
            "id": "salon_test_001",
            "name": "Salon",
            "business_type": "salon",
        }
    )

    import server

    await server.migrate_businesses_to_typed_collections()

    leftover = await patched_server_db.restaurants.find_one({"id": "salon_test_001"})
    assert leftover is None


# ---------------------------------------------------------------------------
# Calendar /book route — Google Calendar integration branch
# ---------------------------------------------------------------------------


async def test_book_appointment_with_google_calendar_attempts_event(
    client, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """Seed restaurant_config with google_calendar_tokens, mock the calendar
    service helpers, and verify the route reaches the create_calendar_event
    path (covers server.py:2389-2431)."""
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "operating_hours": {},
            "google_calendar_tokens": {
                "access_token": "at_test",
                "refresh_token": "rt_test",
            },
            "google_calendar_id": "primary",
        }
    )
    await patched_server_db.services.insert_one(
        {
            "id": "svc1",
            "restaurant_id": TENANT_A_ID,
            "name": "Haircut",
            "duration_minutes": 30,
            "buffer_minutes": 5,
        }
    )

    import calendar_service

    async def _fake_token(tokens, db, rid):
        return "valid_access_token"

    async def _fake_event(**kw):
        return {"id": "google_event_123", "htmlLink": "https://cal.test/e/123"}

    monkeypatch.setattr(
        calendar_service, "get_valid_access_token", _fake_token, raising=False
    )
    monkeypatch.setattr(
        calendar_service, "create_calendar_event", _fake_event, raising=False
    )

    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/calendar/book",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "service_name": "Haircut",
            "service_id": "svc1",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00 AM",
            "customer_name": "Alice",
            "customer_phone": "+15555550100",
            "customer_email": "alice@example.com",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["calendar_event_id"] == "google_event_123"


async def test_book_appointment_with_24hr_time_format(
    client, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """24-hour time format must also pass the route's time parsing."""
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "operating_hours": {},
            "google_calendar_tokens": {"access_token": "x"},
        }
    )

    import calendar_service

    monkeypatch.setattr(
        calendar_service,
        "get_valid_access_token",
        AsyncMock(return_value="x"),
        raising=False,
    )
    monkeypatch.setattr(
        calendar_service,
        "create_calendar_event",
        AsyncMock(return_value={"id": "ev_x"}),
        raising=False,
    )

    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/calendar/book",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "service_name": "Haircut",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "14:30",
            "customer_name": "Bob",
            "customer_phone": "+15555550200",
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Calendar /availability with google_calendar_tokens — exercises the
# Google free/busy branch (lines around 2275-2291).
# ---------------------------------------------------------------------------


async def test_calendar_availability_with_google_tokens(
    client, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "operating_hours": {
                "monday": {"closed": False, "open": "09:00", "close": "17:00"},
            },
            "google_calendar_tokens": {"access_token": "at_test"},
            "google_calendar_id": "primary",
        }
    )

    import calendar_service

    async def _fake_token(tokens, db, rid):
        return "at_test"

    async def _fake_freebusy(token, cal, start, end):
        return [{"start": "2026-06-01T10:00:00Z", "end": "2026-06-01T11:00:00Z"}]

    monkeypatch.setattr(
        calendar_service, "get_valid_access_token", _fake_token, raising=False
    )
    monkeypatch.setattr(
        calendar_service, "get_free_busy", _fake_freebusy, raising=False
    )

    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/availability?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# auto_detect_timezone — exercised when creating a restaurant with an
# address and the default timezone.
# ---------------------------------------------------------------------------


async def test_create_restaurant_auto_detects_timezone(client, mock_clerk, monkeypatch):
    """The create-restaurant route calls auto_detect_timezone for any restaurant
    with an address and the default America/Chicago timezone. Stub the helper
    to return a different zone and verify it's persisted."""
    import server

    async def _fake_detect(address):
        return "Europe/Berlin"

    monkeypatch.setattr(server, "auto_detect_timezone", _fake_detect)

    response = client.post(
        "/api/restaurants",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "name": "Berlin Diner",
            "address": "Unter den Linden 1, Berlin",
        },
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Berlin"


# ---------------------------------------------------------------------------
# Update restaurant — address change triggers timezone auto-detect (line 1177)
# ---------------------------------------------------------------------------


async def test_update_restaurant_address_change_redetects_timezone(
    client, two_tenant_with_memberships, monkeypatch
):
    import server

    monkeypatch.setattr(
        server,
        "auto_detect_timezone",
        AsyncMock(return_value="Asia/Tokyo"),
    )

    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"address": "1 Chuo, Tokyo"},
    )
    assert response.status_code == 200
    assert response.json().get("timezone") == "Asia/Tokyo"
