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


async def test_falls_back_when_toast_fails(monkeypatch):
    """When Toast fails, falls through to webhook or DB."""
    from gemini_service import send_order_to_kitchen

    monkeypatch.setattr("toast_integration.send_order_to_toast",
                        AsyncMock(return_value={"success": False, "order_id": "", "method": "toast"}))
    monkeypatch.delenv("KITCHEN_WEBHOOK_URL", raising=False)

    out = await send_order_to_kitchen(_make_order(), {"pos_type": "toast"})
    # Should fall through to DB-only fallback
    assert out["success"] is True
    assert out["method"] == "database"


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
