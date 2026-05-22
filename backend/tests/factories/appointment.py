"""Appointment factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_appointment(**overrides: Any) -> dict:
    doc = {
        "id": overrides.pop("id", f"appt_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "salon_default"),
        "customer_name": "Jane Doe",
        "customer_phone": "+15555550110",
        "service_id": "svc_default",
        "service_name": "Haircut",
        "start_time": "2026-06-01T14:00:00+00:00",
        "duration_minutes": 30,
        "status": "confirmed",
        "notes": "",
    }
    doc.update(overrides)
    return doc
