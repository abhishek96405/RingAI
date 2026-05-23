"""Cross-provider webhook idempotency tests.

When a webhook provider retries delivery (network blip, slow ACK, etc.) the
endpoint receives the *same event id* twice. Side effects must run exactly
once. This file replays the same payload twice per provider and asserts no
double-effect.

Where a route is known to lack idempotency, the assertion is captured as
``xfail(strict=True)`` so the day idempotency is added the test flips.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Stripe — invoice.paid is the cleanest case: it resets monthly_call_count
# to 0 and sets billing_status=active. Replaying is a no-op (already 0/active).
# ---------------------------------------------------------------------------


async def test_stripe_invoice_paid_idempotent_on_replay(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_idemp_1",
            "monthly_call_count": 42,
            "billing_status": "past_due",
        }
    )
    event = json.dumps(
        {
            "id": "evt_inv_paid_replay",
            "type": "invoice.paid",
            "data": {"object": {"customer": "cus_idemp_1"}},
        }
    ).encode()
    headers = {
        "Stripe-Signature": "t=0,v1=ignored",
        "Content-Type": "application/json",
    }
    r1 = client.post("/api/webhooks/stripe", content=event, headers=headers)
    r2 = client.post("/api/webhooks/stripe", content=event, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    rec = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert rec["monthly_call_count"] == 0
    assert rec["billing_status"] == "active"


# ---------------------------------------------------------------------------
# Stripe — checkout.session.completed in order_payment mode marks an order
# paid. Replay should not double-charge (no second paid timestamp etc.).
# Documents the current behaviour: the update is idempotent at the DB level
# (it's just a $set, no counter increment), but there is no event-id
# dedup table, so secondary side effects (websocket notify, SMS) re-fire.
# ---------------------------------------------------------------------------


async def test_stripe_checkout_replay_does_not_double_mark_paid(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.call_records.insert_one(
        {
            "id": "call_idem_1",
            "call_sid": "order_idem_1",
            "restaurant_id": TENANT_A_ID,
            "payment_status": "pending",
            "caller_number": "+15555550120",
        }
    )
    event = json.dumps(
        {
            "id": "evt_checkout_replay",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_idem_1",
                    "mode": "payment",
                    "payment_intent": "pi_idem_1",
                    "amount_total": 1900,
                    "metadata": {
                        "type": "order_payment",
                        "order_id": "order_idem_1",
                        "restaurant_id": TENANT_A_ID,
                        "restaurant_name": "Tenant A",
                    },
                }
            },
        }
    ).encode()
    headers = {
        "Stripe-Signature": "t=0,v1=ignored",
        "Content-Type": "application/json",
    }
    r1 = client.post("/api/webhooks/stripe", content=event, headers=headers)
    r2 = client.post("/api/webhooks/stripe", content=event, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    rec = await patched_server_db.call_records.find_one({"call_sid": "order_idem_1"})
    assert rec["payment_status"] == "paid"
    # No duplicate call record was created.
    count = await patched_server_db.call_records.count_documents(
        {"call_sid": "order_idem_1"}
    )
    assert count == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MEDIUM: Stripe webhook lacks event-id dedup. SMS/WebSocket notifications "
        "for the same checkout.session.completed event fire on every replay."
    ),
)
async def test_stripe_checkout_replay_does_not_send_second_sms_expected(
    client, patched_server_db, stripe_sdk_mock, telnyx_sdk_mock
):
    await patched_server_db.call_records.insert_one(
        {
            "id": "call_idem_2",
            "call_sid": "order_idem_2",
            "restaurant_id": TENANT_A_ID,
            "payment_status": "pending",
            "caller_number": "+15555550120",
        }
    )
    event = json.dumps(
        {
            "id": "evt_checkout_sms_replay",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_idem_2",
                    "mode": "payment",
                    "payment_intent": "pi_idem_2",
                    "amount_total": 1900,
                    "metadata": {
                        "type": "order_payment",
                        "order_id": "order_idem_2",
                        "restaurant_id": TENANT_A_ID,
                        "restaurant_name": "Tenant A",
                    },
                }
            },
        }
    ).encode()
    headers = {
        "Stripe-Signature": "t=0,v1=ignored",
        "Content-Type": "application/json",
    }
    client.post("/api/webhooks/stripe", content=event, headers=headers)
    client.post("/api/webhooks/stripe", content=event, headers=headers)
    # Expected: only ONE SMS sent across two replays of the same event ID.
    assert len(telnyx_sdk_mock["send_sms"]) == 1


# ---------------------------------------------------------------------------
# Telnyx SMS — message_id update is idempotent (status converges).
# ---------------------------------------------------------------------------


async def test_telnyx_sms_replay_does_not_duplicate_row(
    client, patched_server_db, telnyx_sdk_mock
):
    await patched_server_db.sms_messages.insert_one(
        {
            "id": "sms_idem_1",
            "message_id": "msg_idem_1",
            "status": "queued",
            "restaurant_id": TENANT_A_ID,
        }
    )
    event = json.dumps(
        {
            "data": {
                "event_type": "message.finalized",
                "id": "evt_sms_replay_1",
                "payload": {
                    "id": "msg_idem_1",
                    "to": [{"status": "delivered"}],
                },
            }
        }
    ).encode()
    r1 = client.post(
        "/api/telnyx/sms-inbound",
        content=event,
        headers={"Content-Type": "application/json"},
    )
    r2 = client.post(
        "/api/telnyx/sms-inbound",
        content=event,
        headers={"Content-Type": "application/json"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    count = await patched_server_db.sms_messages.count_documents(
        {"message_id": "msg_idem_1"}
    )
    assert count == 1
    rec = await patched_server_db.sms_messages.find_one({"message_id": "msg_idem_1"})
    assert rec["status"] == "delivered"


# ---------------------------------------------------------------------------
# Telnyx call — upsert on call.initiated is naturally idempotent on
# call_control_id. Replay should not create a second active_calls row.
# ---------------------------------------------------------------------------


async def test_telnyx_call_initiated_replay_upserts_same_row(
    client, patched_server_db, telnyx_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "twilio_phone_number": "+15555550100",
            "phone_number": "+15555550100",
            "is_active": True,
            "language": "en",
        }
    )
    event = json.dumps(
        {
            "data": {
                "event_type": "call.initiated",
                "id": "evt_call_replay",
                "payload": {
                    "call_control_id": "cc_replay_1",
                    "from": "+15555550120",
                    "to": "+15555550100",
                    "direction": "incoming",
                },
            }
        }
    ).encode()
    r1 = client.post(
        "/api/telnyx/incoming",
        content=event,
        headers={"Content-Type": "application/json"},
    )
    r2 = client.post(
        "/api/telnyx/incoming",
        content=event,
        headers={"Content-Type": "application/json"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    count = await patched_server_db.active_calls.count_documents(
        {"call_sid": "cc_replay_1"}
    )
    assert count == 1
