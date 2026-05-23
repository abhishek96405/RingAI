"""Tenant isolation for the ``integrations`` collection.

The ``integrations`` collection holds OAuth tokens (Square, Stripe Connect,
Google Calendar) and POS credentials (Clover, Toast). A cross-tenant read
here would expose encrypted-but-still-sensitive credentials.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


async def test_pos_credentials_cross_tenant_save_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    # Tenant B tries to save POS credentials TO tenant A's restaurant.
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        json={
            "provider": "clover",
            "credentials": {"merchant_id": "merch_evil", "api_token": "evil"},
        },
        headers={"Authorization": "Bearer tenant_b"},
    )
    # 4xx denial expected — exact code depends on validation order.
    assert r.status_code in (400, 403, 404, 422)
    # No integrations row was created under TENANT_A by tenant B.
    count = await patched_server_db.integrations.count_documents(
        {"restaurant_id": TENANT_A_ID, "credentials.merchant_id": "merch_evil"}
    )
    assert count == 0


async def test_pos_sync_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/sync",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


async def test_pos_test_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/test",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


async def test_calendar_status_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/status",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


async def test_calendar_disconnect_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    # Pretend tenant A has calendar connected
    await patched_server_db.integrations.insert_one(
        {
            "id": "integ_cal_a",
            "restaurant_id": TENANT_A_ID,
            "provider": "google_calendar",
            "connected": True,
        }
    )
    r = client.delete(
        f"/api/restaurants/{TENANT_A_ID}/calendar/disconnect",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    rec = await patched_server_db.integrations.find_one({"id": "integ_cal_a"})
    assert rec["connected"] is True


async def test_calendar_availability_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/availability"
        "?date=2026-06-01&service_duration_minutes=30",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Encrypted tokens never appear in response bodies, even when allowed.
# ---------------------------------------------------------------------------


async def test_encrypted_oauth_tokens_never_in_response_body(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.integrations.insert_one(
        {
            "id": "integ_b_square",
            "restaurant_id": TENANT_B_ID,
            "provider": "square",
            "connected": True,
            "access_token": "enc:DEFINITELY_ENCRYPTED_TOKEN_VALUE_XYZ",
            "refresh_token": "enc:REFRESH_SECRET_DO_NOT_LEAK",
        }
    )
    # Tenant B reads their OWN calendar status — token shouldn't surface
    # in the JSON response.
    r = client.get(
        f"/api/restaurants/{TENANT_B_ID}/calendar/status",
        headers={"Authorization": "Bearer tenant_b"},
    )
    if r.status_code == 200:
        assert "DEFINITELY_ENCRYPTED_TOKEN_VALUE_XYZ" not in r.text
        assert "REFRESH_SECRET_DO_NOT_LEAK" not in r.text
        assert "enc:" not in r.text


# ---------------------------------------------------------------------------
# Unauth on integrations routes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/restaurants/{rid}/pos/credentials"),
        ("POST", "/api/restaurants/{rid}/pos/sync"),
        ("POST", "/api/restaurants/{rid}/pos/test"),
        ("GET", "/api/restaurants/{rid}/calendar/status"),
        ("DELETE", "/api/restaurants/{rid}/calendar/disconnect"),
    ],
)
async def test_integration_routes_unauth_returns_401(
    client, two_tenant_with_memberships, method, path
):
    r = client.request(method, path.format(rid=TENANT_A_ID))
    assert r.status_code == 401
