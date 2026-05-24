"""Signature verification scenarios for ``POST /api/webhooks/square``.

Square signs ``notification_url + payload`` with the application's webhook
signature key and sends the base64 HMAC-SHA256 digest in
``x-square-hmacsha256-signature``. The handler reconstructs the same
string from ``request.url`` and compares digests with a constant-time
comparison; any mismatch returns 401.

See ``tests/FINDINGS.md`` for the original CRITICAL writeup.

Part of Duuutah AI.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.webhook, pytest.mark.security]


_BODY = (
    b'{"type": "inventory.count.updated",'
    b' "event_id": "evt_sig_test_1",'
    b' "data": {"object": {}}}'
)
_URL = "/api/webhooks/square"
_FULL_URL = "http://testserver/api/webhooks/square"  # TestClient default


def test_valid_signature_returns_200(client, square_signer):
    """A correctly-signed request is accepted with 200."""
    sig = square_signer.sign(_BODY, notification_url=_FULL_URL)
    r = client.post(
        _URL,
        content=_BODY,
        headers={
            "x-square-hmacsha256-signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200


def test_wrong_secret_rejected(client, square_webhook_secret):
    from tests.conftest import SquareSigner

    bad = SquareSigner("wrong-secret").sign(_BODY, notification_url=_FULL_URL)
    r = client.post(
        _URL,
        content=_BODY,
        headers={
            "x-square-hmacsha256-signature": bad,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401


def test_tampered_body_rejected(client, square_signer):
    sig = square_signer.sign(_BODY, notification_url=_FULL_URL)
    tampered = _BODY.replace(b"count.updated", b"count.HACKED")
    r = client.post(
        _URL,
        content=tampered,
        headers={
            "x-square-hmacsha256-signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401


def test_missing_signature_header_rejected(client, square_webhook_secret):
    r = client.post(_URL, content=_BODY, headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_malformed_signature_header_rejected(client, square_webhook_secret):
    r = client.post(
        _URL,
        content=_BODY,
        headers={
            "x-square-hmacsha256-signature": "this-is-not-base64!!!",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401
