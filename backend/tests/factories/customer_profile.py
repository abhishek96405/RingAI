"""Customer profile factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_customer_profile(**overrides: Any) -> dict:
    doc = {
        "id": overrides.pop("id", f"cust_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "rest_default"),
        "phone": "+15555550120",
        "name": "Returning Customer",
        "visit_count": 3,
        "last_seen": "2026-05-20T19:00:00+00:00",
        "preferences": {},
        "tags": [],
    }
    doc.update(overrides)
    return doc
