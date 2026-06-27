"""compute_order_total cart is retained and used to rebuild the order when
post-call extraction fails (deterministic, no-model-call recovery)."""
from __future__ import annotations

import pytest

from call_pipeline import CallSession

pytestmark = pytest.mark.unit

_MENU = [
    {"id": "i1", "name": "Samosa", "price": 500, "category": "Appetizers", "available": True},
    {"id": "i2", "name": "Chicken Biryani", "price": 1299, "category": "Mains", "available": True},
]


def _session(menu_items=_MENU):
    return CallSession(
        call_sid="test-call",
        restaurant_id="rest-1",
        caller_number="+15555550123",
        restaurant={},
        config={},
        menu_items=menu_items,
    )


def test_rebuild_returns_none_when_no_cart_captured():
    session = _session()
    assert session._last_computed_cart is None
    assert session._rebuild_order_from_computed_cart() is None


def test_rebuild_reconstructs_pickup_order_with_correct_total():
    session = _session()
    session._last_computed_cart = [
        {"name": "Samosa", "quantity": 2, "modifiers": []},
        {"name": "Chicken Biryani", "quantity": 1, "modifiers": []},
    ]
    order = session._rebuild_order_from_computed_cart()
    assert order is not None
    assert order.order_type == "pickup"
    assert sorted((i.name, i.quantity) for i in order.items) == [
        ("Chicken Biryani", 1), ("Samosa", 2),
    ]
    # 2 * $5.00 + 1 * $12.99 = $22.99
    assert order.total == 2299


def test_rebuild_drops_items_not_on_menu():
    session = _session()
    session._last_computed_cart = [
        {"name": "Samosa", "quantity": 1, "modifiers": []},
        {"name": "Nonexistent Dish", "quantity": 1, "modifiers": []},
    ]
    order = session._rebuild_order_from_computed_cart()
    assert order is not None
    assert [i.name for i in order.items] == ["Samosa"]
    assert "Nonexistent Dish" in order.dropped_items


def test_rebuild_refuses_delivery_without_address():
    session = _session()
    session._detected_order_type = "delivery"
    session._last_computed_cart = [{"name": "Samosa", "quantity": 1, "modifiers": []}]
    # The cart has no address; a delivery order can't be safely rebuilt from items
    # alone, so it routes to manual handling instead.
    assert session._rebuild_order_from_computed_cart() is None
