"""
Unit tests for backend/gemini_service.py — POS dispatch helpers.

Covers send_order_to_kitchen, _send_to_clover, _send_to_square,
_send_to_kitchen_webhook, and get_kitchen_queue_depth.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.unit


def _resp(status_code, json=None, text=None, url="https://api.example/x"):
    return httpx.Response(
        status_code=status_code,
        json=json,
        text=text,
        request=httpx.Request("POST", url),
    )


def _make_order(items=None, **kw):
    from gemini_service import LiveOrder, OrderItem

    order = LiveOrder(
        restaurant_id=kw.get("restaurant_id", "rest_a"),
        call_sid=kw.get("call_sid", "call_abcd1234"),
        caller_number=kw.get("caller_number", "+15551234567"),
        customer_name=kw.get("customer_name", "Joe"),
        order_type=kw.get("order_type", "pickup"),
        delivery_address=kw.get("delivery_address", ""),
        special_instructions=kw.get("special_instructions", ""),
    )
    if items is None:
        items = [OrderItem(
            name="Pizza", menu_item_id="p1", category="Pizza",
            unit_price=1299, quantity=1,
        )]
    order.items.extend(items)
    return order


# ---------------------------------------------------------------------------
# send_order_to_kitchen routing
# ---------------------------------------------------------------------------

async def test_routes_to_toast_when_pos_type_toast(monkeypatch):
    from gemini_service import send_order_to_kitchen

    toast_mock = AsyncMock(return_value={"success": True, "order_id": "toast_1", "method": "toast"})
    monkeypatch.setattr("toast_integration.send_order_to_toast", toast_mock)

    out = await send_order_to_kitchen(_make_order(), {"pos_type": "toast"})
    assert out["method"] == "toast"
    toast_mock.assert_awaited_once()


async def test_toast_failure_without_webhook_reports_failure(monkeypatch):
    """A configured POS (Toast) that fails with no webhook fallback must NOT be
    reported as a DB success — that is the A7-1 silent-order-loss bug. It must
    surface as a failure so the operator gets alerted."""
    from gemini_service import send_order_to_kitchen

    monkeypatch.setattr("toast_integration.send_order_to_toast",
                        AsyncMock(return_value={"success": False, "order_id": "", "method": "toast",
                                                "error": "Toast 500"}))
    monkeypatch.delenv("KITCHEN_WEBHOOK_URL", raising=False)

    out = await send_order_to_kitchen(_make_order(), {"pos_type": "toast"})
    assert out["success"] is False
    assert out["method"] == "toast"
    assert out["attempted_pos"] == "toast"
    assert out["fallback_saved"] is True
    assert out["error"]


async def test_routes_to_clover_when_credentials_present(monkeypatch):
    from gemini_service import send_order_to_kitchen

    async def fake_post(self, url, **kwargs):
        if "/orders" in url and "/line_items" not in url:
            return _resp(201, json={"id": "clover_order_xyz"})
        return _resp(201, json={"id": "li_1"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await send_order_to_kitchen(_make_order(), {
        "pos_type": "clover",
        "clover_api_token": "tok",
        "clover_merchant_id": "m",
    })
    assert out["method"] == "clover"
    assert out["order_id"] == "clover_order_xyz"


async def test_clover_returns_failure_on_create_order_error(monkeypatch):
    from gemini_service import _send_to_clover

    async def fake_post(self, url, **kwargs):
        return _resp(500, text="boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_clover(_make_order(), {
        "clover_api_token": "tok",
        "clover_merchant_id": "m",
    })
    assert out["success"] is False


async def test_clover_handles_network_exception(monkeypatch):
    from gemini_service import _send_to_clover

    async def boom(self, *a, **k):
        raise httpx.ConnectError("net")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    out = await _send_to_clover(_make_order(), {"clover_api_token": "t", "clover_merchant_id": "m"})
    assert out["success"] is False


async def test_clover_uses_production_url_for_production_env(monkeypatch):
    from gemini_service import _send_to_clover

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured.setdefault("urls", []).append(url)
        return _resp(201, json={"id": "ord_1"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await _send_to_clover(_make_order(), {
        "clover_api_token": "t",
        "clover_merchant_id": "m",
        "pos_env": "production",
    })
    assert any("api.clover.com" in u for u in captured["urls"])


# ---------------------------------------------------------------------------
# _send_to_square
# ---------------------------------------------------------------------------

async def test_square_dispatch_happy_path(monkeypatch):
    from gemini_service import _send_to_square

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"order": {"id": "sq_order_1"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_square(_make_order(), {
        "square_access_token": "t",
        "square_location_id": "loc_1",
    })
    assert out["success"] is True
    assert out["order_id"] == "sq_order_1"


async def test_square_dispatch_missing_credentials_returns_failure():
    from gemini_service import _send_to_square
    out = await _send_to_square(_make_order(), {})
    assert out["success"] is False


async def test_square_dispatch_handles_error_response(monkeypatch):
    from gemini_service import _send_to_square

    async def fake_post(self, url, **kwargs):
        return _resp(400, json={"errors": ["bad request"]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_square(_make_order(), {
        "square_access_token": "t",
        "square_location_id": "loc_1",
    })
    assert out["success"] is False


async def test_square_dispatch_handles_exception(monkeypatch):
    from gemini_service import _send_to_square

    async def boom(self, *a, **k):
        raise httpx.ConnectError("net")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    out = await _send_to_square(_make_order(), {
        "square_access_token": "t", "square_location_id": "loc",
    })
    assert out["success"] is False


# ---------------------------------------------------------------------------
# _send_to_kitchen_webhook
# ---------------------------------------------------------------------------

async def test_kitchen_webhook_happy_path(monkeypatch):
    from gemini_service import _send_to_kitchen_webhook

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["payload"] = kwargs.get("json")
        return _resp(200, json={"order_id": "webhook_order_1"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_kitchen_webhook(_make_order(), "https://kitchen.test/webhook")
    assert out["success"] is True
    assert out["order_id"] == "webhook_order_1"
    assert captured["payload"]["source"] == "ringai_phone"


async def test_kitchen_webhook_uses_default_order_id_when_response_missing(monkeypatch):
    from gemini_service import _send_to_kitchen_webhook

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_kitchen_webhook(_make_order(), "https://kitchen.test/webhook")
    assert out["success"] is True
    assert out["order_id"].startswith("DTH-")


async def test_kitchen_webhook_returns_failure_on_exception(monkeypatch):
    from gemini_service import _send_to_kitchen_webhook

    async def boom(self, *a, **k):
        raise httpx.ConnectError("net")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    out = await _send_to_kitchen_webhook(_make_order(), "https://kitchen.test/webhook")
    assert out["success"] is False


# ---------------------------------------------------------------------------
# get_kitchen_queue_depth
# ---------------------------------------------------------------------------

async def test_queue_depth_routes_to_toast(monkeypatch):
    from gemini_service import get_kitchen_queue_depth

    monkeypatch.setattr("toast_integration.get_toast_queue_depth",
                        AsyncMock(return_value=5))

    out = await get_kitchen_queue_depth({"pos_type": "toast"}, {})
    assert out == 5


async def test_queue_depth_for_clover(monkeypatch):
    from gemini_service import get_kitchen_queue_depth

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"elements": [{}, {}, {}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    out = await get_kitchen_queue_depth({
        "pos_type": "clover",
        "clover_api_token": "t",
        "clover_merchant_id": "m",
    }, {})
    assert out == 3


async def test_queue_depth_for_square(monkeypatch):
    from gemini_service import get_kitchen_queue_depth

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"orders": [{}, {}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await get_kitchen_queue_depth({
        "pos_type": "square",
        "square_access_token": "t",
    }, {})
    assert out == 2


async def test_queue_depth_returns_none_on_exception(monkeypatch):
    from gemini_service import get_kitchen_queue_depth

    async def boom(self, *a, **k):
        raise httpx.ConnectError("net")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)

    out = await get_kitchen_queue_depth({
        "pos_type": "clover", "clover_api_token": "t", "clover_merchant_id": "m",
    }, {})
    assert out is None


async def test_queue_depth_returns_none_when_no_pos_type():
    from gemini_service import get_kitchen_queue_depth
    out = await get_kitchen_queue_depth({}, {})
    assert out is None


async def test_queue_depth_legacy_fallback_to_clover_by_credentials(monkeypatch):
    """When pos_type is empty but Clover creds exist, queue depth still works."""
    from gemini_service import get_kitchen_queue_depth

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"elements": [{}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    out = await get_kitchen_queue_depth({
        "clover_api_token": "t",
        "clover_merchant_id": "m",
    }, {})
    assert out == 1


# ---------------------------------------------------------------------------
# A7-1: failed POS dispatch must be visible (no silent order loss).
# ---------------------------------------------------------------------------

async def test_square_failure_no_webhook_returns_failure(monkeypatch):
    """pos_type=square + Square HTTP failure + no webhook → success False,
    attempted_pos 'square', fallback_saved True, error populated."""
    from gemini_service import send_order_to_kitchen

    async def fake_post(self, url, **kwargs):
        return _resp(401, json={"errors": [{"code": "UNAUTHORIZED"}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.delenv("KITCHEN_WEBHOOK_URL", raising=False)

    out = await send_order_to_kitchen(_make_order(), {
        "pos_type": "square",
        "square_access_token": "t",
        "square_location_id": "loc_1",
    })
    assert out["success"] is False
    assert out["attempted_pos"] == "square"
    assert out["method"] == "square"
    assert out["fallback_saved"] is True
    assert out["error"]  # non-empty, PII-free reason
    assert out["order_id"].startswith("DTH-")


async def test_square_failure_with_webhook_fallback_succeeds(monkeypatch):
    """pos_type=square + Square failure + KITCHEN_WEBHOOK_URL success → an
    explicitly configured webhook is a real fulfillment channel → success True."""
    from gemini_service import send_order_to_kitchen

    async def fake_post(self, url, **kwargs):
        if "/v2/orders" in url:  # Square
            return _resp(500, json={"errors": [{"code": "INTERNAL"}]})
        return _resp(200, json={"order_id": "webhook_1"})  # webhook

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("KITCHEN_WEBHOOK_URL", "https://kitchen.test/webhook")

    out = await send_order_to_kitchen(_make_order(), {
        "pos_type": "square",
        "square_access_token": "t",
        "square_location_id": "loc_1",
    })
    assert out["success"] is True
    assert "webhook" in out["method"]
    # attempted_pos is preserved through the webhook-rescued path.
    assert out["attempted_pos"] == "square"
    assert out["fallback_saved"] is False


async def test_no_pos_configured_is_database_success(monkeypatch):
    """No pos_type and no credentials → dashboard-only mode. DB-only success is
    CORRECT here and must be regression-protected (attempted_pos None)."""
    from gemini_service import send_order_to_kitchen

    monkeypatch.delenv("KITCHEN_WEBHOOK_URL", raising=False)

    out = await send_order_to_kitchen(_make_order(), {})
    assert out["success"] is True
    assert out["method"] == "database"
    assert out["attempted_pos"] is None
    assert out["fallback_saved"] is False


# ---------------------------------------------------------------------------
# A7-2: POS orders must produce real, visible tickets.
# ---------------------------------------------------------------------------

async def test_square_body_includes_state_open_and_pickup_fulfillment(monkeypatch):
    from gemini_service import _send_to_square

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={"order": {"id": "sq_1"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_square(_make_order(order_type="pickup"), {
        "square_access_token": "t", "square_location_id": "loc_1",
    })
    assert out["success"] is True
    order_body = captured["json"]["order"]
    assert order_body["state"] == "OPEN"
    fulfillments = order_body["fulfillments"]
    assert len(fulfillments) == 1
    f = fulfillments[0]
    assert f["type"] == "PICKUP"
    assert f["state"] == "PROPOSED"
    assert f["pickup_details"]["recipient"]["display_name"] == "Joe"
    # None values are stripped (Square rejects nulls on fulfillment fields).
    assert _no_none_values(f)


async def test_square_body_includes_delivery_fulfillment_for_delivery_order(monkeypatch):
    from gemini_service import _send_to_square

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={"order": {"id": "sq_1"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _make_order(order_type="delivery", delivery_address="1234 Elm St, Austin TX")
    out = await _send_to_square(order, {
        "square_access_token": "t", "square_location_id": "loc_1",
    })
    assert out["success"] is True
    f = captured["json"]["order"]["fulfillments"][0]
    assert f["type"] == "DELIVERY"
    assert f["state"] == "PROPOSED"
    assert f["delivery_details"]["recipient"]["address"]["address_line_1"] == "1234 Elm St, Austin TX"


def _no_none_values(value) -> bool:
    if isinstance(value, dict):
        return all(v is not None and _no_none_values(v) for v in value.values())
    if isinstance(value, list):
        return all(_no_none_values(v) for v in value)
    return True


async def test_clover_create_payload_has_state_open_and_fires_print_event(monkeypatch):
    """Clover order create must include state 'open' (else invisible in Register)
    and a print_event must be POSTed after line items."""
    from gemini_service import _send_to_clover

    posts = []

    async def fake_post(self, url, **kwargs):
        posts.append({"url": url, "json": kwargs.get("json")})
        if url.endswith("/orders"):
            return _resp(201, json={"id": "clv_1"})
        return _resp(201, json={"id": "x"})  # line_items + print_event

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_clover(_make_order(), {
        "clover_api_token": "t", "clover_merchant_id": "m",
    })
    assert out["success"] is True
    assert out["printed"] is True

    create = next(p for p in posts if p["url"].endswith("/orders"))
    assert create["json"]["state"] == "open"

    # print_event POSTed, and it came AFTER the line items.
    urls = [p["url"] for p in posts]
    pe_idx = next(i for i, u in enumerate(urls) if u.endswith("/print_event"))
    li_idx = max(i for i, u in enumerate(urls) if u.endswith("/line_items"))
    assert pe_idx > li_idx


async def test_clover_print_event_failure_still_succeeds_printed_false(monkeypatch):
    """A print_event failure must NOT fail the dispatch — the order is already
    visible in Register. Return success True with printed False."""
    from gemini_service import _send_to_clover

    async def fake_post(self, url, **kwargs):
        if url.endswith("/print_event"):
            return _resp(500, text="printer offline")
        if url.endswith("/orders"):
            return _resp(201, json={"id": "clv_1"})
        return _resp(201, json={"id": "x"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await _send_to_clover(_make_order(), {
        "clover_api_token": "t", "clover_merchant_id": "m",
    })
    assert out["success"] is True
    assert out["printed"] is False
    assert out["order_id"] == "clv_1"


# ---------------------------------------------------------------------------
# PR-A.1: Clover countable quantity — one line-item POST per unit, no unitQty.
# ---------------------------------------------------------------------------

def _clover_line_item_recorder():
    """Return (fake_post, posts) where posts captures every line-item payload."""
    posts: list = []

    async def fake_post(self, url, **kwargs):
        if url.endswith("/line_items"):
            posts.append(kwargs.get("json"))
            return _resp(201, json={"id": "li"})
        if url.endswith("/orders"):
            return _resp(201, json={"id": "clv_1"})
        return _resp(201, json={"id": "x"})  # print_event

    return fake_post, posts


async def test_clover_posts_one_line_item_per_unit(monkeypatch):
    """A countable item with quantity 3 is added as 3 separate line-item POSTs,
    each carrying name/price + special_instructions. No unitQty is ever sent —
    unitQty is for measure/weight-priced catalog items and mis-prices countables."""
    from gemini_service import _send_to_clover, OrderItem

    fake_post, posts = _clover_line_item_recorder()
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _make_order(items=[
        OrderItem(name="Taco", menu_item_id="t1", category="Tacos",
                  unit_price=350, quantity=3, special_instructions="no cilantro"),
    ])
    out = await _send_to_clover(order, {"clover_api_token": "t", "clover_merchant_id": "m"})
    assert out["success"] is True
    assert len(posts) == 3
    for li in posts:
        assert li["name"] == "Taco"
        assert li["price"] == 350
        assert li["note"] == "no cilantro"
        assert "unitQty" not in li


async def test_clover_multiple_items_post_counts_are_per_unit(monkeypatch):
    """Two distinct items (qty 2 and qty 1) produce 2 + 1 = 3 line-item POSTs."""
    from gemini_service import _send_to_clover, OrderItem

    fake_post, posts = _clover_line_item_recorder()
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _make_order(items=[
        OrderItem(name="Burrito", menu_item_id="b1", category="Mains",
                  unit_price=900, quantity=2),
        OrderItem(name="Coffee", menu_item_id="c1", category="Drinks",
                  unit_price=200, quantity=1),
    ])
    out = await _send_to_clover(order, {"clover_api_token": "t", "clover_merchant_id": "m"})
    assert out["success"] is True
    assert sum(1 for li in posts if li["name"] == "Burrito") == 2
    assert sum(1 for li in posts if li["name"] == "Coffee") == 1
    assert all("unitQty" not in li for li in posts)


async def test_clover_quantity_one_posts_exactly_once(monkeypatch):
    from gemini_service import _send_to_clover, OrderItem

    fake_post, posts = _clover_line_item_recorder()
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _make_order(items=[
        OrderItem(name="Coffee", menu_item_id="c1", category="Drinks",
                  unit_price=200, quantity=1),
    ])
    await _send_to_clover(order, {"clover_api_token": "t", "clover_merchant_id": "m"})
    assert len(posts) == 1
    assert "unitQty" not in posts[0]


async def test_clover_quantity_zero_guard_posts_exactly_once(monkeypatch):
    """Guard: a non-positive quantity still posts exactly once — never zero,
    never a negative loop."""
    from gemini_service import _send_to_clover, OrderItem

    fake_post, posts = _clover_line_item_recorder()
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _make_order(items=[
        OrderItem(name="Mint", menu_item_id="m1", category="Extras",
                  unit_price=0, quantity=0),
    ])
    await _send_to_clover(order, {"clover_api_token": "t", "clover_merchant_id": "m"})
    assert len(posts) == 1


# ---------------------------------------------------------------------------
# A7-3: a Clover line-item POST failure leaves a partial order — must surface
# as a failure (not silent success) so the operator gets alerted.
# ---------------------------------------------------------------------------

async def test_clover_line_item_failure_surfaces_as_failure(monkeypatch):
    """The order create succeeds but a line-item POST returns 400. The function
    must report success=False and name the failed item so the operator knows the
    Register order is partial — never report a partial order as success."""
    from gemini_service import _send_to_clover, OrderItem

    async def fake_post(self, url, **kwargs):
        if url.endswith("/orders"):
            return _resp(201, json={"id": "clv_partial"})
        if url.endswith("/line_items"):
            return _resp(400, text="line item rejected")
        return _resp(201, json={"id": "x"})  # print_event

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = _make_order(items=[
        OrderItem(name="Samosa", menu_item_id="s1", category="Starters",
                  unit_price=500, quantity=1),
    ])
    out = await _send_to_clover(order, {"clover_api_token": "t", "clover_merchant_id": "m"})
    assert out["success"] is False
    assert out["order_id"] == "clv_partial"
    assert out["printed"] is False
    assert "Samosa" in out["error"]
