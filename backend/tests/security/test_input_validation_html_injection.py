"""HTML/script injection defence.

User-controllable fields (menu item name, reservation customer name, etc.)
may end up rendered in dashboards, SMS templates, or the public menu HTML
page. Stored XSS would let one tenant inject script into another tenant's
admin dashboard — though that requires a separate XSS vector, defence in
depth says we should never echo raw HTML to clients.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security, pytest.mark.integration]


_XSS_PAYLOAD = "<script>alert('xss')</script>"


def test_menu_item_name_with_html_is_stored_and_returned_as_text(
    client, patched_server_db, two_tenant_with_memberships
):
    # Create a menu item whose name contains a <script> tag. The API
    # should store the literal text. When fetched, it must appear in JSON
    # as a string — never as parsed HTML in any response Content-Type.
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        json={
            "name": _XSS_PAYLOAD,
            "price": 5,
            "available": True,
            "category": "main",
        },
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code in (200, 201)
    r_list = client.get(
        f"/api/restaurants/{TENANT_A_ID}/menu",
        headers={"Authorization": "Bearer tenant_a"},
    )
    # In a JSON response, the script tag is fine as a string value — what
    # matters is the Content-Type is JSON, not text/html.
    assert "application/json" in r_list.headers.get("Content-Type", "")


async def test_public_menu_html_escapes_item_names(
    client, patched_server_db, two_tenant_with_memberships
):
    """Public menu page HTML-escapes user-controllable item fields
    (FINDINGS resolved — was a stored XSS via <script> in item name)."""
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_xss",
            "restaurant_id": TENANT_A_ID,
            "name": _XSS_PAYLOAD,
            "price": 5,
            "available": True,
            "category": "main",
        }
    )
    r = client.get(f"/menu/{TENANT_A_ID}")
    assert r.status_code == 200
    assert "<script>alert('xss')</script>" not in r.text
    assert "&lt;script&gt;" in r.text


async def test_public_menu_html_escapes_item_names_expected(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.menu_items.insert_one(
        {
            "id": "menu_xss_expected",
            "restaurant_id": TENANT_A_ID,
            "name": _XSS_PAYLOAD,
            "price": 5,
            "available": True,
            "category": "main",
        }
    )
    r = client.get(f"/menu/{TENANT_A_ID}")
    assert r.status_code == 200
    assert "<script>alert('xss')</script>" not in r.text
    assert "&lt;script&gt;" in r.text


async def test_reservation_customer_name_with_html_does_not_crash_dashboard(
    client, patched_server_db, two_tenant_with_memberships
):
    await patched_server_db.reservations.insert_one(
        {
            "id": "rv_xss",
            "restaurant_id": TENANT_A_ID,
            "customer_name": _XSS_PAYLOAD,
            "customer_phone": "+15555550111",
            "party_size": 2,
            "scheduled_date": "2026-06-01",
            "scheduled_time": "19:00",
            "status": "confirmed",
        }
    )
    r = client.get(
        f"/api/restaurants/{TENANT_A_ID}/reservations",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    # JSON serialisation must NOT html-decode the script tag back.
    body_text = r.text
    # The exact escaping is JSON's: < and > stay literal in JSON.
    assert "<script>" in body_text  # stored as text
    # And the Content-Type is JSON, so the browser doesn't execute it.
    assert "application/json" in r.headers.get("Content-Type", "")
