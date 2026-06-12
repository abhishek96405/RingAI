"""Per-restaurant WebSocket connection cap (A4-1).

server.py wires rate_limiting's per-restaurant counter into /ws/notifications:
at most MAX_WS_PER_RESTAURANT live notification sockets per restaurant. A
connection over the cap is rejected at the handshake with close code 1013
(Try Again Later), BEFORE the socket is accepted. The media-stream (call-path)
WS is intentionally not capped.

These helpers are plain in-process counters (not slowapi/Redis), so unlike the
HTTP rate limiter they DO take effect under the test client.
"""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from tests._constants import TENANT_A_ID, TENANT_A_USER_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]

_WS_PATH = "/ws/notifications"


@pytest.fixture(autouse=True)
def _reset_ws_counter():
    """Keep the module-level connection counter isolated per test."""
    import rate_limiting

    rate_limiting._ws_connections.clear()
    yield
    rate_limiting._ws_connections.clear()


@pytest.fixture
def patch_clerk_ws(monkeypatch):
    """token 'valid_a' -> tenant A claims; anything else raises."""
    import server

    async def _fake_verify(token: str):
        if token == "valid_a":
            return {"sub": TENANT_A_USER_ID}
        raise ValueError("invalid token")

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify, raising=True)
    return _fake_verify


async def _seed_membership(db):
    await db.memberships.insert_one(
        {
            "id": "membership_ws_cap",
            "user_id": TENANT_A_USER_ID,
            "restaurant_id": TENANT_A_ID,
            "role": "owner",
            "business_type": "restaurant",
        }
    )


def test_ws_connection_helpers_increment_and_decrement():
    """Pure counter math: register up to the cap -> check fails; free one -> ok."""
    import rate_limiting

    rid = "rid_helpers"
    assert rate_limiting.check_ws_connection_limit(rid) is True
    for _ in range(rate_limiting.MAX_WS_PER_RESTAURANT):
        rate_limiting.register_ws_connection(rid)
    assert rate_limiting.check_ws_connection_limit(rid) is False
    rate_limiting.unregister_ws_connection(rid)
    assert rate_limiting.check_ws_connection_limit(rid) is True


async def test_ws_accepted_when_under_cap(client, patched_server_db, patch_clerk_ws):
    """A valid connection under the cap is accepted and counts as 1."""
    import rate_limiting

    await _seed_membership(patched_server_db)
    with client.websocket_connect(
        f"{_WS_PATH}?restaurant_id={TENANT_A_ID}&token=valid_a"
    ) as ws:
        greeting = ws.receive_json()
        assert greeting["type"] == "connected"
        # register_ws_connection runs before the greeting is sent
        assert rate_limiting.get_ws_connection_count(TENANT_A_ID) == 1


async def test_ws_rejected_when_at_cap(client, patched_server_db, patch_clerk_ws):
    """At capacity, an otherwise-valid connection is rejected with 1013."""
    import rate_limiting

    await _seed_membership(patched_server_db)
    # Simulate the restaurant already at capacity.
    rate_limiting._ws_connections[TENANT_A_ID] = rate_limiting.MAX_WS_PER_RESTAURANT

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"{_WS_PATH}?restaurant_id={TENANT_A_ID}&token=valid_a"
        ) as ws:
            ws.receive_text()
    assert exc.value.code == 1013
