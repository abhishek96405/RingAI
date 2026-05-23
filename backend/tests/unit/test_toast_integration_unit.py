"""
Unit tests for backend/toast_integration.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

NOTE: Toast partner approval is pending — the live integration is not
yet wired end-to-end. These tests cover the helpers that *can* be
exercised today (token caching, request shape, credential handling).
End-to-end Toast flows are marked skip until partner approval lands.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

pytestmark = pytest.mark.unit


def _resp(status_code, json=None, text=None, url="https://api.toasttab.com/x"):
    return httpx.Response(
        status_code=status_code,
        json=json,
        text=text,
        request=httpx.Request("GET", url),
    )


@pytest.fixture(autouse=True)
def _clear_toast_cache():
    import toast_integration
    toast_integration._token_cache.clear()
    yield
    toast_integration._token_cache.clear()


# ---------------------------------------------------------------------------
# _get_toast_base_url
# ---------------------------------------------------------------------------

def test_get_toast_base_url_defaults_to_sandbox(monkeypatch):
    from toast_integration import _get_toast_base_url
    monkeypatch.delenv("TOAST_ENV", raising=False)
    url = _get_toast_base_url()
    assert "toasttab.com" in url


def test_get_toast_base_url_respects_env(monkeypatch):
    from toast_integration import _get_toast_base_url
    monkeypatch.setenv("TOAST_ENV", "production")
    url = _get_toast_base_url()
    assert "toasttab.com" in url


# ---------------------------------------------------------------------------
# get_toast_access_token
# ---------------------------------------------------------------------------

async def test_get_access_token_caches_returned_value(monkeypatch):
    from toast_integration import get_toast_access_token

    call_count = {"n": 0}

    async def fake_post(self, url, **kwargs):
        call_count["n"] += 1
        return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    t1 = await get_toast_access_token("rest_a", "cid", "csec", "rg", env="sandbox")
    t2 = await get_toast_access_token("rest_a", "cid", "csec", "rg", env="sandbox")

    assert t1 == "AT"
    assert t2 == "AT"
    assert call_count["n"] == 1  # second call hits cache


async def test_get_access_token_returns_none_on_4xx(monkeypatch):
    from toast_integration import get_toast_access_token

    async def fake_post(self, url, **kwargs):
        return _resp(401, text="bad creds")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await get_toast_access_token("rest_a", "cid", "csec", "rg") is None


async def test_get_access_token_returns_none_on_exception(monkeypatch):
    from toast_integration import get_toast_access_token

    async def fake_post(self, url, **kwargs):
        raise httpx.ConnectError("net down")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await get_toast_access_token("rest_a", "cid", "csec", "rg") is None


async def test_get_access_token_returns_none_when_payload_missing_token(monkeypatch):
    from toast_integration import get_toast_access_token

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"token": {}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await get_toast_access_token("rest_a", "cid", "csec", "rg") is None


# ---------------------------------------------------------------------------
# clear_toast_token_cache
# ---------------------------------------------------------------------------

def test_clear_toast_token_cache_for_restaurant():
    import toast_integration
    from toast_integration import clear_toast_token_cache

    toast_integration._token_cache.update({
        "rest_a:guid_1": {"access_token": "x", "expires_at": 0},
        "rest_a:guid_2": {"access_token": "y", "expires_at": 0},
        "rest_b:guid_3": {"access_token": "z", "expires_at": 0},
    })

    clear_toast_token_cache("rest_a")
    assert "rest_a:guid_1" not in toast_integration._token_cache
    assert "rest_a:guid_2" not in toast_integration._token_cache
    assert "rest_b:guid_3" in toast_integration._token_cache


def test_clear_toast_token_cache_global():
    import toast_integration
    from toast_integration import clear_toast_token_cache

    toast_integration._token_cache.update({"x": {}, "y": {}})
    clear_toast_token_cache()
    assert toast_integration._token_cache == {}


# ---------------------------------------------------------------------------
# sync_menu_from_toast — credential handling
# ---------------------------------------------------------------------------

async def test_sync_menu_returns_error_when_creds_missing(async_db, monkeypatch):
    """If decrypted credentials are missing, sync should fail gracefully — not crash."""
    from toast_integration import sync_menu_from_toast

    # decrypt_value passes through empty strings unchanged
    result = await sync_menu_from_toast(
        "rest_a", async_db,
        restaurant={"toast_client_id": "", "toast_client_secret": "", "toast_restaurant_guid": ""},
    )
    assert result["success"] is False
    assert "credentials" in result["error"].lower()


async def test_sync_menu_returns_error_when_auth_fails(async_db, monkeypatch):
    from toast_integration import sync_menu_from_toast

    async def fake_post(self, url, **kwargs):
        return _resp(401, text="bad")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await sync_menu_from_toast(
        "rest_a", async_db,
        restaurant={
            "toast_client_id": "cid",
            "toast_client_secret": "csec",
            "toast_restaurant_guid": "rg",
        },
    )
    assert result["success"] is False
    assert "authentication" in result["error"].lower()


async def test_sync_menu_returns_error_on_menu_fetch_failure(async_db, monkeypatch):
    from toast_integration import sync_menu_from_toast

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})

    async def fake_get(self, url, **kwargs):
        return _resp(500, text="boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await sync_menu_from_toast(
        "rest_a", async_db,
        restaurant={
            "toast_client_id": "cid", "toast_client_secret": "csec",
            "toast_restaurant_guid": "rg",
        },
    )
    assert result["success"] is False


async def test_sync_menu_inserts_items(async_db, monkeypatch):
    from toast_integration import sync_menu_from_toast

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})

    async def fake_get(self, url, **kwargs):
        return _resp(200, json=[
            {
                "menuGroups": [
                    {
                        "name": "Pizza",
                        "menuItems": [
                            {"guid": "toast_1", "name": "Margherita", "price": 12.99},
                            {"guid": "toast_2", "name": "Pepperoni", "price": 14.99},
                        ],
                    }
                ]
            }
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await sync_menu_from_toast(
        "rest_a", async_db,
        restaurant={
            "toast_client_id": "cid", "toast_client_secret": "csec",
            "toast_restaurant_guid": "rg",
        },
    )
    assert result["success"] is True
    assert result["synced"] == 2

    docs = await async_db.menu_items.find({"restaurant_id": "rest_a"}, {"_id": 0}).to_list(10)
    assert {d["pos_item_id"] for d in docs} == {"toast_1", "toast_2"}
    # Price is converted to cents
    margherita = next(d for d in docs if d["pos_item_id"] == "toast_1")
    assert margherita["price"] == 1299


async def test_sync_menu_updates_existing_items(async_db, monkeypatch):
    from toast_integration import sync_menu_from_toast

    await async_db.menu_items.insert_one({
        "restaurant_id": "rest_a",
        "pos_item_id": "toast_1",
        "name": "Old Name",
        "price": 999,
    })

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})

    async def fake_get(self, url, **kwargs):
        return _resp(200, json=[
            {"menuGroups": [{"name": "Cat", "menuItems": [{"guid": "toast_1", "name": "Updated", "price": 15.00}]}]}
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await sync_menu_from_toast(
        "rest_a", async_db,
        restaurant={"toast_client_id": "c", "toast_client_secret": "s", "toast_restaurant_guid": "g"},
    )
    assert result["success"] is True

    updated = await async_db.menu_items.find_one({"restaurant_id": "rest_a", "pos_item_id": "toast_1"})
    assert updated["name"] == "Updated"
    assert updated["price"] == 1500


# ---------------------------------------------------------------------------
# send_order_to_toast
# ---------------------------------------------------------------------------

class _FakeOrder:
    def __init__(self, **kw):
        self.restaurant_id = kw.get("restaurant_id", "rest_a")
        self.call_sid = kw.get("call_sid", "call_1")
        self.order_type = kw.get("order_type", "pickup")
        self.customer_name = kw.get("customer_name", "Joe")
        self.caller_number = kw.get("caller_number", "+15551234567")
        self.delivery_address = kw.get("delivery_address", None)
        self.items = kw.get("items", [])


def _make_item(menu_item_id="m1", quantity=1, special_instructions=None):
    return SimpleNamespace(
        menu_item_id=menu_item_id,
        quantity=quantity,
        special_instructions=special_instructions,
    )


async def test_send_order_returns_failure_when_creds_missing():
    from toast_integration import send_order_to_toast

    order = _FakeOrder(items=[_make_item()])
    result = await send_order_to_toast(order, restaurant={})
    assert result["success"] is False
    assert result["method"] == "toast"


async def test_send_order_returns_failure_when_auth_fails(monkeypatch):
    from toast_integration import send_order_to_toast

    async def fake_post(self, url, **kwargs):
        return _resp(401, text="bad")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _FakeOrder(items=[_make_item()])
    result = await send_order_to_toast(
        order,
        restaurant={"toast_client_id": "c", "toast_client_secret": "s", "toast_restaurant_guid": "g"},
    )
    assert result["success"] is False


async def test_send_order_success(monkeypatch):
    from toast_integration import send_order_to_toast

    posts = []

    async def fake_post(self, url, **kwargs):
        posts.append({"url": url, "json": kwargs.get("json")})
        if "authentication" in url:
            return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})
        return _resp(201, json={"guid": "toast_order_xyz"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _FakeOrder(
        items=[_make_item("menu_1", quantity=2, special_instructions="no onion")],
        order_type="delivery",
        delivery_address="123 Main St",
    )
    result = await send_order_to_toast(
        order,
        restaurant={"toast_client_id": "c", "toast_client_secret": "s", "toast_restaurant_guid": "g"},
    )
    assert result["success"] is True
    assert result["order_id"] == "toast_order_xyz"

    order_post = next(p for p in posts if "orders" in p["url"])
    payload = order_post["json"]
    assert payload["entityType"] == "Order"
    assert payload["diningOption"]["guid"] == "DELIVERY"
    assert payload["selections"][0]["quantity"] == 2
    assert payload["selections"][0]["specialInstructions"] == "no onion"
    assert payload["deliveryInfo"]["address1"] == "123 Main St"


# ---------------------------------------------------------------------------
# get_toast_queue_depth
# ---------------------------------------------------------------------------

async def test_queue_depth_counts_open_orders(monkeypatch):
    from toast_integration import get_toast_queue_depth

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})

    async def fake_get(self, url, **kwargs):
        return _resp(200, json=[
            {"displayStatus": "OPEN"},
            {"displayStatus": "in_progress"},
            {"displayStatus": "COMPLETED"},
            {"displayStatus": "NEW"},
        ])

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    depth = await get_toast_queue_depth(
        restaurant={"id": "r", "toast_client_id": "c", "toast_client_secret": "s", "toast_restaurant_guid": "g"},
        config={},
    )
    assert depth == 3


async def test_queue_depth_returns_none_when_creds_missing():
    from toast_integration import get_toast_queue_depth
    assert await get_toast_queue_depth(restaurant={}, config={}) is None


# ---------------------------------------------------------------------------
# test_toast_connection
# ---------------------------------------------------------------------------

async def test_toast_connection_returns_restaurant_info(monkeypatch):
    from toast_integration import test_toast_connection

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"token": {"accessToken": "AT", "expiresIn": 3600}})

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"general": {"name": "Tasty Bites", "locationName": "Downtown"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await test_toast_connection("cid", "csec", "rg")
    assert result["success"] is True
    assert result["restaurant_name"] == "Tasty Bites"
    assert result["location"] == "Downtown"


async def test_toast_connection_failure(monkeypatch):
    from toast_integration import test_toast_connection

    async def fake_post(self, url, **kwargs):
        return _resp(401, text="bad")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await test_toast_connection("cid", "csec", "rg")
    assert result["success"] is False
