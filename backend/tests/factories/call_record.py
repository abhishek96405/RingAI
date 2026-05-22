"""Call record factory."""
from __future__ import annotations

import uuid
from typing import Any


def make_call_record(**overrides: Any) -> dict:
    """Return a call_records document. Note: post-call extraction is the
    source of truth for cart/totals — do not seed mid-call partial state in
    tests that assert order content."""
    doc = {
        "id": overrides.pop("id", f"call_{uuid.uuid4().hex[:12]}"),
        "restaurant_id": overrides.pop("restaurant_id", "rest_default"),
        "from_number": "+15555550120",
        "to_number": "+15555550100",
        "started_at": "2026-05-21T12:00:00+00:00",
        "ended_at": "2026-05-21T12:03:30+00:00",
        "duration_sec": 210,
        "transcript": "",
        "language": "en",
        "outcome": "completed",
        "extracted_order": None,
    }
    doc.update(overrides)
    return doc
