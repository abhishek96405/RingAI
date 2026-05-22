"""Restaurant reservation factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_reservation(**overrides: Any) -> dict:
    doc = {
        "id": overrides.pop("id", f"resv_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "rest_default"),
        "customer_name": "John Smith",
        "customer_phone": "+15555550111",
        "party_size": 4,
        "reservation_time": "2026-06-15T19:00:00+00:00",
        "status": "pending",
        "notes": "",
    }
    doc.update(overrides)
    return doc
