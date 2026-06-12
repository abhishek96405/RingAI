"""
PR-F / F1 — endpoint authz hardening (A6-1, A6-3, A6-4).

A6-1: POST /restaurants/{id}/send-menu-sms previously fetched membership but never
      enforced it. Now goes through ensure_restaurant_access (404 for non-members).
A6-3: GET /telnyx/numbers/order/{order_id} was authed but not tenant-scoped. Now
      scoped to the caller's membership on the order record's restaurant_id.
A6-4: GET /test-mode/status and /test-mode/scenarios were unauthenticated; now
      require a valid user.
"""
from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.integration


# --- A6-1: send-menu-sms enforces membership -------------------------------

async def test_send_menu_sms_blocks_non_member(client, two_tenant_with_memberships, monkeypatch):
    """tenant_a is not a member of TENANT_B_ID -> 404, and SMS is never sent."""
    import server

    called = {"n": 0}

    async def _never(*a, **k):
        called["n"] += 1
        return True

    monkeypatch.setattr(server, "send_menu_sms", _never)

    resp = client.post(
        f"/api/restaurants/{TENANT_B_ID}/send-menu-sms",
        headers={"Authorization": "Bearer tenant_a"},
        json={"caller_number": "+15551234567"},
    )
    assert resp.status_code == 404
    assert called["n"] == 0


async def test_send_menu_sms_allows_member(client, two_tenant_with_memberships, monkeypatch):
    """tenant_a IS a member of TENANT_A_ID -> proceeds and SMS fires."""
    import server

    sent = {"n": 0}

    async def _fake_send(*a, **k):
        sent["n"] += 1
        return True

    monkeypatch.setattr(server, "send_menu_sms", _fake_send)

    resp = client.post(
        f"/api/restaurants/{TENANT_A_ID}/send-menu-sms",
        headers={"Authorization": "Bearer tenant_a"},
        json={"caller_number": "+15551234567"},
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] is True
    assert sent["n"] == 1


# --- A6-3: telnyx order lookup scoped to caller's tenant -------------------

async def test_telnyx_get_order_blocks_cross_tenant(client, two_tenant_with_memberships, patched_server_db, monkeypatch):
    """An order owned by TENANT_B is not readable by tenant_a -> 404, Telnyx not called."""
    import telnyx_service

    await patched_server_db.phone_number_orders.insert_one(
        {"order_id": "ord_b_1", "restaurant_id": TENANT_B_ID, "status": "pending"}
    )

    called = {"n": 0}

    async def _never(*a, **k):
        called["n"] += 1
        return {"id": "ord_b_1"}

    monkeypatch.setattr(telnyx_service, "get_number_order", _never)

    resp = client.get(
        "/api/telnyx/numbers/order/ord_b_1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert resp.status_code == 404
    assert called["n"] == 0


async def test_telnyx_get_order_404_when_missing(client, two_tenant_with_memberships, monkeypatch):
    """Unknown order_id -> 404 before any Telnyx call."""
    import telnyx_service

    async def _never(*a, **k):
        raise AssertionError("Telnyx must not be called for a missing record")

    monkeypatch.setattr(telnyx_service, "get_number_order", _never)

    resp = client.get(
        "/api/telnyx/numbers/order/does_not_exist",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert resp.status_code == 404


async def test_telnyx_get_order_allows_owner(client, two_tenant_with_memberships, patched_server_db, monkeypatch):
    """tenant_a can read its OWN tenant's order record -> 200."""
    import telnyx_service

    await patched_server_db.phone_number_orders.insert_one(
        {"order_id": "ord_a_1", "restaurant_id": TENANT_A_ID, "status": "pending"}
    )

    async def _fake(order_id):
        return {"id": order_id, "status": "complete"}

    monkeypatch.setattr(telnyx_service, "get_number_order", _fake)

    resp = client.get(
        "/api/telnyx/numbers/order/ord_a_1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["telnyx"]["status"] == "complete"
    assert body["audit"]["restaurant_id"] == TENANT_A_ID


# --- A6-4: test-mode status/scenarios require auth ------------------------

async def test_test_mode_status_requires_auth(client, mock_clerk):
    assert client.get("/api/test-mode/status").status_code == 401
    ok = client.get("/api/test-mode/status", headers={"Authorization": "Bearer tenant_a"})
    assert ok.status_code == 200


async def test_test_mode_scenarios_requires_auth(client, mock_clerk):
    assert client.get("/api/test-mode/scenarios").status_code == 401
    ok = client.get("/api/test-mode/scenarios", headers={"Authorization": "Bearer tenant_a"})
    assert ok.status_code == 200
