"""Tenant isolation for menu catalog collections.

Covers ``menu_items``, ``modifier_groups``, ``services``, and the
``menu_aliases`` learning collection. The LIST routes (under
``/api/restaurants/{rid}/menu`` etc.) are tenant-scoped via the path; the
item-level routes (under ``/api/menu/{item_id}`` etc.) discover the tenant
from the document and then call ``ensure_restaurant_access``.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Scenario 2 — LIST is tenant-scoped. Tenant A's items never appear in
# Tenant B's listing.
# ---------------------------------------------------------------------------


async def test_list_menu_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_many(
        [
            {
                "id": "menu_a_1",
                "restaurant_id": TENANT_A_ID,
                "name": "A-Burger",
                "price": 12.0,
                "available": True,
            },
            {
                "id": "menu_b_1",
                "restaurant_id": TENANT_B_ID,
                "name": "B-Salad",
                "price": 8.0,
                "available": True,
            },
        ]
    )

    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
    )
    r_b = client.get(
        f"/api/restaurants/{TENANT_B_ID}/menu",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    a_names = {item["name"] for item in r_a.json()}
    b_names = {item["name"] for item in r_b.json()}
    assert "A-Burger" in a_names and "B-Salad" not in a_names
    assert "B-Salad" in b_names and "A-Burger" not in b_names


async def test_list_modifier_groups_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.modifier_groups.insert_many(
        [
            {
                "id": "mg_a_1",
                "restaurant_id": TENANT_A_ID,
                "name": "Toppings (A)",
                "min_select": 0,
                "max_select": 3,
                "modifiers": [],
            },
            {
                "id": "mg_b_1",
                "restaurant_id": TENANT_B_ID,
                "name": "Spice Level (B)",
                "min_select": 0,
                "max_select": 1,
                "modifiers": [],
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/modifier-groups",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    a_names = {m["name"] for m in r_a.json()}
    assert "Toppings (A)" in a_names
    assert "Spice Level (B)" not in a_names


async def test_list_services_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.services.insert_many(
        [
            {
                "id": "svc_a_1",
                "restaurant_id": TENANT_A_ID,
                "name": "Haircut (A)",
                "duration_minutes": 30,
                "price": 25.0,
            },
            {
                "id": "svc_b_1",
                "restaurant_id": TENANT_B_ID,
                "name": "Massage (B)",
                "duration_minutes": 60,
                "price": 90.0,
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/services",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    a_names = {s["name"] for s in r_a.json()}
    assert "Haircut (A)" in a_names
    assert "Massage (B)" not in a_names


# ---------------------------------------------------------------------------
# Scenario 1 — cross-tenant GET of LIST endpoint is denied (or empty).
# ---------------------------------------------------------------------------


async def test_list_menu_cross_tenant_via_path_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_a_2",
            "restaurant_id": TENANT_A_ID,
            "name": "A-Secret",
            "available": True,
        }
    )
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_b"},
    )
    # Either denied (403/404) or returned an empty list — both are isolation
    # outcomes. What must NOT happen is exposing Tenant A's items.
    if r.status_code == 200:
        names = {it["name"] for it in r.json()}
        assert "A-Secret" not in names
    else:
        assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Scenario 4 — UPDATE/DELETE cross-tenant menu item is denied; record
# unchanged.
# ---------------------------------------------------------------------------


async def test_update_menu_item_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_target",
            "restaurant_id": TENANT_A_ID,
            "name": "Original",
            "price": 10.0,
            "available": True,
        }
    )
    r = client.put(
        "/api/menu/menu_target",
        json={"name": "Hacked", "price": 1, "available": True},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    after = await patched_server_db.menu_items.find_one({"id": "menu_target"})
    assert after["name"] == "Original"
    assert after["price"] == 10.0


async def test_delete_menu_item_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_del_target",
            "restaurant_id": TENANT_A_ID,
            "name": "Stays",
            "available": True,
        }
    )
    r = client.delete(
        "/api/menu/menu_del_target",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert (
        await patched_server_db.menu_items.count_documents({"id": "menu_del_target"})
        == 1
    )


async def test_update_modifier_group_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.modifier_groups.insert_one(
        {
            "id": "mg_target",
            "restaurant_id": TENANT_A_ID,
            "name": "Original MG",
            "min_select": 0,
            "max_select": 1,
            "modifiers": [],
        }
    )
    r = client.put(
        "/api/modifier-groups/mg_target",
        json={"name": "Hacked MG", "min_select": 0, "max_select": 1, "modifiers": []},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    after = await patched_server_db.modifier_groups.find_one({"id": "mg_target"})
    assert after["name"] == "Original MG"


async def test_delete_service_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.services.insert_one(
        {
            "id": "svc_target",
            "restaurant_id": TENANT_A_ID,
            "name": "Premium Wash",
            "duration_minutes": 45,
            "price": 60.0,
        }
    )
    r = client.delete(
        "/api/services/svc_target",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert await patched_server_db.services.count_documents({"id": "svc_target"}) == 1


# ---------------------------------------------------------------------------
# Scenario 3 — unauthenticated list returns 401.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/restaurants/{rid}/menu",
        "/api/restaurants/{rid}/modifier-groups",
        "/api/restaurants/{rid}/services",
        "/api/restaurants/{rid}/menu-with-modifiers",
    ],
)
async def test_catalog_list_unauth_returns_401(
    client, two_tenant_with_memberships, path
):
    r = client.get(path.format(rid=TENANT_A_ID))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Scenario 5 — mass-assignment: creating a menu item under your own
# restaurant must not leak into Tenant A's menu just because the body has
# restaurant_id=tenant_a. The route uses the path param, so the body field
# is ignored — assert that property explicitly.
# ---------------------------------------------------------------------------


async def test_create_menu_item_body_restaurant_id_is_ignored(
    client, patched_server_db, two_tenant_with_memberships
):
    payload = {
        "name": "Trojan",
        "price": 1.0,
        "available": True,
        "category": "main",
        "restaurant_id": TENANT_A_ID,  # claim ownership of A's menu
    }
    r = client.post(
        f"/api/restaurants/{TENANT_B_ID}/menu",
        json=payload,
        headers={"Authorization": "Bearer tenant_b"},
    )
    # Whatever the route returns, no menu item must appear under TENANT_A.
    a_count = await patched_server_db.menu_items.count_documents(
        {"restaurant_id": TENANT_A_ID, "name": "Trojan"}
    )
    assert a_count == 0


# ---------------------------------------------------------------------------
# menu-with-modifiers (composite read) — Tenant B request must not surface
# any of Tenant A's items even if the path was somehow guessable.
# ---------------------------------------------------------------------------


async def test_menu_with_modifiers_cross_tenant_does_not_leak(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_leak_check",
            "restaurant_id": TENANT_A_ID,
            "name": "TopSecretItem",
            "available": True,
        }
    )
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu-with-modifiers",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert "TopSecretItem" not in r.text


# ---------------------------------------------------------------------------
# Expected: cross-tenant GET should be 404 (existence-leak finding). xfail.
# ---------------------------------------------------------------------------


async def test_update_menu_item_cross_tenant_returns_404_expected(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_xfail",
            "restaurant_id": TENANT_A_ID,
            "name": "Item",
            "available": True,
        }
    )
    r = client.put(
        "/api/menu/menu_xfail",
        json={"name": "Hacked", "price": 1, "available": True},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 404
