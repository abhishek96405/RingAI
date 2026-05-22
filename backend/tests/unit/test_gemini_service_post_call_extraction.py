"""
Unit tests for backend/gemini_service.py — post-call extraction.

This file is the SOURCE OF TRUTH for cart/order totals and item resolution.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# MenuIndex.find — name, alias, fuzzy resolution
# ---------------------------------------------------------------------------

MENU = [
    {
        "id": "m1",
        "name": "Chicken Biryani",
        "category": "Mains",
        "price": 1299,
        "available": True,
        "allergens": [],
        "aliases": ["biryani", "chkn biryani"],
    },
    {
        "id": "m2",
        "name": "Veg Samosa",
        "category": "Starters",
        "price": 499,
        "available": True,
        "allergens": [],
    },
    {
        "id": "m3",
        "name": "Mango Lassi",
        "category": "Drinks",
        "price": 399,
        "available": True,
        "allergens": ["dairy"],
    },
    {
        "id": "m4",
        "name": "Out of Stock Item",
        "category": "Mains",
        "price": 100,
        "available": False,
    },
]


def test_menu_index_exact_name():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    found = idx.find("Chicken Biryani")
    assert found["id"] == "m1"


def test_menu_index_case_insensitive():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    found = idx.find("chicken biryani")
    assert found["id"] == "m1"


def test_menu_index_alias_lookup():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    found = idx.find("biryani")
    assert found["id"] == "m1"


def test_menu_index_alias_chkn_briyani_typo():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    found = idx.find("chkn biryani")
    assert found["id"] == "m1"


def test_menu_index_partial_name_match():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    found = idx.find("Veg")  # partial of "Veg Samosa"
    assert found is not None
    assert found["id"] == "m2"


def test_menu_index_unavailable_item_not_found():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    assert idx.find("Out of Stock Item") is None


def test_menu_index_returns_none_for_unrelated():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    assert idx.find("Spaghetti Carbonara") is None


def test_menu_index_word_index_fuzzy_match():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    # Fuzzy "Lassi" → Mango Lassi
    found = idx.find("Lassi Mango")
    assert found is not None
    assert found["id"] == "m3"


def test_menu_index_as_prompt_text_includes_categories():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    out = idx.as_prompt_text()
    assert "STARTERS" in out.upper() or "Starters".upper() in out.upper()
    assert "Chicken Biryani" in out


def test_menu_index_category_names_sorted_and_unique():
    from gemini_service import MenuIndex
    idx = MenuIndex(MENU)
    cats = idx.category_names()
    assert cats == sorted(cats)
    assert len(cats) == len(set(cats))


# ---------------------------------------------------------------------------
# OrderItem / LiveOrder
# ---------------------------------------------------------------------------

def test_order_item_subtotal():
    from gemini_service import OrderItem
    item = OrderItem(
        name="Pizza", menu_item_id="p1", category="Pizza",
        unit_price=1500, quantity=3,
    )
    assert item.subtotal == 4500


def test_order_item_to_dict_includes_all_fields():
    from gemini_service import OrderItem
    item = OrderItem(
        name="Pizza", menu_item_id="p1", category="Pizza",
        unit_price=1500, quantity=2,
        modifiers=["large"], special_instructions="no onions",
        allergens=["gluten"],
    )
    d = item.to_dict()
    assert d["name"] == "Pizza"
    assert d["quantity"] == 2
    assert d["subtotal"] == 3000


def test_live_order_total_sums_items():
    from gemini_service import LiveOrder, OrderItem
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    order.items.append(OrderItem(name="A", menu_item_id="a", category="x",
                                 unit_price=1000, quantity=2))
    order.items.append(OrderItem(name="B", menu_item_id="b", category="y",
                                 unit_price=500, quantity=1))
    assert order.total == 2500


def test_live_order_transition_records_history():
    from gemini_service import LiveOrder, OrderState
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    order.transition(OrderState.TAKING_ORDER, reason="customer requested order")
    order.transition(OrderState.CONFIRMED, reason="readback accepted")
    assert order.state == OrderState.CONFIRMED
    assert len(order.state_history) == 2
    assert order.state_history[0]["to"] == OrderState.TAKING_ORDER


# ---------------------------------------------------------------------------
# format_order_readback
# ---------------------------------------------------------------------------

def test_readback_empty_order():
    from gemini_service import LiveOrder, format_order_readback
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    out = format_order_readback(order)
    assert "no items" in out.lower() or "any items" in out.lower()


def test_readback_includes_items_and_total():
    from gemini_service import LiveOrder, OrderItem, format_order_readback
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    order.items.append(OrderItem(
        name="Cheese Pizza", menu_item_id="p1", category="Pizza",
        unit_price=1299, quantity=2,
    ))
    out = format_order_readback(order)
    assert "Cheese Pizza" in out
    assert "$25.98" in out  # 2x $12.99
    assert "2x" in out


def test_readback_includes_modifiers():
    from gemini_service import LiveOrder, OrderItem, format_order_readback
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    order.items.append(OrderItem(
        name="Pizza", menu_item_id="p1", category="Pizza",
        unit_price=1299, quantity=1,
        modifiers=["Large", "Thin Crust"],
    ))
    out = format_order_readback(order)
    assert "Large" in out and "Thin Crust" in out


def test_readback_delivery_phrasing():
    from gemini_service import LiveOrder, OrderItem, format_order_readback
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1",
                     order_type="delivery")
    order.items.append(OrderItem(name="Pizza", menu_item_id="p1", category="x",
                                 unit_price=1299, quantity=1))
    out = format_order_readback(order)
    assert "delivery" in out.lower()


# ---------------------------------------------------------------------------
# extract_order_from_transcript — end-to-end with mocked Gemini
# ---------------------------------------------------------------------------

def _mock_openai_completion(content):
    """Create a fake OpenAI response chain."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _patch_gemini_response(monkeypatch, content):
    """Patch _get_client to return a fake client returning ``content``."""
    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _mock_openai_completion(content)
    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)


