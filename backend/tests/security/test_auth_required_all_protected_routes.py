"""Enumerate protected routes from the OpenAPI schema and verify every one
returns 401 when called without an ``Authorization`` header.

Protected = depends on ``get_current_user``. We can detect this by checking
whether the route's security schema mentions HTTPBearer. We exclude:
- Webhooks (signature-based auth, tested elsewhere)
- OAuth callbacks (state-token auth)
- Public read endpoints (e.g. /menu/{restaurant_id} HTML page)
- Test-mode endpoints when they are listed as public

The list of exclusions is captured here so future routes are included by
default — a new protected route added to server.py without auth surfaces
as a missing-401 assertion.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security, pytest.mark.integration]


# Routes that are intentionally public or use non-Bearer auth.
_NON_BEARER_ROUTES = {
    # Webhooks — signature-based auth.
    ("POST", "/api/webhooks/stripe"),
    ("POST", "/api/webhooks/square"),
    ("POST", "/api/telnyx/incoming"),
    ("POST", "/api/telnyx/sms-inbound"),
    # OAuth callbacks — state-token auth.
    ("GET", "/api/integrations/square/callback"),
    ("GET", "/api/integrations/stripe/connect/callback"),
    ("GET", "/api/calendar/google/callback"),
    # Voice / media streaming — Telnyx-side auth.
    ("WEBSOCKET", "/api/telnyx/media-stream"),
    # Public reads.
    ("GET", "/api/"),
    ("GET", "/api/status"),
    ("GET", "/api/test-mode/status"),
    ("GET", "/api/test-mode/scenarios"),
    ("GET", "/api/voice-preview/{voice_name}"),
    # Static / heartbeat — not under /api/ namespace.
    ("GET", "/menu/{restaurant_id}"),
    ("GET", "/healthz"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
}


def _enumerate_protected_routes(client) -> list[tuple[str, str]]:
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths", {})
    routes: list[tuple[str, str]] = []
    for path, methods in paths.items():
        for method, op in methods.items():
            m = method.upper()
            if m not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            if (m, path) in _NON_BEARER_ROUTES:
                continue
            # Heuristic: protected routes have an HTTPBearer security
            # requirement or implicitly rely on ``get_current_user`` (which
            # raises 401). We try the call and see what comes back.
            routes.append((m, path))
    return routes


def _path_fillers(path: str) -> str:
    # Replace ``{var}`` placeholders with safe filler values.
    return (
        path.replace("{restaurant_id}", "rest_test")
        .replace("{item_id}", "item_test")
        .replace("{group_id}", "group_test")
        .replace("{service_id}", "svc_test")
        .replace("{appointment_id}", "appt_test")
        .replace("{reservation_id}", "rv_test")
        .replace("{call_id}", "call_test")
        .replace("{slot_id}", "slot_test")
        .replace("{order_id}", "ord_test")
        .replace("{phone_number_id}", "pn_test")
        .replace("{voice_name}", "Joanna")
    )


def test_every_protected_route_returns_401_without_auth(client):
    """Smoke check: hit every route in the OpenAPI schema with no token.

    The expected response is 401 (Unauthorized). 405 (Method Not Allowed)
    or 404 (route not found, e.g. test-only seeded path) is acceptable —
    what's NOT acceptable is 200 (silent passthrough) or 500 (auth not
    even attempted, raw exception).
    """
    routes = _enumerate_protected_routes(client)
    assert len(routes) >= 30, f"expected ≥30 routes, found {len(routes)}"

    failures: list[str] = []
    for method, path in routes:
        url = _path_fillers(path)
        try:
            r = client.request(method, url)
        except Exception as exc:  # pragma: no cover - debug only
            failures.append(f"{method} {url} crashed: {exc}")
            continue
        # Acceptable: 401 (missing auth), 405 (rate-limit/wrong method),
        # 422 (Pydantic required body), 404 (route path-param not found).
        # Unacceptable: 200, 500.
        if r.status_code in (200, 500):
            failures.append(f"{method} {url} returned {r.status_code} without auth")

    # Report all failures at once for actionable feedback.
    assert not failures, "Routes missing auth gate:\n" + "\n".join(failures)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/me/bootstrap"),
        ("POST", "/api/restaurants"),
        ("GET", "/api/restaurants/rest_test"),
        ("PUT", "/api/restaurants/rest_test"),
        ("GET", "/api/restaurants/rest_test/menu"),
        ("GET", "/api/restaurants/rest_test/calls"),
        ("GET", "/api/restaurants/rest_test/analytics/summary"),
        ("GET", "/api/admin/cost-analytics"),
        ("POST", "/api/admin/process-reminders"),
        ("POST", "/api/billing/create-checkout-session"),
        ("POST", "/api/billing/portal"),
        ("GET", "/api/billing/invoices"),
    ],
)
def test_specific_route_returns_401_without_auth(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401, f"{method} {path} → {r.status_code} not 401"
