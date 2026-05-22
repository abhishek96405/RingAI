"""Salon service item factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_service_item(**overrides: Any) -> dict:
    """Return a services document used by salon-type tenants."""
    doc = {
        "id": overrides.pop("id", f"svc_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "salon_default"),
        "name": "Haircut",
        "category": "Hair",
        "duration_minutes": 30,
        "price": 35.0,
        "active": True,
    }
    doc.update(overrides)
    return doc
