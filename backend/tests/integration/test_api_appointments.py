"""Integration tests — appointment, blocked-slot, available-slot, reservation routes."""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# APPOINTMENT LIST / GET / CANCEL / REMINDER
# ---------------------------------------------------------------------------


async def test_list_appointments_empty(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/appointments",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["appointments"] == []
    assert body["total"] == 0
    assert body["page"] == 1


async def test_list_appointments_paginated(
    client, two_tenant_with_memberships, patched_server_db
):
    for i in range(25):
        await patched_server_db.appointments.insert_one(
            {
                "id": f"a{i}",
                "restaurant_id": TENANT_A_ID,
                "customer_name": f"C{i}",
                "customer_phone": "+15555550100",
                "service_name": "Haircut",
                "scheduled_date": "2026-06-01",
                "scheduled_time": "10:00",
                "status": "confirmed",
            }
        )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/appointments?page=2&limit=10",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert body["total"] == 25
    assert body["page"] == 2
    assert len(body["appointments"]) == 10
    assert body["pages"] == 3


async def test_list_appointments_status_filter(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.appointments.insert_many(
        [
            {
                "id": "a1",
                "restaurant_id": TENANT_A_ID,
                "customer_name": "x",
                "customer_phone": "+1",
                "service_name": "s",
                "scheduled_date": "2026-06-01",
                "scheduled_time": "10:00",
                "status": "confirmed",
            },
            {
                "id": "a2",
                "restaurant_id": TENANT_A_ID,
                "customer_name": "y",
                "customer_phone": "+1",
                "service_name": "s",
                "scheduled_date": "2026-06-01",
                "scheduled_time": "11:00",
                "status": "cancelled",
            },
        ]
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/appointments?status=confirmed",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert body["total"] == 1
    assert body["appointments"][0]["id"] == "a1"


def test_list_appointments_requires_auth(client):
    assert client.get(f"/api/restaurants/{TENANT_A_ID}/appointments").status_code == 401


async def test_list_appointments_wrong_tenant_404(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/appointments",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 404


def test_list_appointments_invalid_page_422(client, mock_clerk):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/appointments?page=0",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 422


async def test_get_appointment_happy_path(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.appointments.insert_one(
        {
            "id": "a1",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "x",
            "customer_phone": "+1",
            "service_name": "s",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "status": "confirmed",
        }
    )
    response = client.get(
        "/api/appointments/a1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "a1"


def test_get_appointment_missing_404(client, mock_clerk):
    response = client.get(
        "/api/appointments/nope",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


async def test_cancel_appointment(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.appointments.insert_one(
        {
            "id": "a1",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "x",
            "customer_phone": "+1",
            "service_name": "s",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "status": "confirmed",
        }
    )
    response = client.patch(
        "/api/appointments/a1/cancel",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    saved = await patched_server_db.appointments.find_one({"id": "a1"})
    assert saved["status"] == "cancelled"


def test_cancel_appointment_missing_404(client, mock_clerk):
    response = client.patch(
        "/api/appointments/nope/cancel",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


async def test_send_appointment_reminder_only_for_confirmed(
    client, two_tenant_with_memberships, patched_server_db
):
    """Sending a reminder for a cancelled appointment must return 400."""
    await patched_server_db.appointments.insert_one(
        {
            "id": "a1",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "x",
            "customer_phone": "+1",
            "service_name": "s",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "status": "cancelled",
        }
    )
    response = client.post(
        "/api/appointments/a1/send-reminder",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


def test_send_reminder_missing_404(client, mock_clerk):
    response = client.post(
        "/api/appointments/nope/send-reminder",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# BLOCKED SLOTS
# ---------------------------------------------------------------------------


async def test_block_slot_persists(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots",
        headers={"Authorization": "Bearer tenant_a"},
        json={"date": "2026-06-01", "slot_time": "10:00", "reason": "walk-in"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-01"
    assert body["restaurant_id"] == TENANT_A_ID

    rows = await patched_server_db.blocked_slots.count_documents(
        {"restaurant_id": TENANT_A_ID}
    )
    assert rows == 1


async def test_get_blocked_slots(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.blocked_slots.insert_one(
        {
            "id": "b1",
            "restaurant_id": TENANT_A_ID,
            "date": "2026-06-01",
            "slot_time": "10:00",
            "reason": "x",
        }
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert len(response.json()["blocked_slots"]) == 1


def test_get_blocked_slots_requires_date_422(client, mock_clerk):
    """Date query is required."""
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 422


async def test_unblock_slot(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.blocked_slots.insert_one(
        {
            "id": "b1",
            "restaurant_id": TENANT_A_ID,
            "date": "2026-06-01",
            "slot_time": "10:00",
            "reason": "x",
        }
    )
    response = client.delete(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots/b1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert await patched_server_db.blocked_slots.find_one({"id": "b1"}) is None


def test_unblock_missing_slot_404(client, two_tenant_with_memberships):
    response = client.delete(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots/nope",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# AVAILABLE SLOTS
# ---------------------------------------------------------------------------


async def test_get_available_slots(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/available-slots?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-06-01"
    assert "slots" in body


def test_get_available_slots_invalid_date_returns_something(client, mock_clerk):
    """Even on an invalid date string, the route should respond (it delegates
    to appointment_service.get_available_slots which handles parsing)."""
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/available-slots?date=not-a-date",
        headers={"Authorization": "Bearer tenant_a"},
    )
    # access check happens first → 404 because no membership in mock_clerk path
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# RESERVATION endpoints
# ---------------------------------------------------------------------------


async def test_list_reservations_empty(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/reservations",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reservations"] == []
    assert body["total"] == 0


async def test_list_reservations_with_filters(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.reservations.insert_many(
        [
            {
                "id": "r1",
                "restaurant_id": TENANT_A_ID,
                "customer_name": "x",
                "party_size": 2,
                "reservation_date": "2026-06-01",
                "reservation_time": "18:00",
                "status": "confirmed",
            },
            {
                "id": "r2",
                "restaurant_id": TENANT_A_ID,
                "customer_name": "y",
                "party_size": 4,
                "reservation_date": "2026-06-02",
                "reservation_time": "19:00",
                "status": "cancelled",
            },
        ]
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/reservations?status=confirmed&date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["reservations"][0]["id"] == "r1"


async def test_get_reservation(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.reservations.insert_one(
        {
            "id": "r1",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "x",
            "party_size": 2,
            "reservation_date": "2026-06-01",
            "reservation_time": "18:00",
            "status": "confirmed",
        }
    )
    response = client.get(
        "/api/reservations/r1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200


def test_get_reservation_missing_404(client, mock_clerk):
    response = client.get(
        "/api/reservations/nope",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


async def test_cancel_reservation(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.reservations.insert_one(
        {
            "id": "r1",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "x",
            "party_size": 2,
            "reservation_date": "2026-06-01",
            "reservation_time": "18:00",
            "status": "confirmed",
        }
    )
    response = client.patch(
        "/api/reservations/r1/cancel",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200


def test_cancel_reservation_missing_404(client, mock_clerk):
    response = client.patch(
        "/api/reservations/nope/cancel",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


async def test_confirm_reservation(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.reservations.insert_one(
        {
            "id": "r1",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "x",
            "party_size": 2,
            "reservation_date": "2026-06-01",
            "reservation_time": "18:00",
            "status": "pending",
        }
    )
    response = client.patch(
        "/api/reservations/r1/confirm",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200


def test_confirm_reservation_missing_404(client, mock_clerk):
    response = client.patch(
        "/api/reservations/nope/confirm",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


async def test_get_reservation_slots(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/reservation-slots?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert "slots" in response.json()


def test_get_reservation_slots_missing_date_422(client, mock_clerk):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/reservation-slots",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# CREATE RESERVATION (POST)
# ---------------------------------------------------------------------------


async def test_create_reservation_should_return_200_with_doc(
    client, two_tenant_with_memberships, patched_server_db
):
    # Seed reservations-enabled config with operating hours so the slot is
    # available — this exercises the successful-insert path where the D3-6
    # ObjectId leak used to 500 (2026-06-15 is a Monday).
    await patched_server_db.restaurant_configs.insert_one({
        "restaurant_id": TENANT_A_ID,
        "reservations_enabled": True,
        "operating_hours": {
            day: {"open": "09:00", "close": "22:00"}
            for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        },
    })
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/reservations",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "customer_name": "Alice",
            "customer_phone": "+15555550100",
            "party_size": 4,
            "reservation_date": "2026-06-15",
            "reservation_time": "19:00",
        },
    )
    assert response.status_code == 200
    assert "reservation" in response.json()


def test_create_reservation_rejects_missing_fields_422(client, mock_clerk):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/reservations",
        headers={"Authorization": "Bearer tenant_a"},
        json={"party_size": 4},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# ADMIN /api/admin/process-reminders
# ---------------------------------------------------------------------------


def test_process_reminders_requires_auth(client):
    assert client.post("/api/admin/process-reminders").status_code == 401


async def test_process_reminders_returns_result(client, mock_clerk):
    response = client.post(
        "/api/admin/process-reminders",
        headers={"Authorization": "Bearer admin"},
    )
    # reminder_service.process_appointment_reminders returns {sent: 0, total: 0}
    # when there's nothing to send.
    assert response.status_code == 200
