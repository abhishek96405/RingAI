"""Telnyx SMS-status webhook tests for ``POST /api/telnyx/sms-inbound``.

These tests exercise the SMS delivery-status update flow:
- ``delivered`` -> sets status=delivered
- ``delivery_failed`` / ``sending_failed`` -> sets status=failed + error code/msg
- ``delivery_unconfirmed`` -> sets status=delivery_unconfirmed
- cost.amount -> stored as cost_cents

Idempotency is provided by the ``upsert=False`` semantics — a status update
for an unknown message_id leaves the database unchanged. We assert that
property here.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


def _sms_event(message_id: str, recipient_status: str, **extra) -> dict:
    return {
        "data": {
            "event_type": "message.finalized",
            "id": f"evt_{message_id}",
            "payload": {
                "id": message_id,
                "to": [{"phone_number": "+15555550120", "status": recipient_status}],
                **extra,
            },
        }
    }


def _post(client, event: dict):
    return client.post(
        "/api/telnyx/sms-inbound",
        content=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture
async def seeded_sms(patched_server_db):
    msg_id = "msg_test_1"
    await patched_server_db.sms_messages.insert_one(
        {
            "id": "sms_1",
            "message_id": msg_id,
            "restaurant_id": TENANT_A_ID,
            "status": "queued",
            "to_number": "+15555550120",
            "from_number": "+15555550100",
        }
    )
    return msg_id


async def test_delivered_status_updates_record(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = _sms_event(seeded_sms, "delivered")
    r = _post(client, event)
    assert r.status_code == 200
    rec = await patched_server_db.sms_messages.find_one({"message_id": seeded_sms})
    assert rec["status"] == "delivered"


async def test_failed_status_records_error_details(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = _sms_event(
        seeded_sms,
        "delivery_failed",
        errors=[{"code": "40001", "title": "Carrier rejected the message"}],
    )
    r = _post(client, event)
    assert r.status_code == 200
    rec = await patched_server_db.sms_messages.find_one({"message_id": seeded_sms})
    assert rec["status"] == "failed"
    assert rec["error_code"] == "40001"
    assert rec["error_message"] == "Carrier rejected the message"


async def test_delivery_unconfirmed_status_updates_record(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = _sms_event(seeded_sms, "delivery_unconfirmed")
    r = _post(client, event)
    assert r.status_code == 200
    rec = await patched_server_db.sms_messages.find_one({"message_id": seeded_sms})
    assert rec["status"] == "delivery_unconfirmed"


async def test_cost_amount_persisted_as_cents(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = _sms_event(seeded_sms, "delivered", cost={"amount": "0.0085"})
    r = _post(client, event)
    assert r.status_code == 200
    rec = await patched_server_db.sms_messages.find_one({"message_id": seeded_sms})
    assert rec["cost_cents"] == 1  # round(0.85) == 1


async def test_unknown_message_id_does_not_create_record(
    client, patched_server_db, telnyx_sdk_mock
):
    # upsert=False — webhook for a message we never stored is a no-op.
    event = _sms_event("msg_never_sent", "delivered")
    r = _post(client, event)
    assert r.status_code == 200
    count = await patched_server_db.sms_messages.count_documents({})
    assert count == 0


async def test_missing_message_id_returns_200_with_no_change(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = {
        "data": {
            "event_type": "message.finalized",
            "payload": {"to": [{"status": "delivered"}]},  # no id
        }
    }
    r = _post(client, event)
    assert r.status_code == 200
    rec = await patched_server_db.sms_messages.find_one({"message_id": seeded_sms})
    assert rec["status"] == "queued"


async def test_malformed_cost_amount_is_ignored(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = _sms_event(seeded_sms, "delivered", cost={"amount": "not-a-number"})
    r = _post(client, event)
    assert r.status_code == 200
    rec = await patched_server_db.sms_messages.find_one({"message_id": seeded_sms})
    assert "cost_cents" not in rec


async def test_idempotent_replay_same_event_twice(
    client, patched_server_db, telnyx_sdk_mock, seeded_sms
):
    event = _sms_event(seeded_sms, "delivered")
    r1 = _post(client, event)
    r2 = _post(client, event)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Still exactly one row, status delivered.
    count = await patched_server_db.sms_messages.count_documents(
        {"message_id": seeded_sms}
    )
    assert count == 1


def test_malformed_json_returns_400(client, telnyx_sdk_mock):
    r = client.post(
        "/api/telnyx/sms-inbound",
        content=b"definitely-not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400
