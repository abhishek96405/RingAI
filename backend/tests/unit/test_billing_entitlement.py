"""PL-02: live-call billing entitlement gate (server.is_entitled_to_calls).

This is the authoritative, race-free decision that ends trial/cancelled service
at call time. The matrix below is the close-out gate for PL-02 — the worst
prior bug (calls answered for cancelled tenants) survived 1695 tests precisely
because nothing exercised this decision.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.unit


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


@pytest.mark.parametrize(
    "restaurant, expected",
    [
        ({"billing_status": "active"}, True),
        ({"billing_status": "ACTIVE"}, True),  # case-insensitive
        ({"billing_status": "trialing", "trial_ends_at": _future()}, True),
        ({"billing_status": "trialing", "trial_ends_at": _future().replace("+00:00", "Z")}, True),
        ({"billing_status": "trialing", "trial_ends_at": _past()}, False),
        ({"billing_status": "trialing"}, False),  # missing trial_ends_at → fail closed
        ({"billing_status": "trialing", "trial_ends_at": "not-a-date"}, False),  # unparsable → fail closed
        ({"billing_status": "past_due"}, True),  # grace: Stripe still retrying
        ({"billing_status": "unpaid"}, False),  # retries exhausted
        ({"billing_status": "canceled"}, False),
        ({"billing_status": "pending"}, False),
        ({"billing_status": "incomplete_expired"}, False),
        ({"billing_status": None}, False),
        ({}, False),  # missing entirely → fail closed
    ],
)
def test_is_entitled_to_calls_matrix(restaurant, expected):
    from server import is_entitled_to_calls

    assert is_entitled_to_calls(restaurant) is expected
