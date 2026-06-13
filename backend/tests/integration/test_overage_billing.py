"""H4 (A5-1/A5-2): overage billing uses the authoritative post-increment call
count and an idempotency key, billed only for active subscriptions over limit."""
from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


async def test_overage_billed_on_authoritative_count_with_idempotency_key(
    patched_server_db, stripe_sdk_mock
):
    """A5-2: the decision uses the atomic post-inc DB count, not a stale dict.
    A5-1: the InvoiceItem carries idempotency_key=overage:{call_sid}."""
    from server import _record_call_for_billing
    await patched_server_db.restaurants.insert_one({
        "id": TENANT_A_ID,
        "monthly_call_count": 510,          # authoritative DB state (already over)
        "monthly_call_limit": 500,
        "billing_status": "active",
        "stripe_customer_id": "cus_over_1",
        "plan": "STARTER",
    })
    # The pre-fetched dict carries a STALE count — the A5-2 bug fed this in.
    stale = {
        "monthly_call_count": 5,
        "monthly_call_limit": 500,
        "billing_status": "active",
        "stripe_customer_id": "cus_over_1",
        "plan": "STARTER",
    }
    await _record_call_for_billing(stale, TENANT_A_ID, "call_over_1")
    rec = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert rec["monthly_call_count"] == 511                  # atomic inc on the real doc
    assert len(stripe_sdk_mock["invoiceitem_create"]) == 1   # 511>500 billed (stale 6 would NOT)
    assert stripe_sdk_mock["invoiceitem_create"][0]["idempotency_key"] == "overage:call_over_1"


async def test_overage_not_billed_under_limit(patched_server_db, stripe_sdk_mock):
    from server import _record_call_for_billing
    await patched_server_db.restaurants.insert_one({
        "id": TENANT_A_ID, "monthly_call_count": 10, "monthly_call_limit": 500,
        "billing_status": "active", "stripe_customer_id": "cus_u", "plan": "STARTER",
    })
    rest = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    await _record_call_for_billing(rest, TENANT_A_ID, "call_u_1")
    rec = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert rec["monthly_call_count"] == 11
    assert len(stripe_sdk_mock["invoiceitem_create"]) == 0


async def test_overage_not_billed_during_trial(patched_server_db, stripe_sdk_mock):
    """billing_status gate unchanged: no overage charge during the free trial."""
    from server import _record_call_for_billing
    await patched_server_db.restaurants.insert_one({
        "id": TENANT_A_ID, "monthly_call_count": 600, "monthly_call_limit": 500,
        "billing_status": "trialing", "stripe_customer_id": "cus_t", "plan": "STARTER",
    })
    rest = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    await _record_call_for_billing(rest, TENANT_A_ID, "call_t_1")
    rec = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert rec["monthly_call_count"] == 601
    assert len(stripe_sdk_mock["invoiceitem_create"]) == 0
