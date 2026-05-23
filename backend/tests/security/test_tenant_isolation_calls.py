"""Tenant isolation for call-records and related collections.

Covers ``call_records``, ``active_calls``, ``flagged_calls``,
``customer_profiles``. Calls are the most sensitive non-PII data in the
platform — transcripts can contain credit-card numbers, addresses, and
personal info — so isolation here is critical.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# call_records list (scenario 2)
# ---------------------------------------------------------------------------


async def test_call_records_list_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.call_records.insert_many(
        [
            {
                "id": "call_a_1",
                "restaurant_id": TENANT_A_ID,
                "caller_number": "+15555550111",
                "transcript": "Tenant A transcript SECRET-A",
                "started_at": "2026-05-21T12:00:00+00:00",
            },
            {
                "id": "call_b_1",
                "restaurant_id": TENANT_B_ID,
                "caller_number": "+15555550112",
                "transcript": "Tenant B transcript SECRET-B",
                "started_at": "2026-05-21T13:00:00+00:00",
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    body = r_a.json()
    assert "SECRET-A" in r_a.text or any(
        "SECRET-A" in (c.get("transcript") or "") for c in body.get("calls", [])
    )
    assert "SECRET-B" not in r_a.text


# ---------------------------------------------------------------------------
# Single call read cross-tenant
# ---------------------------------------------------------------------------


async def test_get_call_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.call_records.insert_one(
        {
            "id": "call_secret",
            "restaurant_id": TENANT_A_ID,
            "caller_number": "+15555550199",
            "transcript": "ULTRA-SECRET-TRANSCRIPT",
            "started_at": "2026-05-21T12:00:00+00:00",
        }
    )
    r = client.get(
        "/api/calls/call_secret",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    assert "ULTRA-SECRET-TRANSCRIPT" not in r.text
    assert "+15555550199" not in r.text


# ---------------------------------------------------------------------------
# Analytics summary should NOT include other tenants' data.
# ---------------------------------------------------------------------------


async def test_analytics_summary_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.call_records.insert_many(
        [
            {
                "id": "ca",
                "restaurant_id": TENANT_A_ID,
                "started_at": "2026-05-20T12:00:00+00:00",
                "order_total": 10000,
                "duration_seconds_actual": 120,
            },
            {
                "id": "cb",
                "restaurant_id": TENANT_B_ID,
                "started_at": "2026-05-20T13:00:00+00:00",
                "order_total": 50000,
                "duration_seconds_actual": 180,
            },
        ]
    )
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/analytics/summary?days=30",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    body = r.json()
    # Tenant A's total revenue should not include the 50000 from B.
    revenue = body.get("total_revenue_cents") or body.get("total_revenue") or 0
    if isinstance(revenue, (int, float)):
        assert revenue < 50000, f"Tenant A summary includes Tenant B revenue: {revenue}"


# ---------------------------------------------------------------------------
# Re-analyse cross-tenant call is denied (scenario 4).
# ---------------------------------------------------------------------------


async def test_reanalyse_call_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.call_records.insert_one(
        {
            "id": "call_re_target",
            "restaurant_id": TENANT_A_ID,
            "caller_number": "+15555550199",
            "transcript": [{"role": "user", "text": "private"}],
        }
    )
    r = client.post(
        "/api/calls/call_re_target/analyse",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Unauthenticated routes return 401 across calls surface.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/restaurants/{rid}/calls",
        "/api/restaurants/{rid}/analytics/summary",
        "/api/restaurants/{rid}/analytics/export?format=csv",
    ],
)
async def test_call_routes_unauth_returns_401(
    client, two_tenant_with_memberships, path
):
    r = client.get(path.format(rid=TENANT_A_ID))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# customer_profiles isolation — they're embedded but should never leak
# through cross-resource paths.
# ---------------------------------------------------------------------------


async def test_customer_profile_does_not_leak_via_cross_tenant_call_id(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.customer_profiles.insert_one(
        {
            "id": "cust_a_profile",
            "restaurant_id": TENANT_A_ID,
            "name": "PrivateName",
            "phone": "+15555550199",
            "notes": "VIP-NOTES-DO-NOT-LEAK",
        }
    )
    await patched_server_db.call_records.insert_one(
        {
            "id": "call_with_cust",
            "restaurant_id": TENANT_A_ID,
            "customer_id": "cust_a_profile",
            "caller_number": "+15555550199",
        }
    )
    r = client.get(
        "/api/calls/call_with_cust",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert "PrivateName" not in r.text
    assert "VIP-NOTES-DO-NOT-LEAK" not in r.text


# ---------------------------------------------------------------------------
# flagged_calls / learning surface — Tenant B should never see Tenant A's
# flagged review queue.
# ---------------------------------------------------------------------------


async def test_flagged_calls_list_scopes_by_tenant(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.flagged_calls.insert_many(
        [
            {
                "id": "flag_a_1",
                "restaurant_id": TENANT_A_ID,
                "call_id": "call_a_1",
                "reason": "low_quality",
                "transcript_snippet": "FlagSnippet-A",
            },
            {
                "id": "flag_b_1",
                "restaurant_id": TENANT_B_ID,
                "call_id": "call_b_1",
                "reason": "low_quality",
                "transcript_snippet": "FlagSnippet-B",
            },
        ]
    )
    r_a = client.get(
        f"/api/restaurants/{TENANT_A_ID}/learning/flagged-calls",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r_a.status_code == 200
    assert "FlagSnippet-B" not in r_a.text


# ---------------------------------------------------------------------------
# Review-flagged endpoint must not allow tenant B to clear a flag from A.
# ---------------------------------------------------------------------------


async def test_review_flagged_call_cross_tenant_is_denied(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.flagged_calls.insert_one(
        {
            "id": "flag_lock",
            "restaurant_id": TENANT_A_ID,
            "call_id": "call_a_1",
            "reason": "low_quality",
            "reviewed": False,
        }
    )
    r = client.post(
        "/api/learning/flagged-calls/call_a_1/review",
        json={"action": "approved", "notes": "ok"},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)
    rec = await patched_server_db.flagged_calls.find_one({"id": "flag_lock"})
    assert rec["reviewed"] is False
