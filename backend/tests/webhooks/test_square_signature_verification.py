"""Signature verification scenarios for ``POST /api/webhooks/square``.

Square signs ``notification_url + payload`` with the application's webhook
signature key and sends ``x-square-hmacsha256-signature``. The production
route is currently a stub (no verification), so every test in this file is
``xfail(strict=True)`` — the moment verification lands, the xfails flip
and we get a loud signal that behaviour now matches expectation.

See ``tests/FINDINGS.md`` for the CRITICAL writeup.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.webhook, pytest.mark.security]


_BODY = b'{"type": "inventory.count.updated", "data": {"object": {}}}'
_URL = "/api/webhooks/square"
_FULL_URL = "https://api.duuutah.example/api/webhooks/square"


def test_valid_signature_returns_200(client, square_signer):
    """A correctly-signed request must always succeed — true today (the stub
    accepts everything) and required to remain true once verification lands."""
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


@pytest.mark.xfail(strict=True, reason="Square webhook does not verify signatures yet.")
def test_wrong_secret_rejected_expected(client):
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
    assert r.status_code in (400, 401, 403)


@pytest.mark.xfail(strict=True, reason="Square webhook does not verify signatures yet.")
def test_tampered_body_rejected_expected(client, square_signer):
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
    assert r.status_code in (400, 401, 403)


@pytest.mark.xfail(strict=True, reason="Square webhook does not verify signatures yet.")
def test_missing_signature_header_rejected_expected(client):
    r = client.post(_URL, content=_BODY, headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 401, 403)


@pytest.mark.xfail(strict=True, reason="Square webhook does not verify signatures yet.")
def test_malformed_signature_header_rejected_expected(client):
    r = client.post(
        _URL,
        content=_BODY,
        headers={
            "x-square-hmacsha256-signature": "this-is-not-base64!!!",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code in (400, 401, 403)
