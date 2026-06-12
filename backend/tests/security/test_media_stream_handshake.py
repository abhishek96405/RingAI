"""Media-stream WebSocket pre-start hardening (A4-2, partial).

The /api/telnyx/media-stream socket accepts, then waits for Telnyx's start
message. F4 bounds that unauthenticated window with
MEDIA_STREAM_START_TIMEOUT_SECONDS (silent sockets closed with 1008) and these
tests also pin the existing rejection behavior: unknown call_control_id and
garbage first messages both result in the server closing the socket before any
pipeline is created.

The handshake token + duplicate-stream guard halves of A4-2 are consciously
deferred (see audit/PR_PLAN.md) — do not add tests asserting them.
"""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

pytestmark = [pytest.mark.security, pytest.mark.integration]

_WS_PATH = "/api/telnyx/media-stream"


def test_silent_connection_times_out(client, patched_server_db, monkeypatch):
    """A socket that never sends a start message is closed with 1008."""
    import server

    monkeypatch.setattr(server, "MEDIA_STREAM_START_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_WS_PATH) as ws:
            ws.receive_text()  # blocks until the server closes us
    assert exc.value.code == 1008


def test_unknown_call_control_id_is_rejected(client, patched_server_db):
    """A start message naming a call that isn't live is closed, no session."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_WS_PATH) as ws:
            ws.send_json({"start": {"call_control_id": "no-such-live-call"}})
            ws.receive_text()


def test_garbage_first_message_is_rejected(client, patched_server_db):
    """A non-start, non-connected first message exits the loop and closes."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_WS_PATH) as ws:
            ws.send_json({"event": "definitely-not-telnyx"})
            ws.receive_text()
