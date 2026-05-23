"""Ed25519 signature verification for Telnyx webhooks.

Both ``/api/telnyx/incoming`` and ``/api/telnyx/sms-inbound`` rely on
``telnyx_service.verify_webhook_signature`` to gate forged requests.
Verification is *skipped* when ``BACKEND_PUBLIC_URL`` contains
``localhost`` or ``127.0.0.1`` (test/dev escape hatch); the
``force_nonlocal_backend_url`` fixture overrides that so we actually
exercise the verifier.

Telnyx signs ``f"{timestamp}|".encode() + payload`` with an Ed25519
private key; the matching public key (raw, base64-encoded) lives in
``TELNYX_PUBLIC_KEY``. The ``telnyx_signer`` fixture generates a fresh
keypair per test and publishes the public half via monkeypatch.
"""

from __future__ import annotations

import json
import time

import pytest

pytestmark = [pytest.mark.webhook, pytest.mark.security]


_INCOMING_BODY = json.dumps(
    {
        "data": {
            "event_type": "call.hangup",
            "id": "evt_sig_test",
            "payload": {"call_control_id": "cc_sig_test"},
            "record_type": "event",
        }
    }
).encode()


def _post(client, path, body, headers):
    h = {"Content-Type": "application/json"}
    h.update(headers)
    return client.post(path, content=body, headers=h)


# ---------------------------------------------------------------------------
# /api/telnyx/incoming
# ---------------------------------------------------------------------------


def test_incoming_valid_signature_returns_200(
    client, telnyx_signer, force_nonlocal_backend_url
):
    sig, ts = telnyx_signer.sign(_INCOMING_BODY)
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 200


def test_incoming_wrong_signature_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    # Sign with a different keypair so the public key in the env doesn't match.
    from tests.conftest import TelnyxSigner

    forger = TelnyxSigner()
    sig, ts = forger.sign(_INCOMING_BODY)
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


def test_incoming_tampered_body_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    sig, ts = telnyx_signer.sign(_INCOMING_BODY)
    tampered = _INCOMING_BODY.replace(b"call.hangup", b"call.HACKED")
    r = _post(
        client,
        "/api/telnyx/incoming",
        tampered,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


def test_incoming_stale_timestamp_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    stale = int(time.time()) - 3600  # 1 hour ago; tolerance is 300s
    sig, ts = telnyx_signer.sign(_INCOMING_BODY, timestamp=stale)
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


def test_incoming_future_timestamp_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    future = int(time.time()) + 3600
    sig, ts = telnyx_signer.sign(_INCOMING_BODY, timestamp=future)
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


def test_incoming_missing_signature_header_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {"telnyx-timestamp": str(int(time.time()))},
    )
    assert r.status_code == 403


def test_incoming_missing_timestamp_header_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    sig, ts = telnyx_signer.sign(_INCOMING_BODY)
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {"telnyx-signature-ed25519": sig},
    )
    assert r.status_code == 403


def test_incoming_malformed_signature_returns_403(
    client, telnyx_signer, force_nonlocal_backend_url
):
    r = _post(
        client,
        "/api/telnyx/incoming",
        _INCOMING_BODY,
        {
            "telnyx-signature-ed25519": "definitely-not-base64-!!!",
            "telnyx-timestamp": str(int(time.time())),
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /api/telnyx/sms-inbound — same verifier, same scenarios.
# ---------------------------------------------------------------------------


_SMS_BODY = json.dumps(
    {
        "data": {
            "event_type": "message.finalized",
            "payload": {"id": "msg_sig_test", "to": [{"status": "delivered"}]},
        }
    }
).encode()


def test_sms_valid_signature_returns_200(
    client, patched_server_db, telnyx_signer, force_nonlocal_backend_url
):
    sig, ts = telnyx_signer.sign(_SMS_BODY)
    r = _post(
        client,
        "/api/telnyx/sms-inbound",
        _SMS_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 200


def test_sms_wrong_signature_returns_403(
    client, patched_server_db, telnyx_signer, force_nonlocal_backend_url
):
    from tests.conftest import TelnyxSigner

    forger = TelnyxSigner()
    sig, ts = forger.sign(_SMS_BODY)
    r = _post(
        client,
        "/api/telnyx/sms-inbound",
        _SMS_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


def test_sms_tampered_body_returns_403(
    client, patched_server_db, telnyx_signer, force_nonlocal_backend_url
):
    sig, ts = telnyx_signer.sign(_SMS_BODY)
    tampered = _SMS_BODY.replace(b"delivered", b"failed!!!")
    r = _post(
        client,
        "/api/telnyx/sms-inbound",
        tampered,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


def test_sms_stale_timestamp_returns_403(
    client, patched_server_db, telnyx_signer, force_nonlocal_backend_url
):
    stale = int(time.time()) - 3600
    sig, ts = telnyx_signer.sign(_SMS_BODY, timestamp=stale)
    r = _post(
        client,
        "/api/telnyx/sms-inbound",
        _SMS_BODY,
        {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Verification skipped when BACKEND_PUBLIC_URL is local (default test mode).
# We capture this behaviour explicitly so the escape hatch doesn't drift.
# ---------------------------------------------------------------------------


def test_signature_skipped_when_backend_url_local(client, telnyx_sdk_mock):
    # Default BACKEND_PUBLIC_URL=http://localhost:8000 — verification skipped.
    # The route accepts the request with NO signature headers.
    body = _INCOMING_BODY
    r = client.post(
        "/api/telnyx/incoming",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
