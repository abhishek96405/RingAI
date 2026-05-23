"""Square webhook tests for ``POST /api/webhooks/square`` (server.py:5097).

The route under test is currently a stub — it logs the payload size and
returns ``{"received": True}`` without any signature verification, event
dispatch, or idempotency. Test layout:

- The CURRENT behaviour is captured in passing tests (so a future change
  that breaks the stub surfaces as a failure).
- The EXPECTED behaviour (verify signature, handle events, idempotency)
  is captured in ``@pytest.mark.xfail(strict=True)`` tests so the day the
  route grows real verification, the xfail flips and we get loud feedback.

See ``tests/FINDINGS.md`` for the security implications.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.webhook, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Current behaviour: the stub accepts anything.
# ---------------------------------------------------------------------------


def test_square_webhook_returns_200_for_any_payload(client):
    r = client.post(
        "/api/webhooks/square",
        content=b'{"type": "anything", "data": {}}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json() == {"received": True}


def test_square_webhook_accepts_empty_body(client):
    r = client.post("/api/webhooks/square", content=b"")
    assert r.status_code == 200


def test_square_webhook_accepts_malformed_json(client):
    r = client.post(
        "/api/webhooks/square",
        content=b"not-json-at-all",
        headers={"Content-Type": "application/json"},
    )
    # Stub never parses the body, so even garbage passes.
    assert r.status_code == 200


def test_square_webhook_accepts_request_with_no_signature(client):
    """The stub does not enforce ``x-square-hmacsha256-signature``."""
    r = client.post(
        "/api/webhooks/square",
        content=b'{"type": "oauth.authorization.revoked"}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Expected behaviour — captured as strict xfail until the route is fixed.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "CRITICAL: /api/webhooks/square accepts unsigned requests. Must verify "
        "x-square-hmacsha256-signature against SQUARE_WEBHOOK_SIGNATURE_KEY."
    ),
)
def test_square_webhook_rejects_request_without_signature_expected(client):
    r = client.post(
        "/api/webhooks/square",
        content=b'{"type": "oauth.authorization.revoked", "data": {}}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code in (400, 401, 403)


@pytest.mark.xfail(
    strict=True,
    reason="HIGH: route does not verify signatures, so wrong-signature requests are accepted.",
)
def test_square_webhook_rejects_wrong_signature_expected(client, square_signer):
    body = b'{"type": "oauth.authorization.revoked", "data": {}}'
    # Forge a signature with a different secret.
    from tests.conftest import SquareSigner

    forged = SquareSigner("wrong-key-not-in-env").sign(body)
    r = client.post(
        "/api/webhooks/square",
        content=body,
        headers={
            "x-square-hmacsha256-signature": forged,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code in (400, 401, 403)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HIGH: oauth.authorization.revoked is not handled — disconnecting Square in "
        "Square's UI does not propagate to our integrations record."
    ),
)
async def test_square_oauth_authorization_revoked_disconnects_integration_expected(
    client, patched_server_db
):
    await patched_server_db.integrations.insert_one(
        {
            "id": "integ_square_a",
            "restaurant_id": TENANT_A_ID,
            "provider": "square",
            "connected": True,
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
    r = client.post(
        "/api/webhooks/square",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    integ = await patched_server_db.integrations.find_one(
        {"id": "integ_square_a"}, {"_id": 0}
    )
    assert integ["connected"] is False


@pytest.mark.xfail(
    strict=True,
    reason="HIGH: route has no idempotency, so replayed events would be re-processed.",
)
async def test_square_webhook_idempotent_on_replay_expected(client, patched_server_db):
    event = {
        "type": "inventory.count.updated",
        "event_id": "evt_inv_1",
        "data": {"object": {}},
    }
    body = json.dumps(event).encode()
    headers = {"Content-Type": "application/json"}

    r1 = client.post("/api/webhooks/square", content=body, headers=headers)
    r2 = client.post("/api/webhooks/square", content=body, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Once the route stores event_ids: a second replay should NOT cause a
    # second side-effect. We assert the (future) event-id collection has
    # exactly one entry — a meaningful assertion once idempotency lands.
    seen = await patched_server_db["webhook_events"].count_documents(
        {"event_id": "evt_inv_1"}
    )
    assert seen == 1
