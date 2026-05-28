"""Integration tests — root, bootstrap, and session endpoints.

Covers:
  GET  /api/                          — service banner
  GET  /api/me/bootstrap               — user + memberships + restaurants
  POST /api/me/repair-membership       — owner-membership backfill
  GET  /api/status                     — service health rollup
  GET  /menu/{restaurant_id}           — public menu HTML (no auth)
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_A_USER_ID, TENANT_B_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# GET /api/  (root banner)
# ---------------------------------------------------------------------------


def test_root_returns_banner(client):
    response = client.get("/api/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "operational"
    assert "RingAI" in body["message"] or "Duuutah" in body["message"]


# ---------------------------------------------------------------------------
# GET /api/me/bootstrap
# ---------------------------------------------------------------------------


async def test_bootstrap_requires_auth(client):
    response = client.get("/api/me/bootstrap")
    assert response.status_code == 401


async def test_bootstrap_returns_empty_for_new_user(client, mock_clerk):
    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["memberships"] == []
    assert body["restaurants"] == []
    assert body["active_restaurant"] is None
    assert body["onboarding_complete"] is False
    assert body["user"]["id"] == TENANT_A_USER_ID


async def test_bootstrap_returns_tenant_a_restaurants_only(
    client, two_tenant_with_memberships
):
    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    rest_ids = [r["id"] for r in body["restaurants"]]
    assert TENANT_A_ID in rest_ids
    assert (
        TENANT_B_ID not in rest_ids
    ), "tenant_a's bootstrap leaked tenant_b's restaurant"
    assert body["active_restaurant"]["id"] == TENANT_A_ID


async def test_bootstrap_honours_restaurant_id_query(
    client, two_tenant_with_memberships
):
    """If user has memberships for multiple restaurants, ?restaurant_id= picks the active one.

    For tenant_a who only has 1 restaurant, the query is a no-op (still TENANT_A_ID).
    """
    response = client.get(
        f"/api/me/bootstrap?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_restaurant"]["id"] == TENANT_A_ID


# ---------------------------------------------------------------------------
# POST /api/me/repair-membership
# ---------------------------------------------------------------------------


async def test_repair_membership_requires_auth(client):
    response = client.post("/api/me/repair-membership")
    assert response.status_code == 401


async def test_repair_membership_returns_410_gone(client, two_tenant_setup):
    """The endpoint has been retired after the cross-tenant ownership grant
    bug. It must now return 410 Gone and refuse to grant any membership.

    See FINDINGS.md 2026-05-22 — /api/me/repair-membership granted any
    authenticated caller owner-membership on every restaurant in the DB.
    """
    response = client.post(
        "/api/me/repair-membership",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 410
    assert "repaired" not in response.json()


async def test_repair_membership_does_not_steal_other_tenants(
    client, two_tenant_with_memberships
):
    """After the retirement, tenant_a's call cannot touch tenant_b's restaurant —
    no membership rows are created at all because the route returns 410 before
    any database write.
    """
    import server

    before_b = await server.db.memberships.count_documents(
        {"user_id": TENANT_A_USER_ID, "restaurant_id": TENANT_B_ID}
    )
    response = client.post(
        "/api/me/repair-membership",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 410
    after_b = await server.db.memberships.count_documents(
        {"user_id": TENANT_A_USER_ID, "restaurant_id": TENANT_B_ID}
    )
    assert before_b == after_b == 0, "tenant_a gained a membership row on tenant_b"


async def test_repair_membership_does_not_mutate_existing_memberships(
    client, two_tenant_with_memberships
):
    """The 410 path must not insert, update, or delete any existing
    membership row. tenant_a's pre-existing TENANT_A_ID ownership is
    untouched.
    """
    import server

    before = await server.db.memberships.count_documents(
        {"user_id": TENANT_A_USER_ID, "restaurant_id": TENANT_A_ID}
    )
    client.post(
        "/api/me/repair-membership",
        headers={"Authorization": "Bearer tenant_a"},
    )
    after = await server.db.memberships.count_documents(
        {"user_id": TENANT_A_USER_ID, "restaurant_id": TENANT_A_ID}
    )
    assert (
        before == after == 1
    ), "existing membership row was mutated by a 410 response"


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------


def test_status_returns_service_health_rollup(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["api"] == "operational"
    assert "gemini" in body
    assert "telnyx" in body
    assert "stripe" in body
    assert "clerk" in body
    assert "pipecat_pipeline" in body
    assert body["database"]["available"] is True


def test_status_does_not_require_auth(client):
    """Status endpoint is unauthenticated by design — used by health checks."""
    response = client.get("/api/status")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /menu/{restaurant_id}  — public menu HTML page
# ---------------------------------------------------------------------------


async def test_public_menu_returns_html_when_restaurant_exists(
    client, two_tenant_setup
):
    response = client.get(f"/menu/{TENANT_A_ID}")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Tenant A Diner" in response.text


def test_public_menu_returns_404_for_unknown_restaurant_expected(client):
    """The not-found branch returns 404 with the 'Menu not found' HTML body.

    See FINDINGS (resolved): the redundant ``from fastapi.responses import HTMLResponse``
    inside the function shadowed the module-level import, raising UnboundLocalError
    on the not-found branch. The local import has been removed.
    """
    response = client.get("/menu/does-not-exist")
    assert response.status_code == 404
    assert "Menu not found" in response.text


async def test_public_menu_does_not_require_auth(client, two_tenant_setup):
    """No Authorization header — must still serve."""
    response = client.get(f"/menu/{TENANT_A_ID}")
    assert response.status_code == 200
