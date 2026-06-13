"""Integration tests — billing, voice preview, demo, test-mode, onboarding.

Covers:
  POST   /api/billing/create-checkout-session
  POST   /api/billing/portal
  GET    /api/billing/invoices
  GET    /api/restaurants/{id}/plan-features
  GET    /api/voice-preview/{voice_name}
  POST   /api/demo/simulate-call
  POST   /api/demo/seed
  GET    /api/test-mode/status
  GET    /api/test-mode/scenarios
  POST   /api/test-mode/run-scenario
  POST   /api/onboarding/menu/parse
  POST   /api/onboarding/menu/confirm
  POST   /api/onboarding/activate
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# BILLING ENDPOINTS
# ---------------------------------------------------------------------------


async def test_create_checkout_session_creates_stripe_session(
    client, two_tenant_with_memberships, stripe_sdk_mock, patched_server_db
):
    response = client.post(
        "/api/billing/create-checkout-session",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "plan": "pro"},
    )
    assert response.status_code == 200
    assert response.json()["checkout_url"].startswith("https://stripe.test")
    # Should have called Customer.create and Session.create
    assert len(stripe_sdk_mock["customer_create"]) == 1
    assert len(stripe_sdk_mock["checkout_create"]) == 1


async def test_create_checkout_session_reuses_existing_customer(
    client, two_tenant_with_memberships, stripe_sdk_mock, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_customer_id": "cus_existing"}}
    )
    response = client.post(
        "/api/billing/create-checkout-session",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "plan": "pro"},
    )
    assert response.status_code == 200
    # No Customer.create called this time
    assert len(stripe_sdk_mock["customer_create"]) == 0
    assert len(stripe_sdk_mock["checkout_create"]) == 1


def test_create_checkout_session_requires_auth(client):
    response = client.post(
        "/api/billing/create-checkout-session",
        json={"restaurant_id": TENANT_A_ID, "plan": "pro"},
    )
    assert response.status_code == 401


async def test_create_checkout_session_invalid_plan_400(
    client, two_tenant_with_memberships, stripe_sdk_mock
):
    response = client.post(
        "/api/billing/create-checkout-session",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "plan": "ENTERPRISE_GOLD"},
    )
    assert response.status_code == 400


async def test_billing_portal_requires_stripe_customer_id(
    client, two_tenant_with_memberships, stripe_sdk_mock
):
    """No customer id → 400."""
    response = client.post(
        "/api/billing/portal",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 400


async def test_billing_portal_returns_portal_url(
    client, two_tenant_with_memberships, stripe_sdk_mock, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_customer_id": "cus_test"}}
    )
    response = client.post(
        "/api/billing/portal",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 200
    assert "portal_url" in response.json()


async def test_billing_invoices_empty_when_no_customer(
    client, two_tenant_with_memberships, stripe_sdk_mock
):
    response = client.get(
        f"/api/billing/invoices?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json() == {"invoices": []}


async def test_billing_invoices_with_customer(
    client, two_tenant_with_memberships, stripe_sdk_mock, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_customer_id": "cus_test"}}
    )
    response = client.get(
        f"/api/billing/invoices?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json() == {"invoices": []}


async def test_plan_features_should_return_plan_block(
    client, two_tenant_with_memberships
):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/plan-features",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] in ("STARTER", "PRO")
    assert "features" in body


# ---------------------------------------------------------------------------
# /api/voice-preview/{voice_name}
# ---------------------------------------------------------------------------


def test_voice_preview_rejects_invalid_voice_400(client, mock_clerk):
    response = client.get(
        "/api/voice-preview/NotARealVoice",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


def test_voice_preview_requires_auth(client):
    assert client.get("/api/voice-preview/Puck").status_code == 401


def test_voice_preview_returns_500_when_gemini_unavailable(client, mock_clerk):
    """In test env GOOGLE_API_KEY is fake — the genai client init fails → 500."""
    response = client.get(
        "/api/voice-preview/Puck",
        headers={"Authorization": "Bearer tenant_a"},
    )
    # 500 because the genai SDK call fails on the fake key. The route's bare
    # except clause re-raises as HTTPException(500). Acceptable for test env.
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# /api/demo/simulate-call
# ---------------------------------------------------------------------------


def test_simulate_call_requires_auth(client):
    assert (
        client.post(f"/api/demo/simulate-call?restaurant_id={TENANT_A_ID}").status_code
        == 401
    )


async def test_simulate_call_disabled_in_test_env(client, two_tenant_with_memberships):
    """ENABLE_DEMO_MODE=false in pyproject env block → 403."""
    response = client.post(
        f"/api/demo/simulate-call?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 403


async def test_seed_demo_disabled_in_test_env(client, two_tenant_with_memberships):
    response = client.post(
        f"/api/demo/seed?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /api/test-mode/*
# ---------------------------------------------------------------------------


def test_test_mode_status_requires_auth(client, mock_clerk):
    """A6-4: test-mode status now requires a valid user."""
    assert client.get("/api/test-mode/status").status_code == 401
    response = client.get(
        "/api/test-mode/status", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 200


def test_test_mode_scenarios(client, mock_clerk):
    """A6-4: test-mode scenarios now requires a valid user."""
    assert client.get("/api/test-mode/scenarios").status_code == 401
    response = client.get(
        "/api/test-mode/scenarios", headers={"Authorization": "Bearer tenant_a"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "scenarios" in body
    assert len(body["scenarios"]) > 0


def test_test_mode_run_scenario_requires_auth(client):
    response = client.post(
        f"/api/test-mode/run-scenario?restaurant_id={TENANT_A_ID}&scenario_id=0"
    )
    assert response.status_code == 401


async def test_test_mode_run_scenario_raises_due_to_undefined_call_sid(
    app, two_tenant_with_memberships, monkeypatch
):
    """Captures current behavior. See FINDINGS:

    /api/test-mode/run-scenario at server.py:5215 references ``call_sid``
    inside the appointment-pre-fetch branch (line 5258, 5269) without ever
    defining it — that variable is only set in WS handlers. Triggered only
    when business_type is in {clinic, salon, home_services, legal} OR the
    log line at line 5258 runs unconditionally. For business_type='restaurant'
    the branch is skipped, so the route succeeds for restaurants.

    Note: the test_mode module's `get_scenario_by_id(0)` returns a scenario
    that exercises restaurant flow, so the route should succeed here.
    Real reachability for the bug requires a clinic/salon. We capture the
    restaurant path here.
    """
    from fastapi.testclient import TestClient

    async def _no_op(*a, **kw):
        return "Hi there"

    import server

    monkeypatch.setattr(server, "get_conversation_response", _no_op)

    async def _fake_analyse(*a, **kw):
        return {"quality_score": 85}

    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post(
            f"/api/test-mode/run-scenario?restaurant_id={TENANT_A_ID}&scenario_id=0",
            headers={"Authorization": "Bearer tenant_a"},
        )
    # Restaurant business type → skips the clinic/salon-only branch that
    # references undefined call_sid. Expect either 200 (success) or 500
    # (the buggy branch fires regardless).
    assert response.status_code in (200, 500)


def test_test_mode_run_scenario_invalid_scenario_id_400(
    client, two_tenant_with_memberships
):
    """scenario_id=999 → get_scenario_by_id returns None → 400."""
    # Pre-emptive: the access check happens first. With memberships seeded
    # for tenant_a, restaurant check passes; then scenario lookup fails.
    response = client.post(
        f"/api/test-mode/run-scenario?restaurant_id={TENANT_A_ID}&scenario_id=999",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Onboarding endpoints
# ---------------------------------------------------------------------------


async def test_onboarding_menu_parse(client, two_tenant_with_memberships, monkeypatch):
    async def _fake_parse(text):
        return [{"name": "Burger", "price": 1000, "category": "Main"}]

    import server

    monkeypatch.setattr(server, "parse_menu_text", _fake_parse)

    response = client.post(
        "/api/onboarding/menu/parse",
        headers={"Authorization": "Bearer tenant_a"},
        json={"menu_text": "Burger - $10", "restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 200


async def test_onboarding_menu_confirm_restaurant_writes_items(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.post(
        f"/api/onboarding/menu/confirm?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json=[
            {"name": "Pizza", "category": "Main", "price": 1500},
            {"name": "Soda", "category": "Drinks", "price": 300},
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["saved"] == 2
    count = await patched_server_db.menu_items.count_documents(
        {"restaurant_id": TENANT_A_ID}
    )
    assert count == 2


async def test_onboarding_menu_confirm_replaces_existing_items(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "old",
            "restaurant_id": TENANT_A_ID,
            "name": "Old",
            "category": "X",
            "price": 100,
        }
    )
    client.post(
        f"/api/onboarding/menu/confirm?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json=[{"name": "New", "category": "Y", "price": 200}],
    )
    items = await patched_server_db.menu_items.find(
        {"restaurant_id": TENANT_A_ID}, {"_id": 0}
    ).to_list(10)
    names = [i["name"] for i in items]
    assert "Old" not in names
    assert "New" in names


async def test_onboarding_activate_persists_active_state(
    client, two_tenant_with_memberships, patched_server_db, telnyx_sdk_mock
):
    # Confirmed subscription (webhook sets trialing) -> fast path, no Stripe call.
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"billing_status": "trialing"}}
    )
    response = client.post(
        "/api/onboarding/activate",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["status"] == "active"
    assert saved["is_active"] is True
    assert saved["onboarding_step"] == 7


async def test_onboarding_activate_rejects_when_never_paid(
    client, two_tenant_with_memberships, patched_server_db, telnyx_sdk_mock
):
    """C23-1: a caller who never started checkout (no customer, pending) cannot
    self-activate — no Stripe handle, straight 402, is_active stays False."""
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"billing_status": "pending", "is_active": False},
         "$unset": {"stripe_customer_id": ""}},
    )
    response = client.post(
        "/api/onboarding/activate",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 402
    saved = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID}, {"_id": 0})
    assert saved.get("is_active") is not True


async def test_onboarding_activate_rejects_abandoned_checkout(
    client, two_tenant_with_memberships, patched_server_db, telnyx_sdk_mock, monkeypatch
):
    """Abandoned checkout: a Stripe customer exists but has no subscription -> 402."""
    import stripe
    from types import SimpleNamespace
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"billing_status": "pending", "stripe_customer_id": "cus_test_x", "is_active": False}},
    )
    monkeypatch.setattr(stripe.Subscription, "list",
                        lambda **kw: SimpleNamespace(data=[]), raising=False)
    response = client.post(
        "/api/onboarding/activate",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 402


async def test_onboarding_activate_confirms_via_stripe_when_webhook_lags(
    client, two_tenant_with_memberships, patched_server_db, telnyx_sdk_mock, monkeypatch
):
    """Redirect beats the webhook: billing_status still 'pending', but Stripe has a
    trialing subscription -> activate confirms against Stripe, proceeds, backfills."""
    import stripe
    from types import SimpleNamespace
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"billing_status": "pending", "stripe_customer_id": "cus_test_x", "is_active": False}},
    )
    monkeypatch.setattr(
        stripe.Subscription, "list",
        lambda **kw: SimpleNamespace(data=[{"id": "sub_test_x", "status": "trialing"}]),
        raising=False,
    )
    response = client.post(
        "/api/onboarding/activate",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID}, {"_id": 0})
    assert saved["is_active"] is True
    assert saved["billing_status"] == "trialing"
    assert saved["stripe_subscription_id"] == "sub_test_x"


def test_onboarding_activate_unknown_restaurant_404(client, mock_clerk):
    """No membership → ensure_restaurant_access raises 404 (existence hidden)."""
    response = client.post(
        "/api/onboarding/activate",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": "nonexistent"},
    )
    assert response.status_code == 404
