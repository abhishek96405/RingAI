"""Duuutah AI — webhook security tests (C4).

Tests in this directory exercise the four production webhook endpoints:
- ``POST /api/webhooks/stripe``  (HMAC-SHA256 via ``stripe.Webhook.construct_event``)
- ``POST /api/webhooks/square``  (HMAC-SHA256 — currently NOT verified; see FINDINGS)
- ``POST /api/telnyx/incoming``  (Ed25519 via ``telnyx_service.verify_webhook_signature``)
- ``POST /api/telnyx/sms-inbound`` (Ed25519, same verifier)

Every test signs payloads locally (no network) using the signer fixtures in
the root conftest. No production code is modified.
"""
