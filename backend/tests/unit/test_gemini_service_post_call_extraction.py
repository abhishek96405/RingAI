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


# ---------------------------------------------------------------------------
# A7-9: partial match must be whole-word + unique — a raw substring hit
# ("water" in "watermelon juice") + first-dict-order match returned the wrong
# item. 0 or >1 candidates fall through (don't guess; let the AI re-ask).
# ---------------------------------------------------------------------------

_WATER_MENU = [
    {"id": "wj", "name": "Watermelon Juice", "category": "Drinks", "price": 500, "available": True},
    {"id": "sw", "name": "Sparkling Water", "category": "Drinks", "price": 300, "available": True},
]


def test_menu_index_substring_does_not_match_wrong_item():
    """find("water") must resolve to "Sparkling Water" (whole word), NOT
    "Watermelon Juice" (the old raw-substring bug)."""
    from gemini_service import MenuIndex
    idx = MenuIndex(_WATER_MENU)
    found = idx.find("water")
    assert found is not None
    assert found["id"] == "sw"


def test_menu_index_ambiguous_partial_match_falls_through_to_none():
    """A whole-word match with >1 candidate and no unique fuzzy resolution must
    return None rather than guessing the first dict-order item.

    (Note: a single *distinctive* >3-char word like "juice" is still resolved by
    the unchanged step-5 word-fuzzy fallback — that is desired. The guard here is
    for genuinely ambiguous tokens that the fuzzy step cannot disambiguate.)"""
    from gemini_service import MenuIndex
    idx = MenuIndex([
        {"id": "h", "name": "Hot Tea", "category": "Drinks", "price": 200, "available": True},
        {"id": "i", "name": "Ice Tea", "category": "Drinks", "price": 200, "available": True},
    ])
    assert idx.find("tea") is None


def test_menu_index_exact_name_still_wins_over_partial_logic():
    from gemini_service import MenuIndex
    idx = MenuIndex(_WATER_MENU)
    assert idx.find("Watermelon Juice")["id"] == "wj"


# ---------------------------------------------------------------------------
# A7-8: _head_tail keeps BOTH ends of a long transcript (the confirmed readback
# lives at the END, so head-only truncation drops it).
# ---------------------------------------------------------------------------

def test_head_tail_short_string_unchanged():
    from gemini_service import _head_tail
    s = "short transcript"
    assert _head_tail(s) == s


def test_head_tail_long_string_keeps_head_and_tail():
    from gemini_service import _head_tail
    head = "HEAD_MARKER " + ("a" * 2000)
    tail = ("b" * 3000) + " TAIL_CONFIRMED"
    text = head + tail
    out = _head_tail(text)
    assert len(text) > 4000
    assert "HEAD_MARKER" in out          # head preserved
    assert "TAIL_CONFIRMED" in out       # the end-of-call confirmation preserved
    assert "[middle of call omitted]" in out
    assert len(out) < len(text)


# ---------------------------------------------------------------------------
# A7-11: _safe_int — a non-numeric spoken quantity ("two") must not crash
# extraction; fall back to the default instead.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("two", 1),
    ("3", 3),
    (None, 1),
    (2, 2),
    ("", 1),
    (["bad"], 1),
])
def test_safe_int(value, expected):
    from gemini_service import _safe_int
    assert _safe_int(value, 1) == expected


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
# A7-6: resolve_modifier_deltas — chosen modifier names → total price_delta.
# Matches by option name AND ai_aliases, case-insensitive. Unmatched names add
# $0 but are returned so the caller can log them — never invent a price.
# ---------------------------------------------------------------------------

_MODIFIER_ITEM = {
    "id": "pizza",
    "name": "Pizza",
    "price": 1200,
    "resolved_modifiers": [
        {
            "name": "Size",
            "options": [
                {"name": "Small", "price_delta": 0},
                {"name": "Large", "price_delta": 300, "ai_aliases": ["big", "XL"]},
            ],
        },
        {
            "name": "Toppings",
            "options": [
                {"name": "Extra Cheese", "price_delta": 150},
                {"name": "Light Cheese", "price_delta": -100},
            ],
        },
    ],
}


