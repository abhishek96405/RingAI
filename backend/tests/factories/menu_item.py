"""Menu item factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_menu_item(**overrides: Any) -> dict:
    """Return a menu_items document for the given restaurant."""
    doc = {
        "id": overrides.pop("id", f"item_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "rest_default"),
        "name": "Margherita Pizza",
        "category": "Pizza",
        "description": "Tomato, mozzarella, basil.",
        "price": 14.99,
        "available": True,
        "tags": [],
        "modifiers": [],
        "aliases": [],
    }
    doc.update(overrides)
    return doc
