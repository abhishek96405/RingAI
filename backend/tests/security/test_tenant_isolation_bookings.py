"""Tenant isolation for booking collections.

Covers ``appointments``, ``blocked_slots``, ``reservations``. Each of these
has both a path-scoped list (``/api/restaurants/{rid}/<resource>``) and an
item-scoped route (``/api/<resource>/{id}``) that uses
``ensure_restaurant_access``.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Scenario 2 — list scoping per booking collection.
# ---------------------------------------------------------------------------


async def test_appointment_list_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.appointments.insert_many(
        [
            {
                "id": "appt_a_1",
                "restaurant_id": TENANT_A_ID,
                "customer_name": "Alice",
                "customer_phone": "+15555550111",
                "service_name": "Cut",
                "scheduled_date": "2026-06-01",
                "scheduled_time": "10:00",
                "status": "confirmed",
            },
            {
                "id": "appt_b_1",
                "restaurant_id": TENANT_B_ID,
                "customer_name": "Bob",
                "customer_phone": "+15555550112",
                "service_name": "Wash",
                "scheduled_date": "2026-06-01",
                "scheduled_time": "11:00",
                "status": "confirmed",
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/appointments",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    names = {a["customer_name"] for a in r_a.json()["appointments"]}
    assert "Alice" in names
    assert "Bob" not in names


async def test_blocked_slot_list_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.blocked_slots.insert_many(
        [
            {
                "id": "bs_a_1",
                "restaurant_id": TENANT_A_ID,
                "date": "2026-06-01",
                "start_time": "12:00",
                "end_time": "13:00",
                "reason": "lunch A",
            },
            {
                "id": "bs_b_1",
                "restaurant_id": TENANT_B_ID,
                "date": "2026-06-01",
                "start_time": "12:00",
                "end_time": "13:00",
                "reason": "lunch B",
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    reasons = {s["reason"] for s in r_a.json()["blocked_slots"]}
    assert "lunch A" in reasons
    assert "lunch B" not in reasons


async def test_reservation_list_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.reservations.insert_many(
        [
            {
                "id": "rv_a_1",
                "restaurant_id": TENANT_A_ID,
                "customer_name": "Alpha",
                "customer_phone": "+15555550150",
                "party_size": 2,
                "scheduled_date": "2026-06-01",
                "scheduled_time": "19:00",
                "status": "confirmed",
            },
            {
                "id": "rv_b_1",
                "restaurant_id": TENANT_B_ID,
                "customer_name": "Beta",
                "customer_phone": "+15555550160",
                "party_size": 4,
                "scheduled_date": "2026-06-01",
                "scheduled_time": "20:00",
                "status": "confirmed",
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/reservations",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    names = {x["customer_name"] for x in r_a.json()["reservations"]}
    assert "Alpha" in names
    assert "Beta" not in names


# ---------------------------------------------------------------------------
# Scenario 1 — cross-tenant GET of an item is denied.
# ---------------------------------------------------------------------------


async def test_get_appointment_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.appointments.insert_one(
        {
            "id": "appt_secret",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "VIP",
            "customer_phone": "+15555550111",
            "service_name": "Private",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "status": "confirmed",
        }
    )
    r = client.get(
        "/api/appointments/appt_secret",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert "VIP" not in r.text


async def test_get_reservation_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.reservations.insert_one(
        {
            "id": "rv_secret",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "PrivateVIP",
            "customer_phone": "+15555550111",
            "party_size": 2,
            "scheduled_date": "2026-06-01",
            "scheduled_time": "19:00",
            "status": "confirmed",
        }
    )
    r = client.get(
        "/api/reservations/rv_secret",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert "PrivateVIP" not in r.text


# ---------------------------------------------------------------------------
# Scenario 4 — UPDATE/DELETE cross-tenant is denied, record unchanged.
# ---------------------------------------------------------------------------


async def test_cancel_appointment_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.appointments.insert_one(
        {
            "id": "appt_lock",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "Locked",
            "customer_phone": "+15555550111",
            "service_name": "X",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "status": "confirmed",
        }
    )
    r = client.patch(
        "/api/appointments/appt_lock/cancel",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    rec = await patched_server_db.appointments.find_one({"id": "appt_lock"})
    assert rec["status"] == "confirmed"


async def test_cancel_reservation_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.reservations.insert_one(
        {
            "id": "rv_lock",
            "restaurant_id": TENANT_A_ID,
            "customer_name": "Locked",
            "customer_phone": "+15555550111",
            "party_size": 2,
            "scheduled_date": "2026-06-01",
            "scheduled_time": "19:00",
            "status": "confirmed",
        }
    )
    r = client.patch(
        "/api/reservations/rv_lock/cancel",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    rec = await patched_server_db.reservations.find_one({"id": "rv_lock"})
    assert rec["status"] == "confirmed"


async def test_delete_blocked_slot_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.blocked_slots.insert_one(
        {
            "id": "bs_lock",
            "restaurant_id": TENANT_A_ID,
            "scheduled_date": "2026-06-01",
            "start_time": "12:00",
            "end_time": "13:00",
            "reason": "stays",
        }
    )
    # Tenant B tries to delete from Tenant A's blocked slots collection.
    r = client.delete(
        f"/api/restaurants/{TENANT_A_ID}/blocked-slots/bs_lock",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert await patched_server_db.blocked_slots.count_documents({"id": "bs_lock"}) == 1


# ---------------------------------------------------------------------------
# Scenario 3 — unauthenticated requests return 401 across booking routes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/restaurants/{rid}/appointments",
        "/api/restaurants/{rid}/blocked-slots?date=2026-06-01",
        "/api/restaurants/{rid}/reservations",
        "/api/restaurants/{rid}/available-slots?date=2026-06-01&service_id=svc",
        "/api/restaurants/{rid}/reservation-slots?date=2026-06-01",
    ],
)
async def test_booking_list_routes_unauth_returns_401(
    client, two_tenant_with_memberships, path
):
    r = client.get(path.format(rid=TENANT_A_ID))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Scenario 5 — mass-assignment defence on reservation create.
# ---------------------------------------------------------------------------


async def test_create_reservation_body_restaurant_id_ignored_path_wins(
    client, patched_server_db, two_tenant_with_memberships
):
    payload = {
        "customer_name": "MassA",
        "customer_phone": "+15555550140",
        "party_size": 2,
        "scheduled_date": "2026-06-01",
        "scheduled_time": "20:00",
        "restaurant_id": TENANT_A_ID,
    }
    r = client.post(
        f"/api/restaurants/{TENANT_B_ID}/reservations",
        json=payload,
        headers={"Authorization": "Bearer tenant_b"},
    )
    # No reservation should appear under tenant A.
    a_count = await patched_server_db.reservations.count_documents(
        {"restaurant_id": TENANT_A_ID, "customer_name": "MassA"}
    )
    assert a_count == 0


# ---------------------------------------------------------------------------
# Cross-resource: a reservation may reference a customer profile from the
# same tenant. Make sure tenant B can't read tenant A's customer through
# tenant A's reservation id.
# ---------------------------------------------------------------------------


async def test_reservation_does_not_expose_other_tenants_customer_profile(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.customer_profiles.insert_one(
        {
            "id": "cust_a",
            "restaurant_id": TENANT_A_ID,
            "name": "PrivateCustomer",
            "phone": "+15555550199",
        }
    )
    await patched_server_db.reservations.insert_one(
        {
            "id": "rv_link",
            "restaurant_id": TENANT_A_ID,
            "customer_id": "cust_a",
            "customer_name": "PrivateCustomer",
            "customer_phone": "+15555550199",
            "party_size": 2,
            "scheduled_date": "2026-06-01",
            "scheduled_time": "20:00",
            "status": "confirmed",
        }
    )
    r = client.get(
        "/api/reservations/rv_link",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert "PrivateCustomer" not in r.text
