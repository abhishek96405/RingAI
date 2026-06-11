"""Notifications WebSocket authentication (A6-2).

`@app.websocket("/ws/notifications")` streams a tenant's live notifications
(calls / orders / appointments, which carry customer PII). Before this fix it
accepted any anonymous client that knew a restaurant_id. The handler now
requires a valid Clerk token AND a membership row tying that user to the
restaurant, and it rejects unauthenticated clients with close code 1008
*before* accepting the socket.

These tests drive the in-process FastAPI app via TestClient.websocket_connect.
``verify_clerk_token`` is patched on the ``server`` module (server.py binds it
at import time via ``from auth_helpers import verify_clerk_token``).

Part of Duuutah AI.
"""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from tests._constants import TENANT_A_ID, TENANT_A_USER_ID, TENANT_B_USER_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


_WS_PATH = "/ws/notifications"


@pytest.fixture
def patch_clerk_ws(monkeypatch):
    """Patch server.verify_clerk_token: 'valid_a' -> tenant A claims, else raise.

    The WS handler calls verify_clerk_token directly (not the get_current_user
    dependency), so dependency_overrides do not apply here.
    """
    import server

    async def _fake_verify(token: str):
        if token == "valid_a":
            return {"sub": TENANT_A_USER_ID}
        if token == "valid_b":
            return {"sub": TENANT_B_USER_ID}
        raise ValueError("invalid token")

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify, raising=True)
    return _fake_verify


async def _seed_membership(db, *, user_id=TENANT_A_USER_ID, restaurant_id=TENANT_A_ID):
    await db.memberships.insert_one(
        {
            "id": "membership_ws",
            "user_id": user_id,
            "restaurant_id": restaurant_id,
            "role": "owner",
            "business_type": "restaurant",
        }
    )


def test_ws_rejected_without_token(client):
    """No token at all → closed with 1008, never accepted."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{_WS_PATH}?restaurant_id={TENANT_A_ID}"
        ) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_ws_rejected_without_restaurant_id(client, patch_clerk_ws):
    """Token but no restaurant_id → closed with 1008."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"{_WS_PATH}?token=valid_a") as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_ws_rejected_with_invalid_token(client, patch_clerk_ws):
    """A token that fails Clerk verification → closed with 1008."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{_WS_PATH}?restaurant_id={TENANT_A_ID}&token=garbage"
        ) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


async def test_ws_rejected_when_not_a_member(
    client, patched_server_db, patch_clerk_ws
):
    """Valid token but no membership for that tenant → closed with 1008.

    (No membership row is seeded for tenant A here.)
    """
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{_WS_PATH}?restaurant_id={TENANT_A_ID}&token=valid_a"
        ) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


async def test_ws_rejected_for_other_tenant_membership(
    client, patched_server_db, patch_clerk_ws
):
    """A valid user of tenant B cannot subscribe to tenant A's stream."""
    await _seed_membership(
        patched_server_db, user_id=TENANT_B_USER_ID, restaurant_id="tenant_b_restaurant"
    )
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{_WS_PATH}?restaurant_id={TENANT_A_ID}&token=valid_b"
        ) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


async def test_ws_accepted_with_valid_token_and_membership(
    client, patched_server_db, patch_clerk_ws
):
    """Valid token + existing membership → socket is accepted and greets us."""
    await _seed_membership(patched_server_db)
    with client.websocket_connect(
        f"{_WS_PATH}?restaurant_id={TENANT_A_ID}&token=valid_a"
    ) as ws:
        greeting = ws.receive_json()
        assert greeting["type"] == "connected"
        assert greeting["restaurant_id"] == TENANT_A_ID
