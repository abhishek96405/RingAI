"""Oversize payload rejection.

server.py installs a request-size middleware that rejects bodies above a
configurable threshold (defaults to ~5 MB depending on env). Send a known
oversized body and assert 413 or 400 — never a 500 from a downstream
parser exploding.
"""

from __future__ import annotations

import json

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


def _huge_payload(approx_bytes: int) -> bytes:
    # Build a JSON object whose serialised form is ~approx_bytes long.
    filler = "x" * approx_bytes
    return json.dumps({"junk": filler}).encode()


def test_oversize_post_body_to_menu_route_is_rejected(
    client, two_tenant_with_memberships
):
    body = _huge_payload(11 * 1024 * 1024)  # ~11 MB > middleware cap
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        content=body,
        headers={
            "Authorization": "Bearer tenant_a",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code in (400, 413, 422), f"got {r.status_code}: {r.text[:200]}"


def test_oversize_post_body_to_pos_credentials_is_rejected(
    client, two_tenant_with_memberships
):
    body = _huge_payload(11 * 1024 * 1024)
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        content=body,
        headers={
            "Authorization": "Bearer tenant_a",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code in (400, 413, 422), f"got {r.status_code}: {r.text[:200]}"