def test_resolve_modifier_deltas_matches_by_option_name():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["Large"])
    assert total == 300
    assert unmatched == []


def test_resolve_modifier_deltas_matches_by_ai_alias():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["big"])
    assert total == 300
    assert unmatched == []


def test_resolve_modifier_deltas_case_insensitive():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["lArGe", "EXTRA cheese"])
    assert total == 450
    assert unmatched == []


def test_resolve_modifier_deltas_sums_multiple():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["Large", "Extra Cheese"])
    assert total == 450
    assert unmatched == []


def test_resolve_modifier_deltas_positive_delta():
    from gemini_service import resolve_modifier_deltas
    total, _ = resolve_modifier_deltas(_MODIFIER_ITEM, ["Extra Cheese"])
    assert total == 150


def test_resolve_modifier_deltas_negative_delta():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["Light Cheese"])
    assert total == -100
    assert unmatched == []


def test_resolve_modifier_deltas_unmatched_name_returns_zero_and_name():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["Gold Leaf"])
    assert total == 0
    assert unmatched == ["Gold Leaf"]


def test_resolve_modifier_deltas_mixed_matched_and_unmatched():
    from gemini_service import resolve_modifier_deltas
    total, unmatched = resolve_modifier_deltas(_MODIFIER_ITEM, ["Large", "Gold Leaf"])
    assert total == 300
    assert unmatched == ["Gold Leaf"]


def test_resolve_modifier_deltas_empty_list():
    from gemini_service import resolve_modifier_deltas
    assert resolve_modifier_deltas(_MODIFIER_ITEM, []) == (0, [])


# ---------------------------------------------------------------------------
# A7-6: OrderItem.subtotal folds in modifier_total (per-unit), floored at $0.
# ---------------------------------------------------------------------------

def test_order_item_subtotal_modifier_total_zero():
    from gemini_service import OrderItem
    item = OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                     unit_price=1200, quantity=2, modifier_total=0)
    assert item.subtotal == 2400


def test_order_item_subtotal_positive_modifier():
    from gemini_service import OrderItem
    item = OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                     unit_price=1200, quantity=2, modifier_total=300)
    # (1200 + 300) * 2
    assert item.subtotal == 3000


def test_order_item_subtotal_negative_modifier():
    from gemini_service import OrderItem
    item = OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                     unit_price=1200, quantity=1, modifier_total=-100)
    assert item.subtotal == 1100


def test_order_item_subtotal_floors_at_zero():
    """A modifier_total more negative than unit_price floors the per-unit
    effective price at 0 — a line can never cost less than nothing (A7-6)."""
    from gemini_service import OrderItem
    item = OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                     unit_price=500, quantity=3, modifier_total=-900)
    assert item.subtotal == 0


def test_order_item_subtotal_multiplies_by_quantity():
    from gemini_service import OrderItem
    item = OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                     unit_price=1000, quantity=4, modifier_total=250)
    assert item.subtotal == 5000


def test_live_order_total_includes_modifier_delta():
    """A 2-item order where one item carries a modifier_total → the order total
    includes the delta (A7-6)."""
    from gemini_service import LiveOrder, OrderItem
    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    order.items.append(OrderItem(name="Pizza", menu_item_id="p1", category="x",
                                 unit_price=1200, quantity=1, modifier_total=300))
    order.items.append(OrderItem(name="Soda", menu_item_id="s1", category="y",
                                 unit_price=200, quantity=2))
    # (1200 + 300) + (200 * 2) = 1500 + 400
    assert order.total == 1900


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

def _patch_gemini_response(monkeypatch, content):
    """Patch _get_client to return a native google-genai fake returning ``content``."""
    async def _gen(**kwargs):
        return SimpleNamespace(
            text=content,
            usage_metadata=SimpleNamespace(
                prompt_token_count=10, candidates_token_count=5, total_token_count=15),
        )
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))
    monkeypatch.setattr("gemini_service._get_client", lambda: fake)


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