async def test_extract_order_returns_none_when_client_unavailable(monkeypatch):
    from gemini_service import MenuIndex, extract_order_from_transcript
    monkeypatch.setattr("gemini_service._get_client", lambda: None)

    idx = MenuIndex(MENU)
    result = await extract_order_from_transcript(
        transcript=[{"role": "customer", "text": "one biryani please"}],
        menu_index=idx,
    )
    assert result is None


async def test_extract_simple_order(monkeypatch):
    """One biryani → LiveOrder with 1 item."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, json.dumps({
        "order_confirmed": True,
        "items": [{"name": "Chicken Biryani", "quantity": 1, "modifiers": [], "special_instructions": ""}],
        "order_type": "pickup",
        "customer_name": "Joe",
        "delivery_address": "",
        "special_instructions": "",
    }))

    idx = MenuIndex(MENU)
    order = await extract_order_from_transcript(
        transcript=[
            {"role": "customer", "text": "one biryani please"},
            {"role": "ai", "text": "Your order is confirmed!"},
        ],
        menu_index=idx,
    )
    assert order is not None
    assert order.customer_name == "Joe"
    assert len(order.items) == 1
    assert order.items[0].name == "Chicken Biryani"
    assert order.total == 1299


async def test_extract_multi_item_order_with_modifiers(monkeypatch):
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, json.dumps({
        "order_confirmed": True,
        "items": [
            {"name": "Chicken Biryani", "quantity": 2, "modifiers": ["spicy"], "special_instructions": ""},
            {"name": "Veg Samosa", "quantity": 4, "modifiers": [], "special_instructions": "no chutney"},
            {"name": "Mango Lassi", "quantity": 1, "modifiers": [], "special_instructions": ""},
        ],
        "order_type": "pickup",
        "customer_name": "Joe",
    }))

    idx = MenuIndex(MENU)
    order = await extract_order_from_transcript(
        transcript=[{"role": "ai", "text": "Your order is confirmed!"}],
        menu_index=idx,
    )
    assert len(order.items) == 3
    # Total: 2x1299 + 4x499 + 1x399 = 2598 + 1996 + 399 = 4993
    assert order.total == 4993


async def test_extract_returns_none_when_confirmed_false(monkeypatch):
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, json.dumps({"order_confirmed": False}))

    idx = MenuIndex(MENU)
    result = await extract_order_from_transcript(
        transcript=[{"role": "customer", "text": "Maybe later"}],
        menu_index=idx,
    )
    assert result is None


async def test_extract_skips_off_menu_items(monkeypatch):
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, json.dumps({
        "order_confirmed": True,
        "items": [
            {"name": "Chicken Biryani", "quantity": 1, "modifiers": [], "special_instructions": ""},
            {"name": "Spaghetti Carbonara", "quantity": 1, "modifiers": [], "special_instructions": ""},
        ],
        "order_type": "pickup",
        "customer_name": "Joe",
    }))

    idx = MenuIndex(MENU)
    order = await extract_order_from_transcript(
        transcript=[{"role": "ai", "text": "Your order is confirmed!"}],
        menu_index=idx,
    )
    assert len(order.items) == 1  # only the valid one
    assert order.items[0].name == "Chicken Biryani"


async def test_extract_returns_none_when_no_valid_items(monkeypatch):
    """An "order_confirmed" with zero valid items → None."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, json.dumps({
        "order_confirmed": True,
        "items": [{"name": "Off Menu", "quantity": 1}],
    }))

    idx = MenuIndex(MENU)
    result = await extract_order_from_transcript(
        transcript=[{"role": "ai", "text": "Your order is confirmed!"}],
        menu_index=idx,
    )
    assert result is None


