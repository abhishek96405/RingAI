"""Integration tests — call records, auto-learning, analytics."""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID, ADMIN_USER_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# GET /api/restaurants/{id}/calls
# ---------------------------------------------------------------------------


async def test_list_calls_empty(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["calls"] == []
    assert body["total"] == 0


async def test_list_calls_paginated_and_filtered(
    client, two_tenant_with_memberships, patched_server_db
):
    base = "2026-05-01T10:00:00"
    for i in range(15):
        await patched_server_db.call_records.insert_one(
            {
                "id": f"c{i}",
                "restaurant_id": TENANT_A_ID,
                "call_sid": f"CA{i:032d}",
                "caller_number": f"+1555550{i:04d}",
                "started_at": f"2026-05-0{(i % 9) + 1}T10:00:00",
                "status": "COMPLETED" if i % 2 == 0 else "ESCALATED",
            }
        )

    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls?status=ESCALATED&limit=5",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert body["total"] == 7
    assert all(c["status"] == "ESCALATED" for c in body["calls"])
    assert len(body["calls"]) <= 5


async def test_list_calls_search_by_caller_number(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.call_records.insert_many(
        [
            {
                "id": "c1",
                "restaurant_id": TENANT_A_ID,
                "call_sid": "CA1",
                "caller_number": "+15555550100",
                "started_at": "2026-05-01T10:00",
                "status": "COMPLETED",
            },
            {
                "id": "c2",
                "restaurant_id": TENANT_A_ID,
                "call_sid": "CA2",
                "caller_number": "+15555550200",
                "started_at": "2026-05-01T11:00",
                "status": "COMPLETED",
            },
        ]
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls?search=0100",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert body["total"] == 1
    assert body["calls"][0]["caller_number"] == "+15555550100"


async def test_list_calls_date_range_filter(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.call_records.insert_many(
        [
            {
                "id": "c1",
                "restaurant_id": TENANT_A_ID,
                "call_sid": "CA1",
                "caller_number": "+1",
                "started_at": "2026-05-01T10:00",
                "status": "COMPLETED",
            },
            {
                "id": "c2",
                "restaurant_id": TENANT_A_ID,
                "call_sid": "CA2",
                "caller_number": "+1",
                "started_at": "2026-05-15T10:00",
                "status": "COMPLETED",
            },
        ]
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls?date_from=2026-05-10&date_to=2026-05-20",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.json()["total"] == 1


def test_list_calls_requires_auth(client):
    assert client.get(f"/api/restaurants/{TENANT_A_ID}/calls").status_code == 401


async def test_list_calls_wrong_tenant_404(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 404


def test_list_calls_invalid_limit_422(client, mock_clerk):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calls?limit=200",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/calls/{id}
# ---------------------------------------------------------------------------


async def test_get_call(client, two_tenant_with_memberships, patched_server_db):
    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA1",
            "caller_number": "+1",
            "started_at": "2026-05-01T10:00",
            "status": "COMPLETED",
        }
    )
    response = client.get("/api/calls/c1", headers={"Authorization": "Bearer tenant_a"})
    assert response.status_code == 200
    assert response.json()["id"] == "c1"


def test_get_call_missing_404(client, mock_clerk):
    response = client.get(
        "/api/calls/nope", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/calls/{id}/analyse (re-analyse)
# ---------------------------------------------------------------------------


async def test_reanalyse_call(
    client, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """Replace analyse_call_transcript with a deterministic stub so the route
    does not invoke Gemini."""

    async def _fake_analyse(transcript, order_json, menu_items):
        return {"quality_score": 92, "summary": "test"}

    import server

    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA1",
            "caller_number": "+1",
            "started_at": "2026-05-01T10:00",
            "status": "COMPLETED",
            "transcript": [],
        }
    )
    response = client.post(
        "/api/calls/c1/analyse",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["quality_score"] == 92


def test_reanalyse_call_missing_404(client, mock_clerk):
    response = client.post(
        "/api/calls/nope/analyse",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Analytics summary
# ---------------------------------------------------------------------------


async def test_analytics_summary_empty(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/analytics/summary",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_calls"] == 0
    assert body["calls_today"] == 0
    assert body["top_items"] == []


async def test_analytics_summary_with_data(
    client, two_tenant_with_memberships, patched_server_db
):
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).isoformat()
    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA1",
            "caller_number": "+15555550100",
            "caller_name": "X",
            "started_at": today,
            "ended_at": today,
            "duration_seconds": 120,
            "status": "COMPLETED",
            "contained_by_ai": True,
            "quality_score": 90,
            "order_total": 2500,
            "order_json": {"items": [{"name": "Pizza", "quantity": 2}], "total": 2500},
        }
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/analytics/summary",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert body["total_calls"] == 1
    assert body["completed_calls"] == 1
    assert body["total_revenue"] == 2500
    assert body["top_items"][0]["name"] == "Pizza"


async def test_analytics_export_csv(
    client, two_tenant_with_memberships, patched_server_db
):
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).isoformat()
    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA1",
            "caller_number": "+15555550100",
            "caller_name": "X",
            "started_at": today,
            "duration_seconds": 120,
            "status": "COMPLETED",
            "quality_score": 90,
            "order_total": 2500,
        }
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/analytics/export",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    # CSV body should include header row
    assert "Date,Caller,Status" in response.text


# ---------------------------------------------------------------------------
# Auto-learning routes
# ---------------------------------------------------------------------------


async def test_learning_stats_starter_plan_returns_zeros(
    client, two_tenant_with_memberships
):
    """STARTER plan callers see a zeroed stats block (auto-learning is PRO-only)."""
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/learning/stats",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "total_calls_processed": 0,
        "aliases_learned": 0,
        "calls_flagged": 0,
        "last_processed_at": None,
    }


async def test_learning_stats_pro_plan_invokes_service(
    client, pro_plan_tenant_a, patched_server_db
):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/learning/stats",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    # Pro plan goes through AutoLearningService which queries db.flagged_calls,
    # db.menu_aliases etc. Empty DB → zeros, but keys come from the service.
    assert "total_calls_processed" in body


async def test_learning_flagged_calls_starter_plan(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/learning/flagged-calls",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["flagged_calls"] == []
    assert body["count"] == 0


async def test_learning_aliases_starter_plan(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/learning/aliases",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json() == {"aliases": [], "count": 0}


async def test_learning_suggestions_starter_plan(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/learning/suggestions",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"menu_suggestions": [], "rule_suggestions": []}


async def test_review_flagged_call(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.flagged_calls.insert_one(
        {
            "call_id": "c1",
            "restaurant_id": TENANT_A_ID,
            "reviewed": False,
        }
    )
    response = client.post(
        "/api/learning/flagged-calls/c1/review",
        headers={"Authorization": "Bearer tenant_a"},
        json={"action": "correct", "notes": "ok"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "correct"


def test_review_flagged_missing_404(client, mock_clerk):
    response = client.post(
        "/api/learning/flagged-calls/nope/review",
        headers={"Authorization": "Bearer tenant_a"},
        json={"action": "correct"},
    )
    assert response.status_code == 404


async def test_apply_alias_to_menu_item(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Coca-Cola",
            "category": "Drinks",
            "price": 300,
            "aliases": [],
        }
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/learning/apply-alias"
        f"?alias=coke&target=Coca-Cola",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_apply_alias_to_global_when_item_missing(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/learning/apply-alias"
        f"?alias=foo&target=NonExistentItem",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    saved = await patched_server_db.menu_aliases.find_one(
        {"restaurant_id": TENANT_A_ID, "alias": "foo"}
    )
    assert saved["target"] == "NonExistentItem"


def test_apply_alias_missing_query_422(client, mock_clerk):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/learning/apply-alias",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/admin/cost-analytics  (admin only)
# ---------------------------------------------------------------------------


def test_cost_analytics_requires_auth(client):
    assert client.get("/api/admin/cost-analytics").status_code == 401


def test_cost_analytics_rejects_non_admin(client, mock_clerk):
    response = client.get(
        "/api/admin/cost-analytics",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 403


def test_cost_analytics_admin_returns_rollup(client, mock_clerk):
    response = client.get(
        "/api/admin/cost-analytics?days=7",
        headers={"Authorization": "Bearer admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "overall" in body
    assert "per_restaurant" in body
    assert body["period_days"] == 7
