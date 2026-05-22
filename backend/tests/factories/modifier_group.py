"""Modifier group factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_modifier_group(**overrides: Any) -> dict:
    """Return a modifier_groups document."""
    doc = {
        "id": overrides.pop("id", f"mod_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "rest_default"),
        "name": "Crust",
        "min_select": 1,
        "max_select": 1,
        "required": True,
        "options": [
            {"name": "Thin", "price_delta": 0.0},
            {"name": "Thick", "price_delta": 1.0},
        ],
    }
    doc.update(overrides)
    return doc
