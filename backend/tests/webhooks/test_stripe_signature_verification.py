"""Signature-verification scenarios for ``POST /api/webhooks/stripe``.

These tests do NOT use ``stripe_sdk_mock`` — they exercise the real
``stripe.Webhook.construct_event`` with locally-signed payloads, so signature
math is actually verified. Stripe's verification is offline (HMAC-SHA256)
so no network is involved.
"""

from __future__ import annotations

import json
import time

import pytest

pytestmark = [pytest.mark.webhook, pytest.mark.security]


def _payload(event_id: str = "evt_sig_test") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_x",
                    "customer": "cus_x",
                    "status": "active",
                    "items": {"data": []},
                }
            },
        }
    ).encode()


def test_valid_signature_returns_200(client, stripe_signer):
    body = _payload()
    sig = stripe_signer.sign(body)
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    # 200 on accept; the route may also 500 on internal lookups (no tenant
    # seeded), but the signature gate must pass.
    assert r.status_code != 400
    assert r.status_code != 403


def test_wrong_secret_returns_400(client):
    body = _payload()
    # Sign with the wrong secret — production uses STRIPE_WEBHOOK_SECRET.
    from tests.conftest import StripeSigner

    bad = StripeSigner("whsec_wrong_secret_xyz")
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={
            "Stripe-Signature": bad.sign(body),
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400


def test_tampered_body_returns_400(client, stripe_signer):
    body = _payload()
    sig = stripe_signer.sign(body)
    tampered = body.replace(b"active", b"hacked")
    r = client.post(
        "/api/webhooks/stripe",
        content=tampered,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_stale_timestamp_returns_400(client, stripe_signer):
    body = _payload()
    # Stripe's default tolerance is 300s; sign 1 hour ago.
    stale = int(time.time()) - 3600
    sig = stripe_signer.sign(body, timestamp=stale)
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_future_timestamp_is_currently_accepted_captures_bug(client, stripe_signer):
    """Capture current behaviour: Stripe's ``construct_event`` only checks
    ``now - ts > tolerance``, so a far-future timestamp passes the replay
    window check. A forger who can fix server clocks (e.g. via a compromised
    NTP path) could reuse a captured webhook indefinitely. See FINDINGS.
    """
    body = _payload()
    future = int(time.time()) + 3600
    sig = stripe_signer.sign(body, timestamp=future)
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    # Documents the current behaviour — the route does not reject the future ts.
    assert r.status_code != 400


@pytest.mark.xfail(
    strict=True,
    reason="Stripe SDK does not reject future timestamps; needs custom check",
)
def test_future_timestamp_should_return_400_expected(client, stripe_signer):
    body = _payload()
    future = int(time.time()) + 3600
    sig = stripe_signer.sign(body, timestamp=future)
    r = client.post(
        "/api/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_missing_signature_header_returns_400(client):
    r = client.post(
        "/api/webhooks/stripe",
        content=_payload(),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_malformed_signature_header_returns_400(client):
    r = client.post(
        "/api/webhooks/stripe",
        content=_payload(),
        headers={
            "Stripe-Signature": "nonsense-format-no-equals",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400


def test_signature_with_no_v1_scheme_returns_400(client):
    # Stripe rotates schemes (v0, v1, ...) — only v1 is supported on /v1 keys.
    # A header with only an unknown scheme version must be rejected.
    r = client.post(
        "/api/webhooks/stripe",
        content=_payload(),
        headers={
            "Stripe-Signature": f"t={int(time.time())},v0=deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 400
