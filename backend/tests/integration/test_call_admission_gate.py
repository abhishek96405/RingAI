"""PL-02: the inbound-call path (_prefetch_call_session_data) must deny calls
for tenants without billing entitlement, and must NEVER deny a paying one.

These drive the real call-admission function (not a mock) — the whole point of
the PL-02 fix is that this path now reads billing state.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.integration

PHONE = "+15555559000"


async def _insert_restaurant(db, billing_status, *, trial_ends_at=None, is_active=True):
    doc = {
        "id": "rest_gate_1",
        "name": "Gate Diner",
        "business_type": "restaurant",
        "plan": "STARTER",
        "phone_number": PHONE,
        "is_active": is_active,
        "billing_status": billing_status,
        "language": "en",
        "timezone": "UTC",
    }
    if trial_ends_at is not None:
        doc["trial_ends_at"] = trial_ends_at
    await db.restaurants.insert_one(doc)


@pytest.mark.parametrize("status", ["canceled", "unpaid", "pending"])
async def test_gate_denies_non_entitled(patched_server_db, status):
    import server

    await _insert_restaurant(patched_server_db, status)
    result = await server._prefetch_call_session_data(
        called_number=PHONE, caller_number="+15555550111", call_sid="cs_gate_deny",
    )
    assert result is None


async def test_gate_denies_expired_trial(patched_server_db):
    import server

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await _insert_restaurant(patched_server_db, "trialing", trial_ends_at=past)
    result = await server._prefetch_call_session_data(
        called_number=PHONE, caller_number="+15555550111", call_sid="cs_gate_trial",
    )
    assert result is None


async def test_gate_denies_when_not_provisioned(patched_server_db):
    """is_active gate still applies even when billing is active."""
    import server

    await _insert_restaurant(patched_server_db, "active", is_active=False)
    result = await server._prefetch_call_session_data(
        called_number=PHONE, caller_number="+15555550111", call_sid="cs_gate_prov",
    )
    assert result is None


async def test_gate_allows_active_paying_customer(patched_server_db):
    import server

    await _insert_restaurant(patched_server_db, "active")
    result = await server._prefetch_call_session_data(
        called_number=PHONE, caller_number="+15555550111", call_sid="cs_gate_active",
    )
    assert result is not None
    assert result["restaurant_id"] == "rest_gate_1"


async def test_gate_allows_trialing_within_window(patched_server_db):
    import server

    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    await _insert_restaurant(patched_server_db, "trialing", trial_ends_at=future)
    result = await server._prefetch_call_session_data(
        called_number=PHONE, caller_number="+15555550111", call_sid="cs_gate_trialok",
    )
    assert result is not None


async def test_gate_allows_past_due_grace(patched_server_db):
    """past_due = Stripe still retrying within the 2-week window → service stays on."""
    import server

    await _insert_restaurant(patched_server_db, "past_due")
    result = await server._prefetch_call_session_data(
        called_number=PHONE, caller_number="+15555550111", call_sid="cs_gate_pastdue",
    )
    assert result is not None
