"""Integration tests — menu items, modifier groups, services."""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Menu item CRUD
# ---------------------------------------------------------------------------


async def test_create_menu_item_persists(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Margherita", "category": "Pizza", "price": 1500},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["restaurant_id"] == TENANT_A_ID
    assert body["price"] == 1500

    saved = await patched_server_db.menu_items.find_one({"id": body["id"]}, {"_id": 0})
    assert saved is not None


async def test_create_menu_item_requires_auth(client):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        json={"name": "X", "category": "Y", "price": 100},
    )
    assert response.status_code == 401


async def test_create_menu_item_rejects_bad_payload(
    client, two_tenant_with_memberships
):
    """Missing required price → 422."""
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Margherita", "category": "Pizza"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad_price", [-1, -1500, 10_000_001])
async def test_create_menu_item_rejects_out_of_range_price(
    client, two_tenant_with_memberships, bad_price
):
    """PL-12: negative or absurdly large prices (cents) → 422 on create."""
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Margherita", "category": "Pizza", "price": bad_price},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad_price", [-1, -1500, 10_000_001])
async def test_update_menu_item_rejects_out_of_range_price(
    client, two_tenant_with_memberships, patched_server_db, bad_price
):
    """PL-12: negative or absurdly large prices (cents) → 422 on update."""
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Old",
            "category": "X",
            "price": 100,
        }
    )
    response = client.put(
        "/api/menu/i1",
        headers={"Authorization": "Bearer tenant_a"},
        json={"price": bad_price},
    )
    assert response.status_code == 422


async def test_create_menu_item_wrong_tenant_404(client, two_tenant_with_memberships):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_b"},
        json={"name": "X", "category": "Y", "price": 100},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET menu list
# ---------------------------------------------------------------------------


