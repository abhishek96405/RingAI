"""Tenant isolation for telephony collections.

Covers ``phone_number_orders`` and ``sms_messages``. Telephony provisioning
spends money — a cross-tenant write here could let one tenant order Telnyx
numbers on another tenant's account.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# phone_number_orders — provisioning is gated on restaurant_id ownership.
# ---------------------------------------------------------------------------


async def test_provision_number_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships, telnyx_sdk_mock
):
    r = client.post(
        "/api/telnyx/numbers/provision",
        json={
            "restaurant_id": TENANT_A_ID,
            "phone_numbers": ["+15555550199"],
            "country_code": "US",
        },
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


async def test_assign_existing_number_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships, telnyx_sdk_mock
):
    r = client.post(
        "/api/telnyx/numbers/assign-existing",
        json={"restaurant_id": TENANT_A_ID, "phone_number": "+15555550199"},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


async def test_release_number_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships, telnyx_sdk_mock
):
    r = client.post(
        "/api/telnyx/numbers/release",
        json={"restaurant_id": TENANT_A_ID, "phone_number_id": "pn_a_1"},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


async def test_send_menu_sms_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships, telnyx_sdk_mock
):
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/send-menu-sms",
        json={"to_number": "+15555550120"},
        headers={"Authorization": "Bearer tenant_b"},
    )
    # Some routes validate payload before access (400/422), some after (403/404).
    # Either is a denial — what matters is no SMS was sent.
    assert r.status_code in (400, 403, 404, 422)
    assert telnyx_sdk_mock["send_sms"] == []


# ---------------------------------------------------------------------------
# Unauth on telephony routes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/telnyx/numbers/status?phone_number=%2B15555550100", None),
        (
            "POST",
            "/api/telnyx/numbers/provision",
            {"restaurant_id": TENANT_A_ID, "phone_numbers": ["+15555550100"]},
        ),
        (
            "POST",
            "/api/telnyx/numbers/release",
            {"restaurant_id": TENANT_A_ID, "phone_number_id": "pn"},
        ),
        (
            "POST",
            "/api/restaurants/" + TENANT_A_ID + "/send-menu-sms",
            {"to_number": "+15555550100"},
        ),
    ],
)
def test_telephony_routes_unauth_returns_401(client, method, path, body):
    if body is None:
        r = client.request(method, path)
    else:
        r = client.request(method, path, json=body)
    assert r.status_code == 401
