"""User factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_user(**overrides: Any) -> dict:
    doc = {
        "id": overrides.pop("id", f"user_{uuid.uuid4().hex[:12]}"),
        "clerk_user_id": f"user_{uuid.uuid4().hex[:12]}",
        "email": "owner@example.test",
        "role": "owner",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    doc.update(overrides)
    return doc
