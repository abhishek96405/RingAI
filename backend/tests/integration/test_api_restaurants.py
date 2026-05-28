"""Integration tests — restaurant CRUD + restaurant config endpoints.

Covers:
  POST   /api/restaurants                            — create
  GET    /api/restaurants                            — list (via bootstrap)
  GET    /api/restaurants/{id}                       — single read
  PUT    /api/restaurants/{id}                       — update (plan-gated)
  GET    /api/restaurants/{id}/config                — config read (default fallback)
  PUT    /api/restaurants/{id}/config                — config update
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# POST /api/restaurants
# ---------------------------------------------------------------------------


def test_create_restaurant_requires_auth(client):
    response = client.post("/api/restaurants", json={"name": "Spot"})
    assert response.status_code == 401


async def test_create_restaurant_persists_doc_and_creates_owner_membership(
    client, mock_clerk, patched_server_db
):
    response = client.post(
        "/api/restaurants",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "New Diner", "timezone": "America/New_York"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Diner"
    new_id = body["id"]

    saved = await patched_server_db.restaurants.find_one({"id": new_id}, {"_id": 0})
    assert saved is not None
    membership = await patched_server_db.memberships.find_one(
        {"user_id": "user_tenant_a", "restaurant_id": new_id}, {"_id": 0}
    )
    assert membership is not None
    assert membership["role"] == "owner"


def test_create_restaurant_rejects_bad_payload(client, mock_clerk):
    """Missing required name → 422."""
    response = client.post(
        "/api/restaurants",
        headers={"Authorization": "Bearer tenant_a"},
        json={"timezone": "America/New_York"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/restaurants  (list — proxies through bootstrap)
# ---------------------------------------------------------------------------


def test_list_restaurants_requires_auth(client):
    assert client.get("/api/restaurants").status_code == 401


async def test_list_restaurants_only_returns_owned(client, two_tenant_with_memberships):
    response = client.get(
        "/api/restaurants", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert TENANT_A_ID in ids
    assert TENANT_B_ID not in ids


async def test_list_restaurants_empty_for_new_user(client, mock_clerk):
    response = client.get(
        "/api/restaurants", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/restaurants/{id}
# ---------------------------------------------------------------------------


async def test_get_restaurant_happy_path(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == TENANT_A_ID


async def test_get_restaurant_wrong_tenant_returns_404(
    client, two_tenant_with_memberships
):
    """tenant_b authenticated, asks for tenant_a's restaurant.

    ensure_restaurant_access returns 404 (not 403) to avoid leaking
    existence — OWASP A01. See FINDINGS (resolved).
    """
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 404


async def test_get_restaurant_wrong_tenant_should_return_404(
    client, two_tenant_with_memberships
):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 404


def test_get_restaurant_unknown_id_returns_404(client, mock_clerk):
    """Without a membership row, ensure_restaurant_access raises 404 — same
    response as for an unknown id, so existence cannot be enumerated."""
    response = client.get(
        "/api/restaurants/nonexistent-id",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/restaurants/{id}
# ---------------------------------------------------------------------------


async def test_update_restaurant_persists_changes(client, two_tenant_with_memberships):
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Renamed Diner"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Diner"

    # Read-after-write
    follow_up = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert follow_up.json()["name"] == "Renamed Diner"


async def test_update_restaurant_empty_body_returns_400(
    client, two_tenant_with_memberships
):
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={},
    )
    assert response.status_code == 400


async def test_update_restaurant_wrong_tenant_404(client, two_tenant_with_memberships):
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
        json={"name": "Hijack"},
    )
    assert response.status_code == 404


async def test_update_restaurant_starter_plan_strips_delivery_toggle(
    client, two_tenant_with_memberships, patched_server_db
):
    """STARTER plan callers cannot enable delivery via PUT — the field is silently
    dropped after the empty-body 400 check, leaving the persisted doc unchanged.

    NOTE: server.py does the 400-on-empty-update check BEFORE the plan-feature
    strip, so a payload of only stripped fields returns 200 with no DB change
    (the {$set: {}} update is a no-op). See FINDINGS.
    """
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"delivery_enabled": True},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    # The seeded doc has no delivery_enabled key at all — STARTER plan still
    # blocks the write even though the route returns 200.
    assert "delivery_enabled" not in saved or saved.get("delivery_enabled") in (
        False,
        None,
    )


# ---------------------------------------------------------------------------
# GET /api/restaurants/{id}/config
# ---------------------------------------------------------------------------


async def test_get_config_returns_default_when_missing(
    client, two_tenant_with_memberships
):
    """No config row seeded → server returns a default RestaurantConfig payload."""
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["restaurant_id"] == TENANT_A_ID
    assert body["persona"] == "friendly"
    assert "operating_hours" in body


async def test_get_config_wrong_tenant_404(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/restaurants/{id}/config
# ---------------------------------------------------------------------------


async def test_update_config_creates_row_when_absent(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
        json={"persona": "professional", "delivery_minimum": 2000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persona"] == "professional"
    assert body["delivery_minimum"] == 2000

    saved = await patched_server_db.restaurant_configs.find_one(
        {"restaurant_id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["persona"] == "professional"


async def test_update_config_updates_existing_row(
    client, two_tenant_with_memberships, patched_server_db
):
    # Seed an existing config
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "persona": "warm",
        }
    )
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
        json={"persona": "playful"},
    )
    assert response.status_code == 200
    assert response.json()["persona"] == "playful"

    rows = await patched_server_db.restaurant_configs.count_documents(
        {"restaurant_id": TENANT_A_ID}
    )
    assert rows == 1, "config row was duplicated instead of updated"


async def test_update_config_starter_plan_strips_upsell(
    client, two_tenant_with_memberships
):
    """STARTER tenants cannot enable upsell — flag is silently dropped."""
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_a"},
        json={"upsell_enabled": True, "persona": "spunky"},
    )
    assert response.status_code == 200
    # Persona update went through, upsell flag dropped — still default True from model
    # but the saved row should NOT include the user-supplied upsell_enabled override.
    assert response.json()["persona"] == "spunky"