async def test_extract_respects_order_type_override(monkeypatch):
    """When detected_order_type is passed, it overrides what Gemini returns."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, json.dumps({
        "order_confirmed": True,
        "items": [{"name": "Chicken Biryani", "quantity": 1}],
        "order_type": "delivery",
        "customer_name": "Joe",
    }))

    idx = MenuIndex(MENU)
    order = await extract_order_from_transcript(
        transcript=[{"role": "ai", "text": "Your order is confirmed!"}],
        menu_index=idx,
        detected_order_type="delivery",
    )
    assert order.order_type == "delivery"


async def test_extract_handles_malformed_gemini_response(monkeypatch):
    from gemini_service import MenuIndex, extract_order_from_transcript

    _patch_gemini_response(monkeypatch, "this is not json at all")

    idx = MenuIndex(MENU)
    result = await extract_order_from_transcript(
        transcript=[{"role": "ai", "text": "Your order is confirmed!"}],
        menu_index=idx,
    )
    assert result is None


# ---------------------------------------------------------------------------
# detect_call_signals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,signal", [
    ("ORDER_CONFIRMED — see you soon", "order_confirmed"),
    ("Your order is confirmed!", "order_confirmed"),
    ("Order has been confirmed", "order_confirmed"),
    ("Your order is placed", "order_confirmed"),
    ("ESCALATE_TO_HUMAN now", "escalate_to_human"),
    ("Thank you for calling", "call_ending"),
    ("Goodbye!", "call_ending"),
    ("Take care", "call_ending"),
    ("Have a great day", "call_ending"),
])
def test_detect_call_signals_positive(text, signal):
    from gemini_service import detect_call_signals
    result = detect_call_signals(text)
    assert result[signal] is True


def test_detect_call_signals_returns_all_false_for_neutral_text():
    from gemini_service import detect_call_signals
    result = detect_call_signals("just chatting")
    assert all(v is False for v in result.values())
