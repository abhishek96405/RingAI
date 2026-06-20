"""Stripe webhook event handling for Duuutah AI.

The endpoint under test is ``POST /api/webhooks/stripe`` (server.py:4689).
Signature verification is exercised in
``test_stripe_signature_verification.py``; this file focuses on event
dispatch: subscription lifecycle, checkout completion, payment failure,
and unknown event types.

Signature checking is bypassed via ``stripe_sdk_mock`` (which monkeypatches
``stripe.Webhook.construct_event`` to JSON-decode the body and return it),
so tests can hand the route arbitrary signed-looking bodies.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


def _post_event(client, event: dict) -> "Response":  # noqa: F821 - typing
    body = json.dumps(event).encode()
    return client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={
            "Stripe-Signature": "t=0,v1=ignored-by-mock",
            "Content-Type": "application/json",
        },
    )


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------


async def test_subscription_created_sets_billing_status_active(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "name": "Tenant A",
            "business_type": "restaurant",
            "stripe_customer_id": "cus_test_1",
        }
    )
    event = {
        "id": "evt_sub_created_1",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test_1",
                "customer": "cus_test_1",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["billing_status"] == "active"
    assert updated["plan"] == "PRO"


async def test_subscription_updated_to_past_due(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_test_1",
            "stripe_subscription_id": "sub_test_2",
            "billing_status": "active",
        }
    )
    event = {
        "id": "evt_sub_updated_2",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_test_2",
                "customer": "cus_test_1",
                "status": "past_due",
                "items": {"data": [{"price": {"id": "price_starter_test"}}]},
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["billing_status"] == "past_due"
    assert updated["plan"] == "STARTER"


async def test_subscription_deleted_marks_canceled(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_test_1",
            "stripe_subscription_id": "sub_test_3",
            "billing_status": "active",
        }
    )
    event = {
        "id": "evt_sub_deleted_3",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_test_3",
                "customer": "cus_test_1",
                "status": "canceled",
                "items": {"data": []},
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["billing_status"] == "canceled"


async def test_invoice_payment_failed_marks_past_due(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_test_1",
            "billing_status": "active",
        }
    )
    event = {
        "id": "evt_inv_failed_1",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_test_1"}},
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["billing_status"] == "past_due"


async def test_invoice_paid_resets_monthly_call_count(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_test_1",
            "monthly_call_count": 87,
            "billing_status": "past_due",
        }
    )
    event = {
        "id": "evt_inv_paid_1",
        "type": "invoice.paid",
        "data": {"object": {"customer": "cus_test_1"}},
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["monthly_call_count"] == 0
    assert updated["billing_status"] == "active"


async def test_invoice_payment_succeeded_resets_monthly_call_count(
    client, patched_server_db, stripe_sdk_mock
):
    """PL-07: many Stripe endpoints emit invoice.payment_succeeded (not
    invoice.paid) for recurring renewals. Must reset the counter the same way,
    or paying tenants are over-billed for overage from month 2."""
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_test_1",
            "monthly_call_count": 130,
            "billing_status": "past_due",
        }
    )
    event = {
        "id": "evt_inv_pay_succeeded_1",
        "type": "invoice.payment_succeeded",
        "data": {"object": {"customer": "cus_test_1"}},
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["monthly_call_count"] == 0
    assert updated["billing_status"] == "active"


# ---------------------------------------------------------------------------
# PL-02 loss-of-service notice — fires on transition into a suspended state.
# ---------------------------------------------------------------------------


async def test_subscription_deleted_fires_suspension_notice(
    client, patched_server_db, stripe_sdk_mock, monkeypatch
):
    notices = []

    async def _fake_notify_system(restaurant_id, title, message, data=None):
        notices.append({"restaurant_id": restaurant_id, "title": title, "data": data})

    monkeypatch.setattr("websocket_notifications.notify_system", _fake_notify_system)
    await patched_server_db.restaurants.insert_one(
        {"id": TENANT_A_ID, "stripe_customer_id": "cus_notice_1", "billing_status": "active"}
    )
    event = {
        "id": "evt_sub_deleted_notice",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_n1", "customer": "cus_notice_1", "items": {"data": []}}},
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    assert any(n["restaurant_id"] == TENANT_A_ID for n in notices)


async def test_subscription_updated_unpaid_suspends_and_notifies(
    client, patched_server_db, stripe_sdk_mock, monkeypatch
):
    """When Stripe's retry window ends unrecovered it flips the subscription to
    'unpaid' via customer.subscription.updated. Status must persist as unpaid
    (→ calls denied) and a one-time loss-of-service notice fires."""
    notices = []

    async def _fake_notify_system(restaurant_id, title, message, data=None):
        notices.append({"restaurant_id": restaurant_id})

    monkeypatch.setattr("websocket_notifications.notify_system", _fake_notify_system)
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_notice_2",
            "stripe_subscription_id": "sub_n2",
            "billing_status": "past_due",
        }
    )
    event = {
        "id": "evt_sub_unpaid",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_n2",
                "customer": "cus_notice_2",
                "status": "unpaid",
                "items": {"data": [{"price": {"id": "price_starter_test"}}]},
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["billing_status"] == "unpaid"
    assert any(n["restaurant_id"] == TENANT_A_ID for n in notices)


async def test_subscription_updated_to_active_does_not_notify(
    client, patched_server_db, stripe_sdk_mock, monkeypatch
):
    """A paying customer (status active) must never get a suspension notice."""
    notices = []

    async def _fake_notify_system(restaurant_id, title, message, data=None):
        notices.append(restaurant_id)

    monkeypatch.setattr("websocket_notifications.notify_system", _fake_notify_system)
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "stripe_customer_id": "cus_notice_3",
            "billing_status": "past_due",
        }
    )
    event = {
        "id": "evt_sub_recovered",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_n3",
                "customer": "cus_notice_3",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_starter_test"}}]},
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    assert notices == []


# ---------------------------------------------------------------------------
# Checkout completion
# ---------------------------------------------------------------------------


async def test_checkout_subscription_completed_starts_trial(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.insert_one(
        {"id": TENANT_A_ID, "name": "Tenant A", "business_type": "restaurant"}
    )
    event = {
        "id": "evt_checkout_sub_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "mode": "subscription",
                "customer": "cus_test_1",
                "subscription": "sub_test_1",
                "metadata": {"restaurant_id": TENANT_A_ID, "plan": "PRO"},
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    updated = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert updated["billing_status"] == "trialing"
    assert updated["plan"] == "PRO"
    assert "trial_ends_at" in updated


async def test_checkout_order_payment_marks_paid(
    client, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.call_records.insert_one(
        {
            "id": "call_1",
            "call_sid": "order_test_1",
            "restaurant_id": TENANT_A_ID,
            "payment_status": "pending",
            "caller_number": "+15555550110",
        }
    )
    event = {
        "id": "evt_checkout_pay_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_2",
                "mode": "payment",
                "payment_intent": "pi_test_1",
                "amount_total": 2400,
                "metadata": {
                    "type": "order_payment",
                    "order_id": "order_test_1",
                    "restaurant_id": TENANT_A_ID,
                    "restaurant_name": "Tenant A Diner",
                },
            }
        },
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    rec = await patched_server_db.call_records.find_one({"call_sid": "order_test_1"})
    assert rec["payment_status"] == "paid"


# ---------------------------------------------------------------------------
# Unknown / unhandled event types — should 200 with no side effects.
# ---------------------------------------------------------------------------


async def test_unhandled_event_type_returns_200(
    client, patched_server_db, stripe_sdk_mock
):
    # An event Stripe sends that the app doesn't subscribe to.
    event = {
        "id": "evt_radar_1",
        "type": "radar.early_fraud_warning.created",
        "data": {"object": {"id": "issfr_test_1"}},
    }
    response = _post_event(client, event)
    assert response.status_code == 200
    assert (await patched_server_db.restaurants.count_documents({})) == 0


# ---------------------------------------------------------------------------
# Missing webhook secret short-circuits with 400.
# ---------------------------------------------------------------------------


def test_webhook_secret_missing_returns_400(client, monkeypatch, stripe_sdk_mock):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    response = client.post(
        "/api/webhooks/stripe",
        content=b"{}",
        headers={"Stripe-Signature": "t=0,v1=x", "Content-Type": "application/json"},
    )
    assert response.status_code == 400
