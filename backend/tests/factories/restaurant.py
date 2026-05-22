"""Restaurant factory."""
from __future__ import annotations

import uuid
from typing import Any

from faker import Faker

_faker = Faker()
Faker.seed(0)


def make_restaurant(**overrides: Any) -> dict:
    """Return a minimal restaurant document matching the production shape."""
    doc = {
        "id": overrides.pop("id", f"rest_{uuid.uuid4().hex[:12]}"),
        "name": _faker.company() + " Kitchen",
        "business_type": "restaurant",
        "owner_user_id": f"user_{uuid.uuid4().hex[:12]}",
        "org_id": f"org_{uuid.uuid4().hex[:12]}",
        "phone": "+15555550100",
        "address": _faker.address().replace("\n", ", "),
        "timezone": "America/Chicago",
        "plan": "STARTER",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    doc.update(overrides)
    return doc
