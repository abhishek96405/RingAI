"""Direct-call coverage tests for helpers used only by webhooks/WS handlers.

The Telnyx incoming webhook (POST /api/telnyx/incoming) and the
/api/telnyx/media-stream WebSocket call these helpers as part of their
inbound-call setup. The full webhook is deferred to C4, but the helpers are
pure functions that we can exercise directly to lift server.py coverage.

Covers:
  server.py:3760  _prefetch_call_session_data
  server.py:3939  _decode_client_state / _encode_client_state
  server.py:3959  _compute_language_routing
  server.py:4013  _build_ivr_speak_payload
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


async def test_prefetch_call_session_data_unknown_number_returns_none(
    patched_server_db,
):
    """When the called number isn't on file the helper returns None."""
    import server

    result = await server._prefetch_call_session_data(
        called_number="+19999999999",
        caller_number="+15555550100",
        call_sid="CA_test",
    )
    assert result is None


async def test_prefetch_call_session_data_inactive_restaurant_returns_none(
    patched_server_db,
):
    """Active=False restaurants are treated as not on file."""
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "name": "X",
            "phone_number": "+15551111111",
            "is_active": False,
        }
    )
    import server

    assert (
        await server._prefetch_call_session_data(
            called_number="+15551111111",
            caller_number="+15555550100",
            call_sid="CA_test",
        )
        is None
    )


async def test_prefetch_call_session_data_active_restaurant_builds_session(
    patched_server_db, monkeypatch
):
    """Active restaurant with menu items → returns a session dict including
    the pre-built system prompt and the menu items."""
    await patched_server_db.restaurants.insert_one(
        {
            "id": TENANT_A_ID,
            "name": "Active",
            "phone_number": "+15552222222",
            "is_active": True,
            "plan": "STARTER",
            "business_type": "restaurant",
        }
    )
    await patched_server_db.menu_items.insert_one(
        {
            "id": "i1",
            "restaurant_id": TENANT_A_ID,
            "name": "Pizza",
            "category": "Pizza",
            "price": 1500,
            "available": True,
        }
    )

    import gemini_service

    monkeypatch.setattr(
        gemini_service,
        "get_system_prompt",
        lambda **kw: "stub system prompt",
        raising=False,
    )

    import server

    result = await server._prefetch_call_session_data(
        called_number="+15552222222",
        caller_number="+15555550100",
        call_sid="CA_test",
    )
    assert result is not None
    assert result["restaurant_id"] == TENANT_A_ID
    assert result["system_prompt"] == "stub system prompt"
    assert len(result["menu_items"]) == 1


# ---------------------------------------------------------------------------
# IVR / language routing helpers
# ---------------------------------------------------------------------------


def test_encode_decode_client_state_roundtrip():
    import server

    payload = {"needs_ivr": True, "default_lang": "en", "digit_to_lang": {"1": "en"}}
    encoded = server._encode_client_state(payload)
    decoded = server._decode_client_state(encoded)
    assert decoded == payload


def test_decode_client_state_empty_returns_empty():
    import server

    assert server._decode_client_state("") == {}
    assert server._decode_client_state(None) == {}


def test_decode_client_state_invalid_returns_empty():
    import server

    # Not valid base64 / JSON
    assert server._decode_client_state("not-real-base64!!") == {}


def test_compute_language_routing_starter_plan_no_ivr():
    """STARTER plan must never trigger the IVR even if multilingual_enabled
    is on (multilingual is PRO-only)."""
    import server

    routing = server._compute_language_routing(
        {
            "restaurant": {"plan": "STARTER"},
            "config": {
                "multilingual_enabled": True,
                "primary_language": "en",
                "additional_languages": ["es"],
            },
        }
    )
    assert routing["ivr_state"]["needs_ivr"] is False
    assert routing["lang"] == "en"


def test_compute_language_routing_pro_with_multilang_triggers_ivr():
    """Uses two supported language codes (en, es, hi) so the IVR fires."""
    import server

    routing = server._compute_language_routing(
        {
            "restaurant": {"plan": "PRO"},
            "config": {
                "multilingual_enabled": True,
                "primary_language": "en",
                "additional_languages": ["es", "hi"],
            },
        }
    )
    assert routing["ivr_state"]["needs_ivr"] is True
    assert routing["ivr_state"]["default_lang"] == "en"
    assert routing["ivr_state"]["digit_to_lang"] == {"1": "en", "2": "es", "3": "hi"}


def test_compute_language_routing_pro_with_only_one_language_skips_ivr():
    """PRO plan + multilingual enabled but only one supported language → no IVR."""
    import server

    routing = server._compute_language_routing(
        {
            "restaurant": {"plan": "PRO"},
            "config": {
                "multilingual_enabled": True,
                "primary_language": "en",
                "additional_languages": [],
            },
        }
    )
    assert routing["ivr_state"]["needs_ivr"] is False


def test_compute_language_routing_invalid_primary_language_falls_back_to_en():
    import server

    routing = server._compute_language_routing(
        {
            "restaurant": {"plan": "PRO"},
            "config": {
                "multilingual_enabled": True,
                "primary_language": "klingon",
                "additional_languages": [],
            },
        }
    )
    assert routing["lang"] == "en"


def test_build_ivr_speak_payload_uses_latin_names():
    import server

    payload = server._build_ivr_speak_payload({"1": "en", "2": "es"})
    # Output looks like "For English, press 1. For Spanish, press 2."
    assert "press 1" in payload
    assert "press 2" in payload


# ---------------------------------------------------------------------------
# create_stripe_payment_link helper (server.py:3288)
# ---------------------------------------------------------------------------


async def test_create_stripe_payment_link_returns_none_without_connect_account(
    stripe_sdk_mock,
):
    import server

    result = await server.create_stripe_payment_link(
        order_total_cents=2500,
        restaurant_name="Test",
        call_sid="CA_test",
        restaurant_id=TENANT_A_ID,
        stripe_account_id=None,
    )
    assert result is None


async def test_create_stripe_payment_link_returns_none_for_zero_total(stripe_sdk_mock):
    import server

    result = await server.create_stripe_payment_link(
        order_total_cents=0,
        restaurant_name="Test",
        call_sid="CA_test",
        stripe_account_id="acct_test",
    )
    assert result is None


async def test_create_stripe_payment_link_creates_checkout_when_connected(
    stripe_sdk_mock,
):
    import server

    result = await server.create_stripe_payment_link(
        order_total_cents=2500,
        restaurant_name="Test",
        call_sid="CA_test_xyz",
        restaurant_id=TENANT_A_ID,
        stripe_account_id="acct_test",
    )
    assert result == "https://stripe.test/checkout/cs_test_123"
    # The mock should have recorded the checkout creation
    assert len(stripe_sdk_mock["checkout_create"]) == 1
