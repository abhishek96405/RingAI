"""
Unit tests for backend/pos_sync.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.unit


def _patch_httpx_method(monkeypatch, method, response_or_factory):
    async def fake(self, url, **kwargs):
        if callable(response_or_factory):
            return response_or_factory(url, **kwargs)
        return response_or_factory

    monkeypatch.setattr(httpx.AsyncClient, method, fake)


# ---------------------------------------------------------------------------
# _map_clover_item
# ---------------------------------------------------------------------------

def test_map_clover_item_extracts_basic_fields():
    from pos_sync import _map_clover_item
    item = {
        "id": "clv_1",
        "name": "Cheese Pizza",
        "description": "Hot and cheesy",
        "price": 1299,
        "available": True,
        "categories": {"elements": [{"name": "Pizza"}]},
    }
    mapped = _map_clover_item(item, restaurant_id="rest_a")
    assert mapped["pos_item_id"] == "clv_1"
    assert mapped["name"] == "Cheese Pizza"
    assert mapped["price"] == 1299
    assert mapped["category"] == "Pizza"
    assert mapped["restaurant_id"] == "rest_a"
    assert mapped["available"] is True
    assert "id" in mapped  # uuid generated


def test_map_clover_item_defaults_to_uncategorized():
    from pos_sync import _map_clover_item
    item = {"id": "clv_2", "name": "Mystery Item", "price": 500}
    mapped = _map_clover_item(item, restaurant_id="rest_a")
    assert mapped["category"] == "Uncategorized"


def test_map_clover_item_handles_missing_fields():
    from pos_sync import _map_clover_item
    item = {"id": "clv_3"}
    mapped = _map_clover_item(item, restaurant_id="rest_a")
    assert mapped["name"] == "Unknown Item"
    assert mapped["price"] == 0


# ---------------------------------------------------------------------------
# _map_square_item
# ---------------------------------------------------------------------------

def test_map_square_item_extracts_price_from_variation():
    from pos_sync import _map_square_item
    item = {
        "id": "sq_1",
        "item_data": {
            "name": "Latte",
            "description": "Hot milk + espresso",
            "variations": [{"item_variation_data": {"price_money": {"amount": 450}}}],
            "category": {"name": "Drinks"},
        },
    }
    mapped = _map_square_item(item, restaurant_id="rest_a")
    assert mapped["name"] == "Latte"
    assert mapped["price"] == 450
    assert mapped["category"] == "Drinks"
    assert mapped["pos_item_id"] == "sq_1"


def test_map_square_item_handles_missing_variation():
    from pos_sync import _map_square_item
    item = {"id": "sq_2", "item_data": {"name": "Bread"}}
    mapped = _map_square_item(item, restaurant_id="rest_a")
    assert mapped["price"] == 0


# ---------------------------------------------------------------------------
# sync_menu_from_clover
# ---------------------------------------------------------------------------

async def test_clover_sync_returns_error_when_credentials_missing(async_db):
    from pos_sync import sync_menu_from_clover

    result = await sync_menu_from_clover("rest_a", async_db, restaurant={})
    assert result == {"success": False, "error": "Clover credentials not configured"}


async def test_clover_sync_inserts_new_items(async_db, monkeypatch):
    from pos_sync import sync_menu_from_clover

    payload = {
        "elements": [
            {"id": "clv_1", "name": "Pizza", "price": 1299, "categories": {"elements": [{"name": "Pizza"}]}},
            {"id": "clv_2", "name": "Salad", "price": 799, "categories": {"elements": [{"name": "Sides"}]}},
        ]
    }
    _patch_httpx_method(monkeypatch, "get", httpx.Response(200, json=payload))

    result = await sync_menu_from_clover(
        "rest_a",
        async_db,
        restaurant={"clover_api_token": "tok", "clover_merchant_id": "m", "pos_env": "sandbox"},
    )
    assert result["success"] is True
    assert result["synced"] == 2

    docs = await async_db.menu_items.find({"restaurant_id": "rest_a"}, {"_id": 0}).to_list(10)
    assert len(docs) == 2
    assert {d["pos_item_id"] for d in docs} == {"clv_1", "clv_2"}


async def test_clover_sync_updates_existing_items(async_db, monkeypatch):
    from pos_sync import sync_menu_from_clover

    # Pre-seed an item
    await async_db.menu_items.insert_one({
        "restaurant_id": "rest_a",
        "pos_item_id": "clv_1",
        "name": "Old Name",
        "price": 999,
        "available": True,
    })

    payload = {"elements": [{"id": "clv_1", "name": "New Name", "price": 1499}]}
    _patch_httpx_method(monkeypatch, "get", httpx.Response(200, json=payload))

    await sync_menu_from_clover(
        "rest_a", async_db,
        restaurant={"clover_api_token": "tok", "clover_merchant_id": "m"},
    )

    doc = await async_db.menu_items.find_one({"restaurant_id": "rest_a", "pos_item_id": "clv_1"})
    assert doc["name"] == "New Name"
    assert doc["price"] == 1499


async def test_clover_sync_handles_non_200(async_db, monkeypatch):
    from pos_sync import sync_menu_from_clover

    _patch_httpx_method(monkeypatch, "get", httpx.Response(401, text="unauthorized"))

    result = await sync_menu_from_clover(
        "rest_a", async_db,
        restaurant={"clover_api_token": "tok", "clover_merchant_id": "m"},
    )
    assert result["success"] is False
    assert "401" in result["error"]


async def test_clover_sync_handles_exception(async_db, monkeypatch):
    from pos_sync import sync_menu_from_clover

    async def boom(self, url, **kwargs):
        raise httpx.ConnectError("net down")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)

    result = await sync_menu_from_clover(
        "rest_a", async_db,
        restaurant={"clover_api_token": "tok", "clover_merchant_id": "m"},
    )
    assert result["success"] is False
    assert result["error"]


async def test_clover_sync_uses_production_url_when_env_is_production(async_db, monkeypatch):
    from pos_sync import sync_menu_from_clover

    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["url"] = url
        return httpx.Response(200, json={"elements": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await sync_menu_from_clover(
        "rest_a", async_db,
        restaurant={"clover_api_token": "tok", "clover_merchant_id": "m", "pos_env": "production"},
    )
    assert "api.clover.com" in captured["url"]


# ---------------------------------------------------------------------------
# sync_menu_from_square
# ---------------------------------------------------------------------------

async def test_square_sync_returns_error_without_token(async_db):
    from pos_sync import sync_menu_from_square
    result = await sync_menu_from_square("rest_a", async_db, restaurant={})
    assert result["success"] is False


async def test_square_sync_inserts_new_items(async_db, monkeypatch):
    from pos_sync import sync_menu_from_square

    payload = {
        "objects": [
            {
                "id": "sq_1",
                "item_data": {
                    "name": "Latte",
                    "variations": [{"item_variation_data": {"price_money": {"amount": 450}}}],
                },
            }
        ]
    }
    _patch_httpx_method(monkeypatch, "get", httpx.Response(200, json=payload))

    result = await sync_menu_from_square(
        "rest_a", async_db,
        restaurant={"square_access_token": "tok"},
    )
    assert result["success"] is True
    assert result["synced"] == 1


async def test_square_sync_handles_non_200(async_db, monkeypatch):
    from pos_sync import sync_menu_from_square

    _patch_httpx_method(monkeypatch, "get", httpx.Response(403, text="forbidden"))

    result = await sync_menu_from_square(
        "rest_a", async_db,
        restaurant={"square_access_token": "tok"},
    )
    assert result["success"] is False


async def test_square_sync_uses_sandbox_url_when_env_is_sandbox(async_db, monkeypatch):
    from pos_sync import sync_menu_from_square

    monkeypatch.setenv("SQUARE_ENVIRONMENT", "sandbox")
    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["url"] = url
        return httpx.Response(200, json={"objects": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    await sync_menu_from_square(
        "rest_a", async_db,
        restaurant={"square_access_token": "tok"},
    )
    assert "connect.squareupsandbox.com" in captured["url"]


async def test_square_sync_uses_production_url_when_env_is_production(async_db, monkeypatch):
    from pos_sync import sync_menu_from_square

    monkeypatch.setenv("SQUARE_ENVIRONMENT", "production")
    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["url"] = url
        return httpx.Response(200, json={"objects": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    await sync_menu_from_square(
        "rest_a", async_db,
        restaurant={"square_access_token": "tok"},
    )
    assert "squareupsandbox" not in captured["url"]
    assert "connect.squareup.com" in captured["url"]


# ---------------------------------------------------------------------------
# sync_menu_from_pos — routing
# ---------------------------------------------------------------------------

async def test_sync_routes_to_clover(async_db, monkeypatch):
    from pos_sync import sync_menu_from_pos
    _patch_httpx_method(monkeypatch, "get", httpx.Response(200, json={"elements": []}))
    result = await sync_menu_from_pos(
        "rest_a",
        {"pos_type": "clover", "clover_api_token": "tok", "clover_merchant_id": "m"},
        async_db,
    )
    assert result["source"] == "clover"


async def test_sync_routes_to_square(async_db, monkeypatch):
    from pos_sync import sync_menu_from_pos
    _patch_httpx_method(monkeypatch, "get", httpx.Response(200, json={"objects": []}))
    result = await sync_menu_from_pos(
        "rest_a",
        {"pos_type": "square", "square_access_token": "tok"},
        async_db,
    )
    assert result["source"] == "square"


async def test_sync_returns_error_for_unknown_pos_type(async_db):
    from pos_sync import sync_menu_from_pos
    result = await sync_menu_from_pos(
        "rest_a", {"pos_type": "unknown"}, async_db,
    )
    assert result["success"] is False
    assert "No POS" in result["error"]
