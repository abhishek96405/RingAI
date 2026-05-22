"""Membership factory (links a user/org to a restaurant tenant)."""
from __future__ import annotations

import uuid
from typing import Any


def make_membership(**overrides: Any) -> dict:
    doc = {
        "id": overrides.pop("id", f"memb_{uuid.uuid4().hex[:12]}"),
        "user_id": overrides.pop("user_id", "user_default"),
        "org_id": overrides.pop("org_id", "org_default"),
        "restaurant_id": overrides.pop("restaurant_id", "rest_default"),
        "role": "owner",
        "active": True,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    doc.update(overrides)
    return doc
