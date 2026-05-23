"""Secret-in-logs leak tests.

For every sensitive env-var the system handles, exercise the code paths
that touch it and assert the value never appears in any logged record.
This catches sloppy exception handlers (`logger.exception(req.headers)`)
that would otherwise dump the auth token into a SIEM forever.
"""

from __future__ import annotations

import json
import logging
import os

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


def _log_text(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Authorization header must never appear in logs, even on auth failures.
# ---------------------------------------------------------------------------


def test_authorization_header_never_logged_on_401(client, caplog):
    caplog.set_level(logging.DEBUG)
    r = client.get(
        "/api/restaurants/missing_id",
        headers={"Authorization": "Bearer SECRETBEARERTOKENXYZ"},
    )
    assert r.status_code in (401, 404)
    assert "SECRETBEARERTOKENXYZ" not in _log_text(caplog)


def test_authorization_header_never_logged_on_protected_route_success(
    client, two_tenant_with_memberships, caplog
):
    caplog.set_level(logging.DEBUG)
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    # We use "tenant_a" as a fake token; what matters is no Bearer header
    # value leaks. We pick a distinctive token so it can't collide with
    # normal log content.
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer DISTINCTIVE_TOKEN_QQ_99"},
    )
    assert "DISTINCTIVE_TOKEN_QQ_99" not in _log_text(caplog)


# ---------------------------------------------------------------------------
# Stripe secret key never logged on webhook failure path.
# ---------------------------------------------------------------------------


def test_stripe_secret_never_logged_on_webhook_failure(client, caplog):
    caplog.set_level(logging.DEBUG)
    # Send a tampered webhook — the route's exception handler must not
    # print STRIPE_WEBHOOK_SECRET or STRIPE_SECRET_KEY.
    body = json.dumps({"id": "evt_x", "type": "ping", "data": {"object": {}}}).encode()
    client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={
            "Stripe-Signature": "t=0,v1=invalid",
            "Content-Type": "application/json",
        },
    )
    text = _log_text(caplog)
    assert os.environ["STRIPE_WEBHOOK_SECRET"] not in text
    assert os.environ["STRIPE_SECRET_KEY"] not in text


# ---------------------------------------------------------------------------
# Clerk secret never logged.
# ---------------------------------------------------------------------------


def test_clerk_secret_key_never_logged_on_auth_failure(client, caplog):
    caplog.set_level(logging.DEBUG)
    client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer some.fake.jwt.token"},
    )
    assert os.environ["CLERK_SECRET_KEY"] not in _log_text(caplog)


# ---------------------------------------------------------------------------
# Encryption key never logged.
# ---------------------------------------------------------------------------


def test_encryption_key_never_logged_on_any_request(
    client, two_tenant_with_memberships, caplog
):
    caplog.set_level(logging.DEBUG)
    # Hit a route that touches encryption (POS creds save).
    client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        json={
            "provider": "clover",
            "credentials": {"merchant_id": "m", "api_token": "tok"},
        },
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert os.environ["ENCRYPTION_SECRET_KEY"] not in _log_text(caplog)


# ---------------------------------------------------------------------------
# Telnyx API key never logged.
# ---------------------------------------------------------------------------


def test_telnyx_api_key_never_logged_on_provision(
    client, two_tenant_with_memberships, telnyx_sdk_mock, caplog
):
    caplog.set_level(logging.DEBUG)
    client.post(
        "/api/telnyx/numbers/search?area_code=555&country_code=US&limit=1",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert os.environ["TELNYX_API_KEY"] not in _log_text(caplog)


# ---------------------------------------------------------------------------
# Stored OAuth tokens never logged.
# ---------------------------------------------------------------------------


async def test_stored_oauth_token_never_logged_on_status_check(
    client, patched_server_db, two_tenant_with_memberships, caplog
):
    PLAIN_TOKEN = "ya29.PLAINTEXT_OAUTH_TOKEN_DO_NOT_LEAK"
    await patched_server_db.integrations.insert_one(
        {
            "id": "integ_cal_a",
            "restaurant_id": TENANT_A_ID,
            "provider": "google_calendar",
            "connected": True,
            "access_token": PLAIN_TOKEN,
            "refresh_token": "rt-also-secret",
        }
    )
    caplog.set_level(logging.DEBUG)
    client.get(
        f"/api/restaurants/{TENANT_A_ID}/calendar/status",
        headers={"Authorization": "Bearer tenant_a"},
    )
    text = _log_text(caplog)
    assert PLAIN_TOKEN not in text
    assert "rt-also-secret" not in text
