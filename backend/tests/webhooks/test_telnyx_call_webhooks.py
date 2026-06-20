"""Telnyx call-control webhook tests for ``POST /api/telnyx/incoming``.

This file exercises event dispatch (``call.initiated``, ``call.answered``,
``call.gather.ended``, ``call.hangup``, streaming events) with signature
verification stubbed via ``telnyx_sdk_mock`` (which makes
``telnyx_service.verify_webhook_signature`` always return True).

Signature scenarios live in ``test_telnyx_signature_verification.py``.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


def _event(event_type: str, **payload) -> dict:
    return {
        "data": {
            "event_type": event_type,
            "id": f"evt_{event_type.replace('.', '_')}",
            "payload": payload,
            "record_type": "event",
        }
    }


def _post(client, event: dict, headers: dict | None = None):
    body = json.dumps(event).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    return client.post("/api/telnyx/incoming", content=body, headers=h)


# ---------------------------------------------------------------------------
# call.initiated
# ---------------------------------------------------------------------------


async def test_call_initiated_seeds_active_call(
    client, patched_server_db, telnyx_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "name": "Tenant A Diner",
            "twilio_phone_number": "+15555550100",
            "phone_number": "+15555550100",
            "is_active": True,
            "billing_status": "active",
            "language": "en",
        }
    )
    event = _event(
        "call.initiated",
        call_control_id="cc_inbound_1",
        from_="+15555550120",
        to="+15555550100",
        direction="incoming",
    )
    # Telnyx serializes the field as "from", not "from_".
    event["data"]["payload"]["from"] = event["data"]["payload"].pop("from_")
    r = _post(client, event)
    assert r.status_code == 200
    active = await patched_server_db.active_calls.find_one({"call_sid": "cc_inbound_1"})
    assert active is not None


async def test_call_initiated_with_unknown_to_number_hangs_up(
    client, patched_server_db, telnyx_sdk_mock
):
    event = _event(
        "call.initiated",
        call_control_id="cc_unknown_1",
        to="+15555559999",
        direction="incoming",
    )
    event["data"]["payload"]["from"] = "+15555550120"
    r = _post(client, event)
    assert r.status_code == 200
    # Hang-up was called with the inbound call_control_id.
    assert "cc_unknown_1" in [call for call in telnyx_sdk_mock["hang_up_call"]]


async def test_call_initiated_outbound_direction_short_circuits(
    client, patched_server_db, telnyx_sdk_mock
):
    event = _event(
        "call.initiated",
        call_control_id="cc_outbound_1",
        to="+15555550100",
        direction="outgoing",
    )
    event["data"]["payload"]["from"] = "+15555550100"
    r = _post(client, event)
    assert r.status_code == 200
    # No active_calls row created for outbound direction.
    count = await patched_server_db.active_calls.count_documents(
        {"call_sid": "cc_outbound_1"}
    )
    assert count == 0


# ---------------------------------------------------------------------------
# call.answered — without IVR routing it must start streaming.
# ---------------------------------------------------------------------------


async def test_call_answered_starts_streaming_when_no_ivr(client, telnyx_sdk_mock):
    event = _event("call.answered", call_control_id="cc_ans_1", client_state="")
    r = _post(client, event, headers={"host": "test.example.com"})
    assert r.status_code == 200
    started = telnyx_sdk_mock["start_streaming"]
    assert any(s["call_id"] == "cc_ans_1" for s in started)


# ---------------------------------------------------------------------------
# call.hangup — must accept and 200 without changes.
# ---------------------------------------------------------------------------


async def test_call_hangup_returns_200(client, telnyx_sdk_mock):
    event = _event("call.hangup", call_control_id="cc_hang_1")
    r = _post(client, event)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# call.bridged — transfer-race fix: cleanly releases the pipeline once
# Telnyx confirms the customer-human bridge is live.
# ---------------------------------------------------------------------------


async def test_call_bridged_with_registered_session_invokes_handler(
    client, telnyx_sdk_mock
):
    """When a session for this call_control_id is in the registry and is
    awaiting a transfer bridge, the webhook handler must invoke
    _handle_transfer_bridged on it."""
    import server
    from unittest.mock import AsyncMock

    fake_session = AsyncMock()
    fake_session._transfer_in_progress = True
    fake_session._bridge_succeeded = False
    server.register_call_session("cc_bridged_1", fake_session)
    try:
        event = _event("call.bridged", call_control_id="cc_bridged_1")
        r = _post(client, event)
        assert r.status_code == 200
        fake_session._handle_transfer_bridged.assert_awaited_once()
    finally:
        server.unregister_call_session("cc_bridged_1")


async def test_call_bridged_without_session_returns_200_quietly(
    client, telnyx_sdk_mock
):
    """If no session is registered for this call_control_id (process restart
    between transfer init and bridge complete), the webhook must not crash
    and must return 200. The bridge itself is fine; we just can't do
    post-bridge cleanup."""
    event = _event("call.bridged", call_control_id="cc_orphan_bridge_1")
    r = _post(client, event)
    assert r.status_code == 200


async def test_call_hangup_during_transfer_invokes_timeout_handler(
    client, telnyx_sdk_mock
):
    """When call.hangup arrives for a session that's mid-transfer (transfer
    initiated but bridge never succeeded), the webhook routes to the
    timeout handler so the fallback watchdog gets cancelled and the
    pipeline is released."""
    import server
    from unittest.mock import AsyncMock

    fake_session = AsyncMock()
    fake_session._transfer_in_progress = True
    fake_session._bridge_succeeded = False
    server.register_call_session("cc_timeout_1", fake_session)
    try:
        event = _event("call.hangup", call_control_id="cc_timeout_1")
        r = _post(client, event)
        assert r.status_code == 200
        fake_session._handle_transfer_timeout.assert_awaited_once()
    finally:
        server.unregister_call_session("cc_timeout_1")


async def test_call_hangup_for_normal_call_does_not_invoke_timeout_handler(
    client, telnyx_sdk_mock
):
    """Regular call.hangup (customer hung up normally, no transfer in
    progress) must NOT trigger the transfer timeout path."""
    import server
    from unittest.mock import AsyncMock

    fake_session = AsyncMock()
    fake_session._transfer_in_progress = False
    fake_session._bridge_succeeded = False
    server.register_call_session("cc_normal_hangup_1", fake_session)
    try:
        event = _event("call.hangup", call_control_id="cc_normal_hangup_1")
        r = _post(client, event)
        assert r.status_code == 200
        fake_session._handle_transfer_timeout.assert_not_awaited()
    finally:
        server.unregister_call_session("cc_normal_hangup_1")


# ---------------------------------------------------------------------------
# Streaming events — log-only paths.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event_type", ["streaming.started", "streaming.stopped", "streaming.failed"]
)
async def test_streaming_events_return_200(client, telnyx_sdk_mock, event_type):
    event = _event(event_type, call_control_id="cc_stream_1")
    r = _post(client, event)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Unknown event types — must not crash.
# ---------------------------------------------------------------------------


async def test_unknown_event_type_returns_200(client, telnyx_sdk_mock):
    # NOTE: call.bridged is now a handled event (see transfer-race fix).
    # Use a truly unhandled type here.
    event = _event("call.recording.saved", call_control_id="cc_unk_1")
    r = _post(client, event)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Out-of-order events: hangup arrives before answered. The handler must
# still respond 200; the order assertion is on behaviour, not state.
# ---------------------------------------------------------------------------


async def test_hangup_before_answered_returns_200(client, telnyx_sdk_mock):
    hang = _event("call.hangup", call_control_id="cc_oo_1")
    ans = _event("call.answered", call_control_id="cc_oo_1", client_state="")
    r1 = _post(client, hang)
    r2 = _post(client, ans)
    assert r1.status_code == 200
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Malformed JSON body — route must 400, never 500.
# ---------------------------------------------------------------------------


def test_malformed_json_returns_400(client, telnyx_sdk_mock):
    r = client.post(
        "/api/telnyx/incoming",
        content=b"this-is-not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Missing fields shouldn't crash.
# ---------------------------------------------------------------------------


def test_empty_payload_returns_200(client, telnyx_sdk_mock):
    r = client.post(
        "/api/telnyx/incoming",
        content=b'{"data": {}}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
