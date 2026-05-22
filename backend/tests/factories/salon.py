"""Salon factory."""
from __future__ import annotations

import uuid
from typing import Any

from faker import Faker

_faker = Faker()
Faker.seed(1)


def make_salon(**overrides: Any) -> dict:
    """Return a minimal salon document. Salon-keyed collections share the
    ``restaurant_id`` tenant key for legacy reasons."""
    doc = {
        "id": overrides.pop("id", f"salon_{uuid.uuid4().hex[:12]}"),
        "name": _faker.last_name() + " Beauty Studio",
        "business_type": "salon",
        "owner_user_id": f"user_{uuid.uuid4().hex[:12]}",
        "org_id": f"org_{uuid.uuid4().hex[:12]}",
        "phone": "+15555550101",
        "timezone": "America/Chicago",
        "plan": "PRO",
        "is_active": True,
    }
    doc.update(overrides)
    return doc
