"""OAuth state-token security.

server.py uses ``restaurant_id`` directly as the OAuth state for both
Square (server.py:4860) and Stripe Connect (server.py:4909). This pattern
fails RFC 6749 §10.12 (state must be unguessable and single-use):

- Predictable: any attacker who knows a restaurant_id can forge a state.
- No expiry: a captured state can be replayed indefinitely.
- No single-use: the same state can complete the OAuth flow many times.
- No CSRF binding: there's no nonce tying state to the caller's session.

These tests capture the CURRENT behaviour explicitly and the EXPECTED
behaviour as ``xfail(strict=True)`` so the day the security model is
hardened the xfails flip and we get a loud signal.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Current behaviour — Square connect returns a URL with state=<restaurant_id>.
# ---------------------------------------------------------------------------


def test_square_connect_state_is_restaurant_id_captures_bug(
    client, two_tenant_with_memberships
):
    r = client.get(
        f"/api/integrations/square/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    url = r.json()["connect_url"]
    assert f"state={TENANT_A_ID}" in url


def test_square_callback_accepts_predictable_state_captures_bug(
    client, patched_server_db, two_tenant_with_memberships, mock_square
):
    # Pretend the OAuth exchange completed; the callback only needs `code`
    # and `state` — no nonce check, no session binding.
    r = client.get(
        f"/api/integrations/square/callback?code=oauth_code_test&state={TENANT_A_ID}",
    )
    assert r.status_code in (
        200,
        302,
    ), f"callback should accept predictable state, got {r.status_code}"


# ---------------------------------------------------------------------------
# Expected behaviour (xfail strict) — state must be cryptographically random.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "CRITICAL: OAuth state token equals restaurant_id verbatim. An attacker who "
        "guesses a restaurant_id can complete an OAuth flow attaching tokens to that "
        "tenant. State must be a cryptographically-random per-request nonce stored "
        "server-side with TTL."
    ),
)
def test_square_connect_state_should_be_unguessable_expected(
    client, two_tenant_with_memberships
):
    r = client.get(
        f"/api/integrations/square/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    url = r.json()["connect_url"]
    # A safe state is at least 32 chars of url-safe base64.
    import re

    state_match = re.search(r"state=([^&]+)", url)
    assert state_match
    state = state_match.group(1)
    # Expected: state is NOT the restaurant_id; it's an opaque token.
    assert state != TENANT_A_ID
    assert len(state) >= 32


@pytest.mark.xfail(
    strict=True,
    reason=(
        "CRITICAL: OAuth callback does not verify state against a server-side store. "
        "Any replay of a captured ``state=<restaurant_id>`` succeeds."
    ),
)
def test_square_callback_rejects_replayed_state_expected(
    client, patched_server_db, two_tenant_with_memberships, mock_square
):
    # Call the callback twice with the same state — second one should fail
    # because state should be single-use.
    r1 = client.get(f"/api/integrations/square/callback?code=c1&state={TENANT_A_ID}")
    r2 = client.get(f"/api/integrations/square/callback?code=c2&state={TENANT_A_ID}")
    assert r1.status_code in (200, 302)
    assert r2.status_code in (400, 401, 403, 410)


# ---------------------------------------------------------------------------
# Stripe Connect — same state bug pattern.
# ---------------------------------------------------------------------------


def test_stripe_connect_state_is_restaurant_id_captures_bug(
    client, two_tenant_with_memberships, mock_stripe
):
    # Stripe connect URL may be returned by an info endpoint or built
    # inline; we exercise the callback parameters directly here.
    r = client.get(
        f"/api/integrations/stripe/connect/callback?code=c1&state={TENANT_A_ID}",
    )
    # The callback may 200, 302, or 400/422 depending on the validation
    # path — what matters is the state itself is the restaurant_id.
    assert r.status_code != 401


@pytest.mark.xfail(
    strict=True,
    reason="CRITICAL: Stripe Connect callback accepts state=restaurant_id; must be opaque nonce.",
)
def test_stripe_connect_callback_rejects_predictable_state_expected(
    client, two_tenant_with_memberships, mock_stripe
):
    r = client.get(
        f"/api/integrations/stripe/connect/callback?code=c1&state={TENANT_A_ID}",
    )
    assert r.status_code in (400, 401, 403, 410)
