"""Integration tests for Duuutah AI backend route handlers.

These exercise the FastAPI app in-process via Starlette's TestClient with
the patched in-memory MongoDB (mongomock-motor). Production code is never
modified — all external services (Stripe, Telnyx, Google, Gemini) are stubbed
via fixtures in tests/conftest.py.

Scope (C3):
  - All non-webhook API routes (~91 routes) at server.py
  - Both WebSocket endpoints (/ws/notifications, /api/telnyx/media-stream)
  - HTTP middleware (cloudflare_security_middleware) and startup hooks

Out of scope (deferred to C4):
  - Webhook signature verification: /api/webhooks/stripe, /api/webhooks/square,
    /api/telnyx/incoming, /api/telnyx/sms-inbound
  - Full tenant isolation matrix across all collections × scenarios
"""
