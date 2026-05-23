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


async def test_repair_membership_creates_missing_memberships(client, two_tenant_setup):
    """tenant_a calls repair → gets membership to EVERY unowned restaurant in DB.

    This captures current behavior: the endpoint iterates all business
    collections globally and grants the calling user ownership of any
    restaurant where they aren't yet a member. See FINDINGS — this is
    a cross-tenant exposure risk masquerading as a dev convenience.
    """
    response = client.post(
        "/api/me/repair-membership",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert TENANT_A_ID in body["repaired"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: /api/me/repair-membership currently grants the calling user ownership "
        "of EVERY unowned restaurant in the database, including those belonging to "
        "other tenants. Expected: only restore memberships the user previously had "
        "(via Clerk org membership lookup or similar)."
    ),
)
async def test_repair_membership_does_not_steal_other_tenants(
    client, two_tenant_with_memberships
):
    """Expected behavior: tenant_a's repair must NOT touch tenant_b's restaurant."""
    response = client.post(
        "/api/me/repair-membership",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert TENANT_B_ID not in body["repaired"]


async def test_repair_membership_is_idempotent_for_owned_restaurants(
    client, two_tenant_with_memberships
):
    """For restaurants the user already owns, repair is a no-op.

    Note: this doesn't say `repaired == []` because the buggy global behavior
    above still grants the calling user access to tenant_b's restaurant.
    What this test asserts is the narrower invariant: tenant_a's existing
    membership for TENANT_A_ID is not duplicated.
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
    ), "duplicate membership row created for already-owned restaurant"


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


def test_public_menu_unknown_restaurant_raises_unboundlocalerror(app):
    """Captures current (buggy) behavior. See FINDINGS:

    public_menu_page at server.py:1264 does `from fastapi.responses import HTMLResponse`
    at line 1359, AFTER it references HTMLResponse at line 1276. Python treats the
    name as a local because of the later `from ... import`, so the not-found branch
    raises UnboundLocalError instead of returning a 404 HTML page.

    With Starlette's default ``raise_server_exceptions=True``, the test client
    re-raises the exception; with ``raise_server_exceptions=False`` the client
    returns 500. We exercise the former here.
    """
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/menu/does-not-exist")
    assert response.status_code == 500


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: public_menu_page references HTMLResponse on the not-found branch "
        "before importing it again later in the function, raising UnboundLocalError. "
        "Expected: 404 with 'Menu not found' HTML body."
    ),
)
def test_public_menu_returns_404_for_unknown_restaurant_expected(client):
    response = client.get("/menu/does-not-exist")
    assert response.status_code == 404
    assert "Menu not found" in response.text


async def test_public_menu_does_not_require_auth(client, two_tenant_setup):
    """No Authorization header — must still serve."""
    response = client.get(f"/menu/{TENANT_A_ID}")
    assert response.status_code == 200
