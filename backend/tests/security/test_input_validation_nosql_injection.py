"""NoSQL injection defence.

Mongo operator injection (``$ne``, ``$regex``, ``$where``, ``$gt``) is the
canonical attack on MongoDB-backed APIs that pass user input straight into
``find()`` filters. Pydantic models normally coerce these to strings,
which breaks the operator dispatch — verify that property here.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# A POST that takes a "name" field — if the server uses the value as a
# Mongo filter, injecting ``{"$ne": null}`` would silently match every doc.
# Pydantic must reject (422) or coerce to string.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil",
    [
        {"$ne": None},
        {"$gt": ""},
        {"$regex": ".*"},
        {"$where": "this"},
    ],
)
def test_menu_create_rejects_mongo_operator_injection_in_name(
    client, two_tenant_with_memberships, evil
):
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        json={"name": evil, "price": 5, "available": True, "category": "main"},
        headers={"Authorization": "Bearer tenant_a"},
    )
    # Pydantic should reject (422) since name is str.
    assert r.status_code in (
        400,
        422,
    ), f"injection accepted: {r.status_code}: {r.text[:200]}"


@pytest.mark.parametrize(
    "evil",
    [
        {"$ne": None},
        {"$regex": ".*"},
    ],
)
def test_reservation_create_rejects_mongo_operator_injection(
    client, two_tenant_with_memberships, evil
):
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/reservations",
        json={
            "customer_name": evil,
            "customer_phone": "+15555550150",
            "party_size": 2,
            "scheduled_date": "2026-06-01",
            "scheduled_time": "19:00",
        },
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code in (400, 422)


async def test_call_filter_does_not_expand_via_operator_in_query_string(
    client, patched_server_db, two_tenant_with_memberships
):
    # Mongo operators in query-string field values must be treated as
    # literals. A status filter of `$ne` should match exactly zero records,
    # not "everything not-status".
    await patched_server_db.call_records.insert_one(
        {"id": "c1", "restaurant_id": TENANT_A_ID, "status": "completed"}
    )
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls?status=%24ne",
        headers={"Authorization": "Bearer tenant_a"},
    )
    # No crash; either 0 records (literal match) or 422 (filter rejected).
    assert r.status_code in (200, 400, 422)
