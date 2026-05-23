"""Integration tests — Google Calendar OAuth, POS credentials/sync, Telnyx provisioning.

Webhook endpoints (POST /api/telnyx/incoming, POST /api/telnyx/sms-inbound,
POST /api/webhooks/stripe, POST /api/webhooks/square) are explicitly OUT OF
SCOPE for C3 — they will be covered with full signature verification in C4.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests._constants import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# /api/calendar/google/connect
# ---------------------------------------------------------------------------


def test_calendar_connect_requires_auth(client):
    assert (
        client.get(
            f"/api/calendar/google/connect?restaurant_id={TENANT_A_ID}"
        ).status_code
        == 401
    )


async def test_calendar_connect_returns_auth_url(
    client, two_tenant_with_memberships, monkeypatch
):
    """When configured, returns an authorization_url string."""
    import calendar_service

    monkeypatch.setattr(calendar_service, "is_google_calendar_configured", lambda: True)
    monkeypatch.setattr(
        calendar_service,
        "get_google_auth_url",
        lambda rid, redirect_uri: f"https://accounts.google.com/o/oauth2/v2/auth?state={rid}",
    )

    response = client.get(
        f"/api/calendar/google/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert "authorization_url" in response.json()


async def test_calendar_connect_returns_400_when_not_configured(
    client, two_tenant_with_memberships, monkeypatch
):
    import calendar_service

    monkeypatch.setattr(
        calendar_service, "is_google_calendar_configured", lambda: False
    )
    response = client.get(
        f"/api/calendar/google/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


async def test_calendar_connect_wrong_tenant_403(
    client, two_tenant_with_memberships, monkeypatch
):
    import calendar_service

    monkeypatch.setattr(calendar_service, "is_google_calendar_configured", lambda: True)
    response = client.get(
        f"/api/calendar/google/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /api/calendar/google/callback  (OAuth redirect target, no auth)
# ---------------------------------------------------------------------------


async def test_calendar_callback_exchanges_code_and_redirects(
    client, two_tenant_setup, patched_server_db, monkeypatch
):
    import calendar_service

    async def _fake_exchange(code, redirect_uri):
        return {
            "access_token": "at_test",
            "refresh_token": "rt_test",
            "expires_in": 3600,
        }

    monkeypatch.setattr(calendar_service, "exchange_code_for_tokens", _fake_exchange)

    response = client.get(
        f"/api/calendar/google/callback?code=AUTH_CODE&state={TENANT_A_ID}",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "calendar_connected=true" in response.headers["location"]

    saved = await patched_server_db.restaurant_configs.find_one(
        {"restaurant_id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["google_calendar_tokens"]["access_token"] == "at_test"


async def test_calendar_callback_redirects_on_exchange_error(
    client, two_tenant_setup, monkeypatch
):
    import calendar_service

    async def _broken(code, redirect_uri):
        raise RuntimeError("invalid_grant")

    monkeypatch.setattr(calendar_service, "exchange_code_for_tokens", _broken)

    response = client.get(
        f"/api/calendar/google/callback?code=BAD&state={TENANT_A_ID}",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "calendar_error=true" in response.headers["location"]


def test_calendar_callback_missing_state_returns_422(client):
    response = client.get("/api/calendar/google/callback?code=X")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/restaurants/{id}/calendar/status
# ---------------------------------------------------------------------------


async def test_calendar_status_disconnected(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/status",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False


async def test_calendar_status_connected(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "google_calendar_tokens": {"access_token": "at_test"},
            "google_calendar_id": "primary",
        }
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/status",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["calendar_id"] == "primary"


# ---------------------------------------------------------------------------
# /api/restaurants/{id}/calendar/availability
# ---------------------------------------------------------------------------


async def test_calendar_availability_404_without_config(
    client, two_tenant_with_memberships
):
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/availability?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404


async def test_calendar_availability_returns_slots_with_config(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "operating_hours": {
                "monday": {"closed": False, "open": "09:00", "close": "17:00"},
                "tuesday": {"closed": False, "open": "09:00", "close": "17:00"},
                "wednesday": {"closed": False, "open": "09:00", "close": "17:00"},
                "thursday": {"closed": False, "open": "09:00", "close": "17:00"},
                "friday": {"closed": False, "open": "09:00", "close": "17:00"},
                "saturday": {"closed": True, "open": "00:00", "close": "00:00"},
                "sunday": {"closed": True, "open": "00:00", "close": "00:00"},
            },
        }
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/availability?date=2026-06-01",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert "slots" in response.json()


async def test_calendar_availability_invalid_date_400(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {"restaurant_id": TENANT_A_ID, "operating_hours": {}}
    )
    response = client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/availability?date=not-a-date",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# /api/restaurants/{id}/calendar/book
# ---------------------------------------------------------------------------


async def test_book_appointment_happy_path(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {"restaurant_id": TENANT_A_ID, "operating_hours": {}}
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/calendar/book",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "service_name": "Consult",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "customer_name": "Alice",
            "customer_phone": "+15555550100",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["appointment"]["customer_name"] == "Alice"


async def test_book_appointment_missing_field_400(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {"restaurant_id": TENANT_A_ID, "operating_hours": {}}
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/calendar/book",
        headers={"Authorization": "Bearer tenant_a"},
        json={"service_name": "Consult"},
    )
    assert response.status_code == 400


async def test_book_appointment_invalid_phone_400(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {"restaurant_id": TENANT_A_ID, "operating_hours": {}}
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/calendar/book",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "service_name": "Consult",
            "scheduled_date": "2026-06-01",
            "scheduled_time": "10:00",
            "customer_name": "Alice",
            "customer_phone": "not-a-phone",
        },
    )
    assert response.status_code == 400


async def test_book_appointment_invalid_date_400(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {"restaurant_id": TENANT_A_ID, "operating_hours": {}}
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/calendar/book",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "service_name": "Consult",
            "scheduled_date": "not-a-date",
            "scheduled_time": "10:00",
            "customer_name": "Alice",
            "customer_phone": "+15555550100",
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# /api/restaurants/{id}/calendar/disconnect
# ---------------------------------------------------------------------------


async def test_disconnect_calendar(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "google_calendar_tokens": {"access_token": "at_test"},
        }
    )
    response = client.delete(
        f"/api/restaurants/{TENANT_A_ID}/calendar/disconnect",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurant_configs.find_one(
        {"restaurant_id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["google_calendar_tokens"] is None


# ---------------------------------------------------------------------------
# POS — /api/restaurants/{id}/pos/credentials
# ---------------------------------------------------------------------------


async def test_save_pos_credentials_persists_encrypted(
    client, two_tenant_with_memberships, patched_server_db
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        headers={"Authorization": "Bearer tenant_a"},
        json={
            "pos_type": "clover",
            "clover_api_token": "secret_token",
            "clover_merchant_id": "M12345",
        },
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["pos_type"] == "clover"
    # Values should be ciphertext, not plaintext
    assert saved.get("clover_api_token") != "secret_token"
    assert saved.get("clover_merchant_id") != "M12345"


def test_save_pos_credentials_requires_auth(client):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        json={"pos_type": "clover"},
    )
    assert response.status_code == 401


def test_save_pos_credentials_invalid_payload_422(client, mock_clerk):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        headers={"Authorization": "Bearer tenant_a"},
        json={},  # missing required pos_type
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POS sync — /api/restaurants/{id}/pos/sync
# ---------------------------------------------------------------------------


async def test_pos_sync_unconfigured(client, two_tenant_with_memberships, monkeypatch):
    """No pos_type set → routes to pos_sync.sync_menu_from_pos which short-circuits."""
    import pos_sync

    monkeypatch.setattr(
        pos_sync,
        "sync_menu_from_pos",
        AsyncMock(return_value={"success": False, "error": "No POS type"}),
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/sync",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is False


async def test_pos_test_connection_no_pos_type(client, two_tenant_with_memberships):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/test",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is False


async def test_pos_test_clover_placeholder(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"pos_type": "clover"}}
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/test",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# /api/telnyx/numbers/status
# ---------------------------------------------------------------------------


async def test_telnyx_numbers_status(
    client, two_tenant_with_memberships, telnyx_sdk_mock
):
    response = client.get(
        f"/api/telnyx/numbers/status?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["voice_app_configured"] is True


def test_telnyx_numbers_status_requires_auth(client):
    assert (
        client.get(
            f"/api/telnyx/numbers/status?restaurant_id={TENANT_A_ID}"
        ).status_code
        == 401
    )


# ---------------------------------------------------------------------------
# /api/telnyx/numbers/search
# ---------------------------------------------------------------------------


def test_telnyx_search(client, mock_clerk, telnyx_sdk_mock):
    response = client.get(
        "/api/telnyx/numbers/search?area_code=415",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["available"][0]["phone_number"] == "+15555550100"


def test_telnyx_search_propagates_telnyx_error_as_500_due_to_missing_httpx_import(
    app, mock_clerk, monkeypatch
):
    """Captures current behavior. See FINDINGS:

    GET /api/telnyx/numbers/search wraps the search call in
    ``except httpx.HTTPStatusError`` but ``httpx`` is NOT imported at module
    scope in server.py — that breaks the except clause and lets the original
    exception propagate as a 500. Same bug at server.py:3552 (provision) and
    3649 (assign).
    """
    from fastapi.testclient import TestClient
    import telnyx_service

    async def _broken(country_code="US", area_code=None, limit=10):
        raise RuntimeError("telnyx down")

    monkeypatch.setattr(telnyx_service, "search_available_numbers", _broken)

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get(
            "/api/telnyx/numbers/search",
            headers={"Authorization": "Bearer tenant_a"},
        )
    # 500 instead of the route's intended 502.
    assert response.status_code == 500


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: server.py references httpx in except clauses (lines 3478, 3552, 3649) "
        "but does not import httpx at module scope. The except handler fails with "
        "NameError → original exception is not converted to the documented 502. "
        "Fix: add `import httpx` at the top of server.py."
    ),
)
def test_telnyx_search_should_return_502_on_error(client, mock_clerk, monkeypatch):
    import telnyx_service

    async def _broken(country_code="US", area_code=None, limit=10):
        raise RuntimeError("telnyx down")

    monkeypatch.setattr(telnyx_service, "search_available_numbers", _broken)

    response = client.get(
        "/api/telnyx/numbers/search",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 502


def test_telnyx_search_invalid_limit_422(client, mock_clerk):
    response = client.get(
        "/api/telnyx/numbers/search?limit=999",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/telnyx/numbers/provision
# ---------------------------------------------------------------------------


async def test_telnyx_provision(
    client, two_tenant_with_memberships, telnyx_sdk_mock, patched_server_db
):
    response = client.post(
        "/api/telnyx/numbers/provision",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "area_code": "415"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["phone_number"] == "+15555550100"
    assert body["status"] == "success"

    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["phone_number"] == "+15555550100"


async def test_telnyx_provision_rejects_already_assigned(
    client, two_tenant_with_memberships, telnyx_sdk_mock, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"phone_number": "+15551234567", "phone_number_id": "pn_old"}},
    )
    response = client.post(
        "/api/telnyx/numbers/provision",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "area_code": "415"},
    )
    assert response.status_code == 409


async def test_telnyx_provision_no_available_numbers_404(
    client, two_tenant_with_memberships, monkeypatch
):
    import telnyx_service

    monkeypatch.setattr(telnyx_service, "_get_voice_app_id", lambda: "voice_app_test")
    monkeypatch.setattr(
        telnyx_service, "_get_messaging_profile_id", lambda: "msg_profile_test"
    )

    async def _empty(**kw):
        return []

    monkeypatch.setattr(telnyx_service, "search_available_numbers", _empty)

    response = client.post(
        "/api/telnyx/numbers/provision",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "area_code": "415"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/telnyx/numbers/assign-existing
# ---------------------------------------------------------------------------


async def test_telnyx_assign_existing(
    client, two_tenant_with_memberships, telnyx_sdk_mock, patched_server_db
):
    response = client.post(
        "/api/telnyx/numbers/assign-existing",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "phone_number": "+15551234567"},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["phone_number"] == "+15551234567"


async def test_telnyx_assign_unknown_number_404(
    client, two_tenant_with_memberships, monkeypatch
):
    import telnyx_service

    monkeypatch.setattr(telnyx_service, "_get_voice_app_id", lambda: "voice_app_test")
    monkeypatch.setattr(
        telnyx_service, "_get_messaging_profile_id", lambda: "msg_profile_test"
    )

    async def _none(phone_number=None):
        return []

    monkeypatch.setattr(telnyx_service, "list_phone_numbers", _none)

    response = client.post(
        "/api/telnyx/numbers/assign-existing",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID, "phone_number": "+15559999999"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/telnyx/numbers/release
# ---------------------------------------------------------------------------


async def test_telnyx_release_no_number_404(
    client, two_tenant_with_memberships, telnyx_sdk_mock
):
    response = client.post(
        "/api/telnyx/numbers/release",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 404


async def test_telnyx_release_happy_path(
    client, two_tenant_with_memberships, telnyx_sdk_mock, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"phone_number_id": "pn_test_123", "phone_number": "+15555550100"}},
    )
    response = client.post(
        "/api/telnyx/numbers/release",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 200
    assert response.json()["released"] is True


# ---------------------------------------------------------------------------
# /api/telnyx/numbers/order/{order_id}
# ---------------------------------------------------------------------------


def test_telnyx_get_order_status(client, mock_clerk, telnyx_sdk_mock):
    response = client.get(
        "/api/telnyx/numbers/order/ord_test_123",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["telnyx"]["status"] == "success"


# ---------------------------------------------------------------------------
# /api/restaurants/{id}/send-menu-sms
# ---------------------------------------------------------------------------


async def test_send_menu_sms_requires_caller_number(
    client, two_tenant_with_memberships
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/send-menu-sms",
        headers={"Authorization": "Bearer tenant_a"},
        json={},
    )
    assert response.status_code == 400


async def test_send_menu_sms_invokes_helper(
    client, two_tenant_with_memberships, monkeypatch
):
    async def _fake_send(**kw):
        return True

    import server

    monkeypatch.setattr(server, "send_menu_sms", _fake_send)

    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/send-menu-sms",
        headers={"Authorization": "Bearer tenant_a"},
        json={"caller_number": "+15555550100"},
    )
    assert response.status_code == 200
    assert response.json()["sent"] is True


# ---------------------------------------------------------------------------
# Square OAuth — /api/integrations/square/{connect, callback}
# ---------------------------------------------------------------------------


async def test_square_connect(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/integrations/square/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert "connect_url" in response.json()
    assert TENANT_A_ID in response.json()["connect_url"]


async def test_square_connect_wrong_tenant_403(client, two_tenant_with_memberships):
    response = client.get(
        f"/api/integrations/square/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert response.status_code == 403


async def test_square_callback_persists_integration(
    client, two_tenant_setup, patched_server_db
):
    response = client.get(
        f"/api/integrations/square/callback?code=AUTH&state={TENANT_A_ID}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True

    integ = await patched_server_db.integrations.find_one(
        {"provider": "square", "restaurant_id": TENANT_A_ID}, {"_id": 0}
    )
    assert integ["auth_code"] == "AUTH"


def test_square_callback_missing_code_400(client):
    response = client.get(f"/api/integrations/square/callback?state={TENANT_A_ID}")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Stripe Connect OAuth
# ---------------------------------------------------------------------------


async def test_stripe_connect_returns_url(
    client, two_tenant_with_memberships, stripe_sdk_mock
):
    response = client.get(
        f"/api/integrations/stripe/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    assert "connect_url" in response.json()


async def test_stripe_callback_success_redirect(
    client, two_tenant_setup, patched_server_db, stripe_sdk_mock
):
    response = client.get(
        f"/api/integrations/stripe/callback?code=AUTH&state={TENANT_A_ID}",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "stripe_connected=true" in response.headers["location"]

    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["stripe_account_id"] == "acct_test_123"


async def test_stripe_callback_error_redirect(client, two_tenant_setup):
    response = client.get(
        f"/api/integrations/stripe/callback?error=access_denied&state={TENANT_A_ID}",
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "stripe_error=true" in response.headers["location"]


async def test_stripe_disconnect(
    client, two_tenant_with_memberships, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {
            "$set": {
                "stripe_account_id": "acct_test_123",
                "stripe_connect_status": "active",
            }
        },
    )
    response = client.post(
        "/api/integrations/stripe/disconnect",
        headers={"Authorization": "Bearer tenant_a"},
        json={"restaurant_id": TENANT_A_ID},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["stripe_connect_status"] == "disconnected"


async def test_stripe_status_endpoint(
    client, two_tenant_with_memberships, patched_server_db
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"stripe_account_id": "acct_x", "stripe_connect_status": "active"}},
    )
    response = client.get(
        f"/api/integrations/stripe/status?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    body = response.json()
    assert body["connected"] is True
    assert body["status"] == "active"


# ---------------------------------------------------------------------------
# /api/restaurants/{id}/orders/{call_sid}/refund
# ---------------------------------------------------------------------------


async def test_refund_order_happy_path(
    client, two_tenant_with_memberships, patched_server_db, stripe_sdk_mock, monkeypatch
):
    # Stub the SMS send so the refund-confirmation branch doesn't blow up.
    import telnyx_service

    class _R:
        success = True
        message_id = "msg_x"
        error_code = None
        error_message = None

    async def _send_sms(**kw):
        return _R()

    monkeypatch.setattr(telnyx_service, "send_sms", _send_sms, raising=False)

    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_account_id": "acct_x"}}
    )
    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA_test",
            "caller_number": "+15555550100",
            "payment_status": "paid",
            "stripe_payment_id": "pi_test_123",
            "order_total": 2500,
        }
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/orders/CA_test/refund",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refunded"] is True
    assert body["refund_id"] == "re_test_123"


async def test_refund_order_already_refunded_400(
    client, two_tenant_with_memberships, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_account_id": "acct_x"}}
    )
    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA_test",
            "payment_status": "refunded",
        }
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/orders/CA_test/refund",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


async def test_refund_order_not_paid_400(
    client, two_tenant_with_memberships, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_account_id": "acct_x"}}
    )
    await patched_server_db.call_records.insert_one(
        {
            "id": "c1",
            "restaurant_id": TENANT_A_ID,
            "call_sid": "CA_test",
            "payment_status": "pending",
        }
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/orders/CA_test/refund",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


async def test_refund_no_connect_account_400(
    client, two_tenant_with_memberships, patched_server_db, stripe_sdk_mock
):
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/orders/CA_test/refund",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 400


async def test_refund_order_not_found_404(
    client, two_tenant_with_memberships, patched_server_db, stripe_sdk_mock
):
    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID}, {"$set": {"stripe_account_id": "acct_x"}}
    )
    response = client.post(
        f"/api/restaurants/{TENANT_A_ID}/orders/nope/refund",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 404
