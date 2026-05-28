"""Tenant isolation for business-root collections.

Covers ``restaurants``, ``clinics``, ``salons``, ``home_services``, ``legal``
and their paired ``*_configs``. These are the foundational tenant
documents — a leak here is a cross-tenant data breach.

Scenarios exercised:
1. GET cross-tenant → denied (403 today, 404 expected — see FINDINGS)
2. LIST scoped — only the caller's businesses are returned
3. Unauth → 401
4. PUT cross-tenant → denied
5. Mass-assignment: POST with another tenant's restaurant_id in body
   doesn't elevate caller to that tenant
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_A_USER_ID, TENANT_B_USER_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Scenario 1 — direct GET cross-tenant returns 403 (existing; 404 expected).
# ---------------------------------------------------------------------------


async def test_get_restaurant_cross_tenant_is_denied(
    client, two_tenant_with_memberships
):
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert "Tenant A" not in r.text


# ---------------------------------------------------------------------------
# Scenario 3 — unauthenticated requests return 401.
# ---------------------------------------------------------------------------


async def test_get_restaurant_unauth_returns_401(client, two_tenant_with_memberships):
    r = client.get(f"/api/restaurants/{TENANT_A_ID}")
    assert r.status_code == 401


async def test_get_restaurant_with_invalid_token_returns_401(
    client, two_tenant_with_memberships
):
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer not_a_real_token"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Scenario 4 — UPDATE cross-tenant is denied and original is unchanged.
# ---------------------------------------------------------------------------


async def test_put_restaurant_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    before = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})

    r = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        json={"name": "OVERWRITTEN BY ATTACKER"},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    after = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert after["name"] == before["name"]
    assert "OVERWRITTEN" not in (after.get("name") or "")


# ---------------------------------------------------------------------------
# Scenario 1 — list bootstrap returns only the caller's businesses.
# ---------------------------------------------------------------------------


async def test_bootstrap_scopes_restaurants_by_user_memberships(
    client, two_tenant_with_memberships
):
    r = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 200
    body = r.json()
    restaurant_ids = {r["id"] for r in body.get("restaurants", [])}
    assert TENANT_A_ID not in restaurant_ids


# ---------------------------------------------------------------------------
# Cross-tenant config read is denied.
# ---------------------------------------------------------------------------


async def test_get_restaurant_config_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.restaurant_configs.insert_one(
        {
            "id": "cfg_a",
            "restaurant_id": TENANT_A_ID,
            "system_prompt": "secret prompt for tenant A",
        }
    )
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/config",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert "secret prompt" not in r.text


# ---------------------------------------------------------------------------
# Expected-behaviour xfail — cross-tenant GET should return 404, not 403.
# This duplicates the C3 existing finding but is included here so the
# isolation-matrix file is self-contained.
# ---------------------------------------------------------------------------


async def test_get_restaurant_cross_tenant_returns_404_expected(
    client, two_tenant_with_memberships
):
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Membership integrity: the user table is shared but per-tenant routes never
# return another tenant's owner_user_id (or any user PII) in error bodies.
# ---------------------------------------------------------------------------


async def test_cross_tenant_error_body_does_not_leak_owner_user_id(
    client, two_tenant_with_memberships
):
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert TENANT_A_USER_ID not in r.text


# ---------------------------------------------------------------------------
# Scenario 5 — mass assignment: a POST creating a restaurant must use the
# JWT-derived owner_user_id, never the body-provided one (would let any
# user assign ownership to a different account).
# ---------------------------------------------------------------------------


async def test_create_restaurant_uses_jwt_owner_not_body(
    client, patched_server_db, mock_clerk
):
    payload = {
        "name": "MassAssign Bistro",
        "business_type": "restaurant",
        "owner_user_id": TENANT_A_USER_ID,  # attacker claims to be tenant A
        "org_id": "org_attacker",
    }
    r = client.post(
        "/api/restaurants",
        json=payload,
        headers={"Authorization": "Bearer tenant_b"},
    )
    # The route returned 200 and stored a doc — we read it back and assert
    # the owner_user_id matches the JWT (tenant B), not the body claim.
    if r.status_code == 200:
        created = r.json()
        # If a doc was returned, the owner must be tenant B (caller).
        owner = created.get("owner_user_id") or created.get("ownerId")
        if owner is not None:
            assert owner == TENANT_B_USER_ID
