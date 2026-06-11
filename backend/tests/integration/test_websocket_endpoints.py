"""Integration tests — WebSocket endpoints.

Covers:
  ws /ws/notifications
  ws /api/telnyx/media-stream
"""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from tests._constants import TENANT_A_ID, TENANT_A_USER_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# /ws/notifications
#
# A6-2: the notifications socket now requires a valid Clerk token + a
# membership tying that user to the restaurant. ``authed_notifications`` patches
# verify_clerk_token (server.py binds it at import) and seeds the membership so
# the handshake / ping-pong assertions below exercise the post-auth path.
# Comprehensive auth-rejection coverage lives in
# tests/security/test_ws_notifications_auth.py.
# ---------------------------------------------------------------------------


@pytest.fixture
async def authed_notifications(monkeypatch, patched_server_db):
    import server

    async def _verify(token: str):
        if token == "good":
            return {"sub": TENANT_A_USER_ID}
        raise ValueError("bad token")

    monkeypatch.setattr(server, "verify_clerk_token", _verify, raising=True)
    await patched_server_db.memberships.insert_one(
        {
            "id": "membership_ws_endpoints",
            "user_id": TENANT_A_USER_ID,
            "restaurant_id": TENANT_A_ID,
            "role": "owner",
            "business_type": "restaurant",
        }
    )


def test_ws_notifications_requires_token(client):
    """Connect with no token → server rejects with close code 1008, no handshake."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws/notifications?restaurant_id={TENANT_A_ID}"
        ) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


async def test_ws_notifications_connect_with_restaurant_id(
    client, authed_notifications
):
    with client.websocket_connect(
        f"/ws/notifications?restaurant_id={TENANT_A_ID}&token=good"
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert msg["restaurant_id"] == TENANT_A_ID


async def test_ws_notifications_ping_pong(client, authed_notifications):
    """Sending 'ping' must receive 'pong' back."""
    with client.websocket_connect(
        f"/ws/notifications?restaurant_id={TENANT_A_ID}&token=good"
    ) as ws:
        ws.receive_json()  # discard handshake
        ws.send_text("ping")
        reply = ws.receive_text()
        assert reply == "pong"


# ---------------------------------------------------------------------------
# /api/telnyx/media-stream
# ---------------------------------------------------------------------------


def test_telnyx_media_stream_without_active_call_closes(client):
    """Sending a Telnyx-style start frame without a pre-populated db.active_calls
    row must cause the server to close the WebSocket."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/telnyx/media-stream") as ws:
            ws.send_json({"event": "connected", "version": "1.0"})
            ws.send_json(
                {
                    "start": {
                        "call_control_id": "unknown_call_sid",
                        "to": "+15555550100",
                        "from": "+15555551234",
                    }
                }
            )
            # If no active_call is found in the DB, server.py:4344 closes the WS.
            ws.receive_text()  # raises WebSocketDisconnect


async def test_telnyx_media_stream_with_active_call_runs_pipeline_or_closes(
    client, patched_server_db, monkeypatch
):
    """With an active_calls row, the server proceeds into the pipecat pipeline
    branch (or closes cleanly if the pipeline is not available)."""
    import server

    async def _no_pipeline(**kw):
        # The server checks `is_pipeline_available()` first; if it returns
        # False, the WS is closed. Force that path to keep the test simple.
        pass

    monkeypatch.setattr(server, "is_pipeline_available", lambda: False)

    await patched_server_db.active_calls.insert_one(
        {
            "call_sid": "test_call_sid",
            "restaurant_id": TENANT_A_ID,
            "caller_number": "+15555551234",
            "started_at": "2026-05-01T10:00:00",
            "system_prompt": "test prompt",
            "prompt_kwargs": {},
            "restaurant": {"id": TENANT_A_ID, "name": "Test", "plan": "STARTER"},
            "config": {},
            "menu_items": [],
            "services": [],
            "lang": "en",
        }
    )

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/telnyx/media-stream") as ws:
            ws.send_json({"event": "connected", "version": "1.0"})
            ws.send_json(
                {
                    "start": {
                        "call_control_id": "test_call_sid",
                        "to": "+15555550100",
                        "from": "+15555551234",
                    }
                }
            )
            ws.receive_text()
