"""Webhook payload edge cases across providers.

Each route must survive malformed input, oversized payloads, unexpected
event types, and missing required fields without crashing (no 500).
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Stripe — events with no metadata / unexpected shapes.
# ---------------------------------------------------------------------------


def test_stripe_event_with_missing_data_object_raises_keyerror_captures_bug(
    app, stripe_sdk_mock
):
    """Captures current bug: the Stripe webhook crashes with KeyError when
    ``event["data"]`` is missing — instead of treating it as a malformed
    event and returning 400. See FINDINGS."""
    from fastapi.testclient import TestClient

    body = json.dumps({"id": "evt_no_data", "type": "ping"}).encode()
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/api/webhooks/stripe",
            content=body,
            headers={
                "Stripe-Signature": "t=0,v1=x",
                "Content-Type": "application/json",
            },
        )
    # Server-side exception, no clean 4xx — body never makes it past the
    # `event["data"]["object"]` lookup at server.py:4704.
    assert r.status_code == 500


@pytest.mark.xfail(
    strict=True,
    reason=(
        "LOW: Stripe webhook should treat events with no data.object as malformed "
        "(400) instead of crashing with KeyError → 500."
    ),
)
def test_stripe_event_with_missing_data_object_should_400_expected(
    app, stripe_sdk_mock
):
    from fastapi.testclient import TestClient

    body = json.dumps({"id": "evt_no_data", "type": "ping"}).encode()
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/api/webhooks/stripe",
            content=body,
            headers={
                "Stripe-Signature": "t=0,v1=x",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 400


def test_stripe_event_with_unknown_type_returns_200(client, stripe_sdk_mock):
    body = json.dumps(
        {
            "id": "evt_unknown_1",
            "type": "this.event.type.does.not.exist",
            "data": {"object": {}},
        }
    ).encode()
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": "t=0,v1=x", "Content-Type": "application/json"},
    )
    assert r.status_code == 200


def test_stripe_subscription_event_missing_customer(client, stripe_sdk_mock):
    body = json.dumps(
        {
            "id": "evt_sub_no_cust",
            "type": "customer.subscription.created",
            "data": {
                "object": {"id": "sub_x", "status": "active", "items": {"data": []}}
            },
        }
    ).encode()
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": "t=0,v1=x", "Content-Type": "application/json"},
    )
    # Without a customer, the route's update_one filters match nothing —
    # the route must not crash.
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Telnyx — events with missing payload sub-keys.
# ---------------------------------------------------------------------------


def test_telnyx_call_event_missing_payload(client, telnyx_sdk_mock):
    body = json.dumps({"data": {"event_type": "call.hangup"}}).encode()
    r = client.post(
        "/api/telnyx/incoming",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200


def test_telnyx_call_event_with_no_data(client, telnyx_sdk_mock):
    body = json.dumps({}).encode()
    r = client.post(
        "/api/telnyx/incoming",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200


def test_telnyx_sms_event_no_recipients(client, patched_server_db, telnyx_sdk_mock):
    body = json.dumps(
        {
            "data": {
                "event_type": "message.finalized",
                "payload": {"id": "msg_no_recip"},
            }
        }
    ).encode()
    r = client.post(
        "/api/telnyx/sms-inbound",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Square — accepts anything (current stub) but must not crash on edges.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b"null",
        b'{"deeply": {"nested": {"object": {"with": "no-event-shape"}}}}',
    ],
)
def test_square_webhook_survives_edge_bodies(client, body):
    r = client.post(
        "/api/webhooks/square",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
