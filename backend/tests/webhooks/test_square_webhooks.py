"""Square webhook tests for ``POST /api/webhooks/square`` (server.py:5128).

The route verifies HMAC-SHA256 signatures against
``SQUARE_WEBHOOK_SIGNATURE_KEY`` (returns 503 if unconfigured, 401 if
the signature is missing or invalid), dispatches the
``oauth.authorization.revoked`` event to mark the integration as
disconnected, and idempotency-checks via the ``webhook_events``
collection so retries are deduplicated.

See ``tests/FINDINGS.md`` for the original CRITICAL writeup.

Part of Duuutah AI.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


_URL = "/api/webhooks/square"
_FULL_URL = "http://testserver/api/webhooks/square"  # TestClient default


# ---------------------------------------------------------------------------
# Signature enforcement — unsigned / wrong-key requests are rejected.
# ---------------------------------------------------------------------------


def test_square_webhook_rejects_request_without_signature(
    client, square_webhook_secret
):
    r = client.post(
        _URL,
        content=b'{"type": "oauth.authorization.revoked", "data": {}}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401


def test_square_webhook_rejects_wrong_signature(client, square_signer):
    from tests.conftest import SquareSigner

    body = b'{"type": "oauth.authorization.revoked", "data": {}}'
    forged = SquareSigner("wrong-key-not-in-env").sign(body, notification_url=_FULL_URL)
    r = client.post(
        _URL,
        content=body,
        headers={
            "x-square-hmacsha256-signature": forged,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Event dispatch — oauth.authorization.revoked disconnects the integration.
# ---------------------------------------------------------------------------


async def test_square_oauth_authorization_revoked_disconnects_integration(
    client, patched_server_db, square_signer
):
    await patched_server_db.integrations.insert_one(
        {
            "id": "integ_square_a",
            "restaurant_id": TENANT_A_ID,
            "provider": "square",
            "status": "connected",
            "merchant_id": "merch_a",
        }
    )
    event = {
        "type": "oauth.authorization.revoked",
        "event_id": "evt_revoked_1",
        "data": {
            "type": "revocation",
            "id": "rev_1",
            "object": {"merchant_id": "merch_a"},
        },
    }
    body = json.dumps(event).encode()
    sig = square_signer.sign(body, notification_url=_FULL_URL)
    r = client.post(
        _URL,
        content=body,
        headers={
            "x-square-hmacsha256-signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    integ = await patched_server_db.integrations.find_one(
        {"id": "integ_square_a"}, {"_id": 0}
    )
    assert integ["status"] == "disconnected"


# ---------------------------------------------------------------------------
# Idempotency — a replayed event_id is deduplicated.
# ---------------------------------------------------------------------------


async def test_square_webhook_idempotent_on_replay(
    client, patched_server_db, square_signer
):
    event = {
        "type": "inventory.count.updated",
        "event_id": "evt_inv_1",
        "data": {"object": {}},
    }
    body = json.dumps(event).encode()
    sig = square_signer.sign(body, notification_url=_FULL_URL)
    headers = {
        "x-square-hmacsha256-signature": sig,
        "Content-Type": "application/json",
    }

    r1 = client.post(_URL, content=body, headers=headers)
    r2 = client.post(_URL, content=body, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    seen = await patched_server_db["webhook_events"].count_documents(
        {"event_id": "evt_inv_1"}
    )
    assert seen == 1
