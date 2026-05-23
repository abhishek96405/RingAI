"""Tenant isolation for ``users`` + ``memberships`` collections.

These two collections cross tenant boundaries by design (a user can belong
to multiple businesses). The isolation rule is different:
- ``memberships`` MUST be filtered by ``user_id == caller`` everywhere
  except admin routes; otherwise one user could list other users'
  memberships and pivot.
- ``users`` documents must not leak email or admin role to other tenants.
"""

from __future__ import annotations

import pytest

from tests._constants import (
    TENANT_A_ID,
    TENANT_A_USER_ID,
    TENANT_B_USER_ID,
)

pytestmark = [pytest.mark.security, pytest.mark.integration]


# ---------------------------------------------------------------------------
# bootstrap returns only the caller's memberships, never another user's.
# ---------------------------------------------------------------------------


async def test_bootstrap_membership_list_scopes_by_user(
    client, patched_server_db, two_tenant_with_memberships
):
    # Tenant B's bootstrap should include only their own membership row.
    r = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 200
    memberships = r.json().get("memberships", [])
    user_ids = {m.get("user_id") for m in memberships}
    assert user_ids == {TENANT_B_USER_ID}
    assert TENANT_A_USER_ID not in user_ids


async def test_bootstrap_does_not_leak_other_users_emails(
    client, patched_server_db, two_tenant_with_memberships
):
    # Seed a third user record with a distinctive email.
    await patched_server_db.users.insert_one(
        {
            "id": "user_unrelated",
            "email": "secret-unrelated@example.test",
            "role": "owner",
        }
    )
    r = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 200
    assert "secret-unrelated@example.test" not in r.text


# ---------------------------------------------------------------------------
# repair-membership is now a no-op (hotfix landed); ensure it never
# fabricates memberships for the calling user across tenants.
# ---------------------------------------------------------------------------


async def test_repair_membership_does_not_steal_tenant_a(
    client, patched_server_db, two_tenant_with_memberships
):
    r = client.post(
        "/api/me/repair-membership",
        headers={"Authorization": "Bearer tenant_b"},
    )
    # The route may have been retired entirely (404) or hardened (200/403).
    # The invariant is: tenant B did NOT acquire a membership on tenant A.
    leaked = await patched_server_db.memberships.find_one(
        {"user_id": TENANT_B_USER_ID, "restaurant_id": TENANT_A_ID}
    )
    assert leaked is None
    # And the status code must NOT be 200 silently with bogus side effects.
    assert r.status_code in (200, 403, 404, 405, 410)


# ---------------------------------------------------------------------------
# Bootstrap with an unauthorized user returns 401, never partial data.
# ---------------------------------------------------------------------------


def test_bootstrap_unauth_returns_401(client):
    r = client.get("/api/me/bootstrap")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Active restaurant in bootstrap is never tenant A's when the caller is B.
# ---------------------------------------------------------------------------


async def test_bootstrap_active_restaurant_is_callers_own(
    client, patched_server_db, two_tenant_with_memberships
):
    r = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer tenant_b"},
    )
    body = r.json()
    active = body.get("active_restaurant")
    if active is not None:
        assert active["id"] != TENANT_A_ID
