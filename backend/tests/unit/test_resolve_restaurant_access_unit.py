"""A2-8/A3-3: resolve_restaurant_access does the membership+restaurant lookup once.

It returns (full_restaurant, membership) so routes needing business_type and/or the
restaurant doc don't re-query after the access check. ensure_restaurant_access is
refactored to delegate to it; its contract (stripped doc, identical 404s) must hold.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.unit]

_USER = {"id": "user_resolve"}


async def _seed(business_type: str = "restaurant", *, with_restaurant: bool = True) -> None:
    import server

    await server.db.memberships.insert_one(
        {
            "id": "m_resolve",
            "user_id": "user_resolve",
            "restaurant_id": "r_resolve",
            "role": "owner",
            "business_type": business_type,
        }
    )
    if with_restaurant:
        # Seed via the same collection getter the code under test uses.
        await server.get_business_collection(business_type).insert_one(
            {"id": "r_resolve", "name": "Test Biz", "clover_api_token": "secret-token"}
        )


async def test_resolve_returns_full_restaurant_and_membership(patched_server_db):
    import server

    await _seed()
    restaurant, membership = await server.resolve_restaurant_access("r_resolve", _USER)
    assert restaurant["id"] == "r_resolve"
    assert restaurant["clover_api_token"] == "secret-token"  # FULL doc, not stripped
    assert membership["business_type"] == "restaurant"


async def test_ensure_still_returns_stripped_restaurant(patched_server_db):
    import server

    await _seed()
    restaurant = await server.ensure_restaurant_access("r_resolve", _USER)
    assert restaurant["id"] == "r_resolve"
    assert "clover_api_token" not in restaurant  # delegation preserved the strip


async def test_resolve_404_when_no_membership(patched_server_db):
    import server

    with pytest.raises(HTTPException) as exc:
        await server.resolve_restaurant_access("r_resolve", _USER)
    assert exc.value.status_code == 404


async def test_resolve_404_when_membership_but_no_restaurant(patched_server_db):
    import server

    await _seed(with_restaurant=False)
    with pytest.raises(HTTPException) as exc:
        await server.resolve_restaurant_access("r_resolve", _USER)
    assert exc.value.status_code == 404


async def test_resolve_uses_membership_business_type_collection(patched_server_db):
    import server

    await _seed("salon")
    restaurant, membership = await server.resolve_restaurant_access("r_resolve", _USER)
    assert membership["business_type"] == "salon"
    assert restaurant["name"] == "Test Biz"  # fetched from the salons collection
