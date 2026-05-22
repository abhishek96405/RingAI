"""
Smoke tests for the Duuutah AI test infrastructure itself.

These tests verify:
- conftest.py loads without error and exports its constants
- the async_db fixture (mongomock-motor) is writable and isolated per test
- the two_tenant_setup fixture produces two distinct tenants
- the in-process FastAPI app can be constructed under the patched DB
- the mock_clerk fixture installs a working dependency override so
  Authorization: Bearer tenant_a / tenant_b tokens resolve to deterministic
  claims instead of executing the real Clerk verifier

They are intentionally trivial. Real tests for production modules begin in C2.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


def test_constants_are_defined_and_distinct():
    """Tenant constants used across the suite must be present and distinct."""
    from tests._constants import (
        TENANT_A_ID,
        TENANT_B_ID,
        TENANT_A_USER_ID,
        TENANT_B_USER_ID,
        TENANT_A_ORG_ID,
        TENANT_B_ORG_ID,
    )

    all_ids = [
        TENANT_A_ID, TENANT_B_ID,
        TENANT_A_USER_ID, TENANT_B_USER_ID,
        TENANT_A_ORG_ID, TENANT_B_ORG_ID,
    ]
    assert all(isinstance(x, str) and x for x in all_ids)
    assert TENANT_A_ID != TENANT_B_ID
    assert TENANT_A_USER_ID != TENANT_B_USER_ID
    assert TENANT_A_ORG_ID != TENANT_B_ORG_ID


async def test_async_db_fixture_is_writable(async_db):
    """The async_db fixture provides a working mongomock-motor instance."""
    collection = async_db["smoke_writes"]

    result = await collection.insert_one({"_id": "smoke_1", "value": "ok"})
    assert result.inserted_id == "smoke_1"

    fetched = await collection.find_one({"_id": "smoke_1"})
    assert fetched is not None
    assert fetched["value"] == "ok"

    count = await collection.count_documents({})
    assert count == 1


async def test_async_db_is_isolated_between_tests(async_db):
    """Each test gets a fresh DB — data from the previous test must not leak."""
    collection = async_db["smoke_writes"]
    count = await collection.count_documents({})
    assert count == 0, "async_db fixture must yield a clean DB per test"


async def test_two_tenant_setup_creates_two_distinct_tenants(two_tenant_setup):
    """The two_tenant_setup fixture must produce two non-overlapping tenants.

    The fixture in conftest.py returns a dict shaped::

        {"a": {"restaurant": ..., "user_id": ..., "org_id": ..., "headers": ...},
         "b": {"restaurant": ..., "user_id": ..., "org_id": ..., "headers": ...}}
    """
    assert isinstance(two_tenant_setup, dict)
    assert set(two_tenant_setup.keys()) >= {"a", "b"}

    a = two_tenant_setup["a"]
    b = two_tenant_setup["b"]

    assert a["user_id"] != b["user_id"]
    assert a["org_id"] != b["org_id"]
    assert a["restaurant"]["id"] != b["restaurant"]["id"]
    assert a["headers"] != b["headers"]


def test_app_fixture_constructs(client):
    """The TestClient fixture must build the FastAPI app without crashing."""
    assert client is not None
    response = client.get("/__definitely_not_a_real_route__")
    assert response.status_code in (404, 405)


def test_mock_clerk_installs_dependency_override(app, mock_clerk):
    """mock_clerk must install a FastAPI override for server.get_current_user.

    This is the core thing the fixture needs to do. If the override is not
    on ``app.dependency_overrides``, then ``Depends(get_current_user)`` in
    every route will fall through to the real Clerk verifier and tests in
    C2+ will get 401s instead of deterministic claims.
    """
    import server

    assert server.get_current_user in app.dependency_overrides, (
        "mock_clerk did not register a dependency_overrides entry for "
        "server.get_current_user. The override is the seam that lets test "
        "tokens like 'tenant_a' resolve to fake claims."
    )


async def test_mock_clerk_override_returns_fake_claims(app, mock_clerk):
    """The installed override must return the mapped claims for known tokens
    and raise 401 for unknown tokens — proving the seam works end-to-end."""
    from fastapi import HTTPException

    import server

    override = app.dependency_overrides[server.get_current_user]

    claims_a = await override(authorization="Bearer tenant_a")
    assert claims_a["sub"] == "user_tenant_a"
    assert claims_a["org_id"] == "org_tenant_a"

    with pytest.raises(HTTPException) as exc:
        await override(authorization="Bearer not_a_real_token")
    assert exc.value.status_code == 401
