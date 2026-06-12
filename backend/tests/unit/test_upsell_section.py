"""
D3-11: the upsell suggestion is built from the restaurant's REAL menu, never a
hardcoded item. A non-Indian menu must never produce 'Mango Lassi'; an Indian menu
that actually lists it still may. The example phrasing always anchors on a real
on-menu item, and categorisation is whole-word (no 'tea' in 'steak' false match).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_upsell_section_non_indian_menu_uses_real_items_not_mango_lassi():
    from gemini_service import MenuIndex, _build_upsell_section
    menu = MenuIndex([
        {"id": "1", "name": "Margherita Pizza", "category": "Pizza", "price": 1200, "available": True},
        {"id": "2", "name": "Coca-Cola", "category": "Drinks", "price": 300, "available": True},
        {"id": "3", "name": "Tiramisu", "category": "Desserts", "price": 600, "available": True},
        {"id": "4", "name": "Garlic Bread", "category": "Sides", "price": 500, "available": True},
    ])
    section = _build_upsell_section(menu)
    assert "Mango Lassi" not in section
    assert "Gulab Jamun" not in section
    assert "Coca-Cola" in section
    assert "Tiramisu" in section
    assert "Garlic Bread" in section
    assert "A Coca-Cola would go great" in section


def test_upsell_section_indian_menu_still_allows_mango_lassi():
    from gemini_service import MenuIndex, _build_upsell_section
    menu = MenuIndex([
        {"id": "1", "name": "Chicken Biryani", "category": "Mains", "price": 1599, "available": True},
        {"id": "2", "name": "Mango Lassi", "category": "Beverages", "price": 599, "available": True},
        {"id": "3", "name": "Gulab Jamun", "category": "Desserts", "price": 499, "available": True},
    ])
    section = _build_upsell_section(menu)
    assert "Mango Lassi" in section
    assert "A Mango Lassi would go great" in section


def test_upsell_section_example_is_always_a_real_menu_item():
    from gemini_service import MenuIndex, _build_upsell_section
    menu = MenuIndex([
        {"id": "1", "name": "Cheeseburger", "category": "Burgers", "price": 900, "available": True},
        {"id": "2", "name": "Veggie Burger", "category": "Burgers", "price": 850, "available": True},
    ])
    section = _build_upsell_section(menu)
    assert "Mango Lassi" not in section
    assert ("Cheeseburger" in section) or ("Veggie Burger" in section)


def test_upsell_section_does_not_false_match_substrings():
    from gemini_service import MenuIndex, _build_upsell_section
    menu = MenuIndex([
        {"id": "1", "name": "Ribeye Steak", "category": "Grill", "price": 2500, "available": True},
        {"id": "2", "name": "House Lemonade", "category": "Drinks", "price": 400, "available": True},
    ])
    section = _build_upsell_section(menu)
    assert "House Lemonade" in section
    assert "A House Lemonade would go great" in section
