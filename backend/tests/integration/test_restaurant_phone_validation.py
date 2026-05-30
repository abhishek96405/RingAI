"""Integration tests — three-phone-number distinctness validation.

Covers:
  POST   /api/restaurants                  — rejects duplicate phone/business_phone
  PUT    /api/restaurants/{id}             — rejects new business_phone equal to
                                              existing phone_number (and normalizes
                                              input to E.164)
  PUT    /api/restaurants/{id}/config      — rejects escalation_phone_number equal
                                              to either restaurant phone, and
                                              normalizes input to E.164

Also asserts that a partial update of an unrelated field on a (legacy)
restaurant that already has duplicate phones still succeeds — the
validation hook only fires when phone fields are part of the change set.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# POST /api/restaurants
# ---------------------------------------------------------------------------


async def test_create_restaurant_rejects_duplicate_phones(client, mock_clerk, patched_server_db):
    response = client.post(
        "/api/restaurants",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "name": "Bad Phones",
            "phone_number": "+15551112222",
            "business_phone": "+15551112222",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "phone_number" in detail and "business_phone" in detail


# ---------------------------------------------------------------------------
# PUT /api/restaurants/{id}
# ---------------------------------------------------------------------------


async def test_update_restaurant_rejects_new_business_equals_existing_phone(
    client, two_tenant_with_memberships, patched_server_db
):
    # Seed existing phone_number on the tenant_a restaurant.
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"phone_number": "+15551112222"}},
    )
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"business_phone": "+15551112222"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "phone_number" in detail
    assert "business_phone" in detail


async def test_update_restaurant_normalizes_input_to_e164(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"phone_number": "(815) 693-2226"},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["phone_number"] == "+18156932226"


async def test_update_restaurant_partial_update_does_not_validate_phones(
    client, two_tenant_with_memberships, patched_server_db
):
    """Legacy restaurants with duplicate phones must still accept unrelated updates."""
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {
            "phone_number": "+15551112222",
            "business_phone": "+15551112222",
        }},
    )
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Just Rename Me"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# PUT /api/restaurants/{id}/config
# ---------------------------------------------------------------------------


async def test_update_restaurant_config_rejects_escalation_equals_restaurant_phone(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"phone_number": "+15551112222"}},
    )
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
        json={"escalation_phone_number": "+15551112222"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "phone_number" in detail
    assert "escalation_phone_number" in detail


async def test_update_restaurant_config_rejects_escalation_equals_business_phone(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"business_phone": "+15553334444"}},
    )
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
        json={"escalation_phone_number": "+15553334444"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "business_phone" in detail
    assert "escalation_phone_number" in detail


async def test_update_restaurant_config_normalizes_input(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
        json={"escalation_phone_number": "(815) 693-2226"},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurant_configs.find_one(
        {"restaurant_id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["escalation_phone_number"] == "+18156932226"
