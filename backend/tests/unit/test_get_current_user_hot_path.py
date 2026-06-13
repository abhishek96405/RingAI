"""A1-3: get_current_user must not write on the hot path.

get_current_user runs on every authenticated request. It must NOT issue a Mongo
write when the Clerk-sourced profile is unchanged; it must write only the fields
that changed; and a claim absent from a given token must not wipe a stored value.

These exercise the REAL server.get_current_user (the mock_clerk fixture replaces
it wholesale for integration tests, so it can't cover this). They patch
server.verify_clerk_token to return controlled claims and run against the
patched_server_db mongomock database.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


@pytest.fixture
def claims(monkeypatch):
    """Patch the verifier bound in server's namespace to return mutable claims."""
    import server

    data = {
        "sub": "user_hotpath",
        "email": "u@x.test",
        "given_name": "Ada",
        "family_name": "Lovelace",
        "picture": "https://img/ada.png",
    }

    async def _fake_verify(token):
        return dict(data)

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify)
    return data


async def test_creates_user_on_first_call(patched_server_db, claims):
    import server

    user = await server.get_current_user("Bearer t")
    assert user["id"] == "user_hotpath"
    assert user["email"] == "u@x.test"
    assert await server.db.users.find_one({"id": "user_hotpath"}) is not None


async def test_no_write_when_unchanged(patched_server_db, claims):
    import server

    await server.get_current_user("Bearer t")  # create
    before = await server.db.users.find_one({"id": "user_hotpath"})
    await server.get_current_user("Bearer t")  # identical claims -> must not write
    after = await server.db.users.find_one({"id": "user_hotpath"})
    assert after == before  # byte-identical stored doc => no write occurred


async def test_writes_only_changed_fields(patched_server_db, claims):
    import server

    await server.get_current_user("Bearer t")
    before = await server.db.users.find_one({"id": "user_hotpath"}, {"_id": 0})
    claims["given_name"] = "Grace"  # profile changed in Clerk
    user = await server.get_current_user("Bearer t")
    assert user["first_name"] == "Grace"
    after = await server.db.users.find_one({"id": "user_hotpath"}, {"_id": 0})
    assert after["first_name"] == "Grace"
    assert after["email"] == before["email"]          # untouched fields preserved
    assert after["updated_at"] != before["updated_at"]  # a real change bumps it


async def test_absent_claim_does_not_wipe_stored_value(patched_server_db, claims):
    import server

    await server.get_current_user("Bearer t")  # stores image_url
    claims.pop("picture")                      # token now lacks picture
    user = await server.get_current_user("Bearer t")
    assert user["image_url"] == "https://img/ada.png"  # preserved, not nulled
