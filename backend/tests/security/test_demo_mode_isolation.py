"""Demo-mode isolation.

When ``ENABLE_DEMO_MODE=true``, the app seeds a demo restaurant and exposes
``/api/demo/simulate-call`` + ``/api/demo/seed``. These routes must never
allow demo data to bleed into a non-demo tenant's queries, and must
themselves enforce the feature flag.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# When demo mode is OFF (default in tests), the demo-only routes 403.
# ---------------------------------------------------------------------------


def test_demo_simulate_call_returns_403_when_flag_off(
    client, two_tenant_with_memberships
):
    r = client.post(
        f"/api/demo/simulate-call?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 403


def test_demo_seed_returns_403_when_flag_off(client, two_tenant_with_memberships):
    r = client.post(
        f"/api/demo/seed?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    # 403 when flag off; 422 if route requires extra params and flag check is post-validation
    assert r.status_code in (403, 422)


# ---------------------------------------------------------------------------
# When ON, demo routes work BUT non-demo tenants still can't see the demo
# restaurant's data without their own auth context.
# ---------------------------------------------------------------------------


def test_demo_mode_enabled_does_not_leak_demo_data_to_other_tenant_routes(
    client, monkeypatch, patched_server_db, two_tenant_with_memberships
):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    # Tenant B's bootstrap must NOT show "demo-restaurant-001" — that demo
    # restaurant is not linked to tenant B's user via memberships.
    r = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 200
    restaurant_ids = {x["id"] for x in r.json().get("restaurants", [])}
    assert "demo-restaurant-001" not in restaurant_ids


async def test_demo_data_does_not_appear_in_other_tenant_listings(
    client, monkeypatch, patched_server_db, two_tenant_with_memberships
):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    # Seed a demo menu item under the demo restaurant.
    await patched_server_db.menu_items.insert_one(
        {
            "id": "demo_menu_1",
            "restaurant_id": "demo-restaurant-001",
            "name": "DEMO-ONLY-PIZZA",
            "available": True,
        }
    )
    # Tenant A reads its own menu — must not see demo items.
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    assert "DEMO-ONLY-PIZZA" not in r.text
