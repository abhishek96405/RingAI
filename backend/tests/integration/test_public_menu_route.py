"""Public menu page — regression guard for the A2-2 rate-limit decorator.

A2-2 added `request: Request` + @limiter.limit("30/minute") to public_menu_page.
The slowapi limiter does NOT fire 429s in the mongomock test env (documented by
the strict xfail in tests/security/test_rate_limiting_enforced.py), so we do NOT
assert 429 here. We only assert the route still serves correctly after the
signature change: 200 HTML for a known restaurant, 404 for an unknown id.
"""
from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.integration]


def test_public_menu_page_serves_for_known_restaurant(
    client, two_tenant_with_memberships
):
    r = client.get(f"/menu/{TENANT_A_ID}")
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    assert "text/html" in r.headers.get("content-type", "")


def test_public_menu_page_404_for_unknown_restaurant(
    client, two_tenant_with_memberships
):
    r = client.get("/menu/does-not-exist-xyz")
    assert r.status_code == 404