async def test_list_menu_items_empty_when_unseeded(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_menu_items_filtered_by_category(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_many(
        [
            {
                "id": "i1",
                "restaurant_id": TENANT_A_ID,
                "name": "Pizza",
                "category": "Pizza",
                "price": 1000,
            },
            {
                "id": "i2",
                "restaurant_id": TENANT_A_ID,
                "name": "Pasta",
                "category": "Pasta",
                "price": 1200,
            },
        ]
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu?category=Pizza",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "Pizza"


async def test_list_menu_items_does_not_leak_other_tenants(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_many(
        [
            {
                "id": "a1",
                "restaurant_id": TENANT_A_ID,
                "name": "A Pie",
                "category": "Pizza",
                "price": 1000,
            },
            {
                "id": "b1",
                "restaurant_id": TENANT_B_ID,
                "name": "B Pie",
                "category": "Pizza",
                "price": 1100,
            },
        ]
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
    )
    names = [i["name"] for i in response.json()]
    assert "A Pie" in names
    assert "B Pie" not in names


# ---------------------------------------------------------------------------
# PUT/DELETE/PATCH menu item
# ---------------------------------------------------------------------------


async def test_update_menu_item(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Old",
            "category": "X",
            "price": 100,
        }
    )
    response = client.put(
        "/api/menu/i1",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "New", "price": 200},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New"
    assert response.json()["price"] == 200


def test_update_menu_item_missing_returns_404(client, mock_clerk):
    response = client.put(
        "/api/menu/nope",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "X"},
    )
    assert response.status_code == 404


async def test_update_menu_item_wrong_tenant_404(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Old",
            "category": "X",
            "price": 100,
        }
    )
    response = client.put(
        "/api/menu/i1",
        headers={"Authorization": "Bearer tenant_b"},
        json={"name": "Hijack"},
    )
    assert response.status_code == 404


async def test_delete_menu_item(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Drop",
            "category": "X",
            "price": 100,
        }
    )
    response = client.delete(
        "/api/menu/i1", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 200
    assert await patched_server_db.menu_items.find_one({"id": "i1"}) is None


def test_delete_menu_item_missing_404(client, mock_clerk):
    response = client.delete(
        "/api/menu/nope", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 404


async def test_toggle_menu_item_availability(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Toggle",
            "category": "X",
            "price": 100,
            "available": True,
        }
    )
    r1 = client.patch(
        "/api/menu/i1/toggle", headers={"Authorization": "Bearer tenant_a"}
    )
    assert r1.status_code == 200
    assert r1.json()["available"] is False

    r2 = client.patch(
        "/api/menu/i1/toggle", headers={"Authorization": "Bearer tenant_a"}
    )
    assert r2.json()["available"] is True


def test_toggle_menu_item_missing_404(client, mock_clerk):
    response = client.patch(
        "/api/menu/nope/toggle", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Modifier groups
# ---------------------------------------------------------------------------


async def test_create_modifier_group(client, two_tenant_with_memberships):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/modifier-groups",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "name": "Size",
            "selection_type": "single",
            "required": True,
            "options": [
                {"name": "Small", "price_delta": 0},
                {"name": "Large", "price_delta": 200},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Size"
    assert len(body["options"]) == 2


async def test_list_modifier_groups_empty(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/modifier-groups",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_update_modifier_group(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.modifier_groups.insert_one(
        {
            "id": "g1",
            "restaurant_id": TENANT_A_ID,
            "name": "Toppings",
            "selection_type": "multiple",
            "required": False,
            "min_selections": 0,
            "max_selections": 5,
            "display_order": 0,
            "active": True,
            "options": [],
        }
    )
    response = client.put(
        "/api/modifier-groups/g1",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Add-ons", "max_selections": 10},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Add-ons"
    assert response.json()["max_selections"] == 10


def test_update_modifier_group_404(client, mock_clerk):
    response = client.put(
        "/api/modifier-groups/nope",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "X"},
    )
    assert response.status_code == 404


async def test_delete_modifier_group_removes_assignments(
    client, two_tenant_with_memberships, patched_server_db
):
    """Deleting a modifier group must also $pull assignments from every menu item."""
    await patched_server_db.modifier_groups.insert_one(
        {
            "id": "g1",
            "restaurant_id": TENANT_A_ID,
            "name": "x",
            "selection_type": "single",
            "required": False,
            "min_selections": 0,
            "max_selections": 1,
            "display_order": 0,
            "active": True,
            "options": [],
        }
    )
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Burger",
            "category": "X",
            "price": 100,
            "modifier_group_assignments": [{"modifier_group_id": "g1"}],
        }
    )
    response = client.delete(
        "/api/modifier-groups/g1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    item = await patched_server_db.menu_items.find_one({"id": "i1"}, {"_id": 0})
    assert item["modifier_group_assignments"] == []


async def test_update_item_modifier_assignments(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "X",
            "category": "Y",
            "price": 100,
        }
    )
    response = client.put(
        "/api/menu/i1/modifier-assignments",
        headers={"Authorization": "Bearer tenant_a"},
        json=[
            {"modifier_group_id": "g1", "display_order": 0},
            {"modifier_group_id": "g2", "display_order": 1},
        ],
    )
    assert response.status_code == 200
    assert len(response.json()["modifier_group_assignments"]) == 2


def test_update_item_modifier_assignments_missing_item_404(client, mock_clerk):
    response = client.put(
        "/api/menu/nope/modifier-assignments",
        headers={"Authorization": "Bearer tenant_a"},
        json=[],
    )
    assert response.status_code == 404


async def test_get_menu_with_modifiers_resolves_groups(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.modifier_groups.insert_one(
        {
            "id": "g1",
            "restaurant_id": TENANT_A_ID,
            "name": "Size",
            "selection_type": "single",
            "required": True,
            "min_selections": 1,
            "max_selections": 1,
            "display_order": 0,
            "active": True,
            "options": [{"id": "o1", "name": "Large", "price_delta": 200}],
        }
    )
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Pizza",
            "category": "Pizza",
            "price": 1000,
            "modifier_group_assignments": [
                {"modifier_group_id": "g1", "display_order": 0}
            ],
        }
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu-with-modifiers",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items[0]["resolved_modifiers"]) == 1
    assert items[0]["resolved_modifiers"][0]["name"] == "Size"


# ---------------------------------------------------------------------------
# Service items (for appointment businesses)
# ---------------------------------------------------------------------------


async def test_create_service(client, two_tenant_with_memberships):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/services",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "Haircut", "duration_minutes": 45},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Haircut"
    assert body["duration_minutes"] == 45


async def test_create_service_rejects_short_name(client, two_tenant_with_memberships):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/services",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "A", "duration_minutes": 30},
    )
    assert response.status_code == 400


async def test_create_service_rejects_out_of_range_duration(
    client, two_tenant_with_memberships
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/services",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "TooShort", "duration_minutes": 1},
    )
    assert response.status_code == 400

    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/services",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "TooLong", "duration_minutes": 1000},
    )
    assert response.status_code == 400


async def test_list_services_empty(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/services",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_update_service(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.services.insert_one(
        {
            "id": "s1",
            "restaurant_id": TENANT_A_ID,
            "name": "Old Service",
            "duration_minutes": 30,
            "buffer_minutes": 5,
            "price_cents": 5000,
            "available": True,
        }
    )
    response = client.put(
        "/api/services/s1",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "New Service", "duration_minutes": 60},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Service"


def test_update_service_missing_404(client, mock_clerk):
    response = client.put(
        "/api/services/nope",
        headers={"Authorization": "Bearer tenant_a"},
        json={"name": "X"},
    )
    assert response.status_code == 404


async def test_update_service_empty_body_400(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.services.insert_one(
        {
            "id": "s1",
            "restaurant_id": TENANT_A_ID,
            "name": "Old",
            "duration_minutes": 30,
        }
    )
    response = client.put(
        "/api/services/s1",
        headers={"Authorization": "Bearer tenant_a"},
        json={},
    )
    assert response.status_code == 400


async def test_delete_service(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.services.insert_one(
        {
            "id": "s1",
            "restaurant_id": TENANT_A_ID,
            "name": "x",
            "duration_minutes": 30,
        }
    )
    response = client.delete(
        "/api/services/s1", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 200


def test_delete_service_missing_404(client, mock_clerk):
    response = client.delete(
        "/api/services/nope", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 404
