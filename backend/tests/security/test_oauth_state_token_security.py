"""OAuth state-token security.

Square and Stripe Connect OAuth flows use cryptographically random,
single-use state tokens (server.py:4863 + 4919, via
backend/oauth_state_service.py). Tokens are bound to the issuing user +
tenant + provider, persisted with a 10-minute TTL, and atomically
consumed by the callback so replays are rejected.

These tests verify the security properties required by RFC 6749 §10.12:
- State is unguessable (cryptographically random, >=32 chars).
- State is single-use (replay returns 400 / redirects to error).
- State is not the bare restaurant_id.

Part of Duuutah AI.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Square connect — state must be an opaque, unguessable token.
# ---------------------------------------------------------------------------


def test_square_connect_state_is_opaque_token(
    client, two_tenant_with_memberships, monkeypatch
):
    """The /connect URL's state param must be an opaque >=32-char token,
    not the restaurant_id verbatim."""
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app_test")
    monkeypatch.setenv("SQUARE_REDIRECT_URI", "https://example.test/callback")

    r = client.get(
        f"/api/integrations/square/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    url = r.json()["connect_url"]

    state_match = re.search(r"state=([^&]+)", url)
    assert state_match
    state = state_match.group(1)
    assert state != TENANT_A_ID
    assert len(state) >= 32


# ---------------------------------------------------------------------------
# Square callback — state must be single-use; replays are rejected.
# ---------------------------------------------------------------------------


async def test_square_callback_rejects_replayed_state(
    client, patched_server_db, two_tenant_with_memberships, monkeypatch
):
    """A state token may be redeemed exactly once; the second redemption
    must be rejected even with otherwise-valid params."""
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app_test")
    monkeypatch.setenv("SQUARE_REDIRECT_URI", "https://example.test/callback")

    connect = client.get(
        f"/api/integrations/square/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert connect.status_code == 200
    state = parse_qs(urlparse(connect.json()["connect_url"]).query)["state"][0]

    r1 = client.get(f"/api/integrations/square/callback?code=c1&state={state}")
    r2 = client.get(f"/api/integrations/square/callback?code=c2&state={state}")
    assert r1.status_code == 200
    assert r2.status_code == 400


# ---------------------------------------------------------------------------
# Stripe Connect — callback must reject the bare restaurant_id as state.
# ---------------------------------------------------------------------------


async def test_stripe_connect_callback_rejects_predictable_state(
    client, two_tenant_with_memberships
):
    """Submitting the bare restaurant_id as state (the old broken pattern)
    must be rejected — the callback redirects to the error page rather than
    completing the OAuth handshake."""
    r = client.get(
        f"/api/integrations/stripe/callback?code=c1&state={TENANT_A_ID}",
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)
    assert "stripe_error=true" in r.headers["location"]
