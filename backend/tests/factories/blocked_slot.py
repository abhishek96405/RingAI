"""Blocked slot factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_blocked_slot(**overrides: Any) -> dict:
    doc = {
        "id": overrides.pop("id", f"block_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "salon_default"),
        "start_time": "2026-06-01T18:00:00+00:00",
        "end_time": "2026-06-01T19:00:00+00:00",
        "reason": "staff break",
    }
    doc.update(overrides)
    return doc
