"""Clover v2 OAuth — connect, authenticated exchange, token refresh.

Clover v2 OAuth does not support a state parameter, so the connect URL carries
no opaque state token; CSRF protection is instead provided by the authenticated
/exchange endpoint (auth + tenant check via ensure_restaurant_access). These
tests cover the connect URL shape, the exchange happy/error paths, the
get_valid_clover_token refresh/rotation logic, and the two real
test_pos_connection branches that replaced the "not yet implemented" stubs.

Follows the function-level monkeypatch convention (see
security/test_oauth_state_token_security.py), not respx.

Part of Duuutah AI.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import httpx
import pytest

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# 1. clover_connect — env-correct authorize URL, no state param.
# ---------------------------------------------------------------------------


def test_clover_connect_url_sandbox_has_no_state(
    client, two_tenant_with_memberships, monkeypatch
):
    monkeypatch.setenv("CLOVER_ENV", "sandbox")
    r = client.get(
        f"/api/integrations/clover/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    url = r.json()["connect_url"]
    assert url.startswith("https://sandbox.dev.clover.com/oauth/v2/authorize")
    assert "state=" not in url
    assert "client_id=" in url
    assert "redirect_uri=" in url


def test_clover_connect_url_production_host(
    client, two_tenant_with_memberships, monkeypatch
):
    monkeypatch.setenv("CLOVER_ENV", "production")
    r = client.get(
        f"/api/integrations/clover/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    url = r.json()["connect_url"]
    assert url.startswith("https://www.clover.com/oauth/v2/authorize")
    assert "state=" not in url


# ---------------------------------------------------------------------------
# 2. clover_connect — auth + tenant enforcement.
# ---------------------------------------------------------------------------


def test_clover_connect_unauthenticated_401(client, two_tenant_with_memberships):
    r = client.get(f"/api/integrations/clover/connect?restaurant_id={TENANT_A_ID}")
    assert r.status_code == 401


def test_clover_connect_non_member_404(client, two_tenant_with_memberships):
    # tenant_b is not a member of TENANT_A's restaurant.
    r = client.get(
        f"/api/integrations/clover/connect?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 3. exchange — happy path persists encrypted, rotated token pair.
# ---------------------------------------------------------------------------


async def test_clover_exchange_happy_path(
    client, patched_server_db, two_tenant_with_memberships, monkeypatch
):
    import pos_sync
    from encryption_utils import decrypt_value

    async def _fake_exchange(code):
        return {
            "access_token": "clv_at_test",
            "access_token_expiration": 9999999999,
            "refresh_token": "clv_rt_test",
            "refresh_token_expiration": 9999999999,
        }

    monkeypatch.setattr(pos_sync, "exchange_clover_code", _fake_exchange)

    r = client.post(
        "/api/integrations/clover/exchange",
        json={"restaurant_id": TENANT_A_ID, "code": "auth_code_xyz", "merchant_id": "MERCH123"},
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    assert r.json() == {"connected": True, "restaurant_id": TENANT_A_ID}

    integ = await patched_server_db.integrations.find_one(
        {"provider": "clover", "restaurant_id": TENANT_A_ID}
    )
    assert integ["status"] == "connected"
    assert integ["merchant_id"] == "MERCH123"

    doc = await patched_server_db.restaurants.find_one({"id": TENANT_A_ID})
    assert doc["pos_type"] == "clover"
    # Tokens are encrypted at rest, not the raw values.
    assert doc["clover_api_token"] != "clv_at_test"
    assert doc["clover_api_token"].startswith("enc:")
    assert decrypt_value(doc["clover_api_token"]) == "clv_at_test"
    assert decrypt_value(doc["clover_refresh_token"]) == "clv_rt_test"
    assert decrypt_value(doc["clover_merchant_id"]) == "MERCH123"
    # Expirations stay plaintext ints.
    assert doc["clover_access_token_expiration"] == 9999999999
    assert doc["clover_refresh_token_expiration"] == 9999999999


# ---------------------------------------------------------------------------
# 4. exchange — failure + auth paths.
# ---------------------------------------------------------------------------


async def test_clover_exchange_failure_records_error_502(
    client, patched_server_db, two_tenant_with_memberships, monkeypatch
):
    import pos_sync

    async def _boom(code):
        raise ValueError("Clover token exchange failed: 400")

    monkeypatch.setattr(pos_sync, "exchange_clover_code", _boom)

    r = client.post(
        "/api/integrations/clover/exchange",
        json={"restaurant_id": TENANT_A_ID, "code": "bad", "merchant_id": "M1"},
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 502

    integ = await patched_server_db.integrations.find_one(
        {"provider": "clover", "restaurant_id": TENANT_A_ID}
    )
    assert integ["status"] == "error"


def test_clover_exchange_unauthenticated_401(client, two_tenant_with_memberships):
    r = client.post(
        "/api/integrations/clover/exchange",
        json={"restaurant_id": TENANT_A_ID, "code": "c", "merchant_id": "M1"},
    )
    assert r.status_code == 401


def test_clover_exchange_non_member_404(client, two_tenant_with_memberships):
    r = client.post(
        "/api/integrations/clover/exchange",
        json={"restaurant_id": TENANT_A_ID, "code": "c", "merchant_id": "M1"},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 5. get_valid_clover_token — passthrough vs refresh-and-rotate.
# ---------------------------------------------------------------------------


async def test_get_valid_clover_token_legacy_passthrough(async_db, monkeypatch):
    import pos_sync

    async def _must_not_refresh(refresh_token):
        raise AssertionError("refresh_clover_token must not be called for manual tokens")

    monkeypatch.setattr(pos_sync, "refresh_clover_token", _must_not_refresh)

    # No refresh fields → manual/legacy token, returned unchanged.
    restaurant = {"id": TENANT_A_ID, "clover_api_token": "manual_tok"}
    token = await pos_sync.get_valid_clover_token(restaurant, async_db)
    assert token == "manual_tok"


async def test_get_valid_clover_token_far_future_no_refresh(async_db, monkeypatch):
    import pos_sync

    async def _must_not_refresh(refresh_token):
        raise AssertionError("refresh_clover_token must not be called when token is fresh")

    monkeypatch.setattr(pos_sync, "refresh_clover_token", _must_not_refresh)

    now = int(datetime.now(timezone.utc).timestamp())
    restaurant = {
        "id": TENANT_A_ID,
        "clover_api_token": "current_tok",
        "clover_refresh_token": "rt",
        "clover_access_token_expiration": now + 100000,
    }
    token = await pos_sync.get_valid_clover_token(restaurant, async_db)
    assert token == "current_tok"


async def test_get_valid_clover_token_near_expiry_rotates(async_db, monkeypatch):
    import pos_sync
    from encryption_utils import decrypt_value

    refresh_calls = []

    async def _fake_refresh(refresh_token):
        refresh_calls.append(refresh_token)
        return {
            "access_token": "clv_new_at",
            "access_token_expiration": 9999999999,
            "refresh_token": "clv_new_rt",
            "refresh_token_expiration": 9999999999,
        }

    monkeypatch.setattr(pos_sync, "refresh_clover_token", _fake_refresh)

    await async_db.restaurants.insert_one({"id": TENANT_A_ID, "clover_api_token": "enc:old"})

    now = int(datetime.now(timezone.utc).timestamp())
    restaurant = {
        "id": TENANT_A_ID,
        "clover_api_token": "old_tok",
        "clover_refresh_token": "old_rt",
        "clover_access_token_expiration": now + 10,  # within the 300s window
    }
    token = await pos_sync.get_valid_clover_token(restaurant, async_db)

    assert refresh_calls == ["old_rt"]
    assert token == "clv_new_at"
    # In-memory dict updated with decrypted new values.
    assert restaurant["clover_api_token"] == "clv_new_at"
    assert restaurant["clover_refresh_token"] == "clv_new_rt"

    # Rotated pair persisted encrypted, round-trips back.
    doc = await async_db.restaurants.find_one({"id": TENANT_A_ID})
    assert doc["clover_api_token"].startswith("enc:")
    assert decrypt_value(doc["clover_api_token"]) == "clv_new_at"
    assert decrypt_value(doc["clover_refresh_token"]) == "clv_new_rt"
    assert doc["clover_access_token_expiration"] == 9999999999


# ---------------------------------------------------------------------------
# 6. test_pos_connection — real Clover/Square branches (no more placeholders).
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.mark.parametrize("status_code,expected_success", [(200, True), (403, False)])
async def test_pos_test_clover_branch(
    client, patched_server_db, two_tenant_with_memberships, monkeypatch,
    status_code, expected_success,
):
    # /pos/test is rate-limited (5/min, keyed by ip:testclient); the limiter is
    # shared session state, so disable it here — this test exercises the branch
    # logic, not rate limiting.
    import server
    monkeypatch.setattr(server.limiter, "enabled", False)

    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {
            "pos_type": "clover",
            "clover_api_token": "manual_tok",
            "clover_merchant_id": "M1",
        }},
    )

    async def _fake_get(self, url, **kwargs):
        return _FakeResp(status_code)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/test",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is expected_success
    if expected_success:
        assert body["message"] == "Clover connection OK"
    else:
        assert body["error"] == f"Clover API error: {status_code}"


@pytest.mark.parametrize("status_code,expected_success", [(200, True), (401, False)])
async def test_pos_test_square_branch(
    client, patched_server_db, two_tenant_with_memberships, monkeypatch,
    status_code, expected_success,
):
    # See note in test_pos_test_clover_branch — disable the shared rate limiter.
    import server
    monkeypatch.setattr(server.limiter, "enabled", False)

    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {
            "pos_type": "square",
            "square_access_token": "sq_tok",
        }},
    )

    async def _fake_get(self, url, **kwargs):
        return _FakeResp(status_code)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/test",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is expected_success
    if expected_success:
        assert body["message"] == "Square connection OK"
    else:
        assert body["error"] == f"Square API error: {status_code}"


def test_pos_test_placeholders_removed_from_source():
    import server

    src = pathlib.Path(server.__file__).read_text(encoding="utf-8")
    assert "not yet implemented" not in src


# ---------------------------------------------------------------------------
# 7. _clover_oauth_base — token/refresh host (apisandbox by default) + override.
# ---------------------------------------------------------------------------


def test_clover_oauth_base_sandbox_default(monkeypatch):
    # Clover's official curl walkthroughs use the API subdomain for the token
    # and refresh endpoints, even on sandbox.
    monkeypatch.delenv("CLOVER_OAUTH_TOKEN_BASE", raising=False)
    monkeypatch.setenv("CLOVER_ENV", "sandbox")
    import pos_sync

    assert pos_sync._clover_oauth_base() == "https://apisandbox.dev.clover.com"


def test_clover_oauth_base_production_default(monkeypatch):
    monkeypatch.delenv("CLOVER_OAUTH_TOKEN_BASE", raising=False)
    monkeypatch.setenv("CLOVER_ENV", "production")
    import pos_sync

    assert pos_sync._clover_oauth_base() == "https://api.clover.com"


def test_clover_oauth_base_override_wins(monkeypatch):
    monkeypatch.setenv("CLOVER_OAUTH_TOKEN_BASE", "https://custom.clover.example")
    monkeypatch.setenv("CLOVER_ENV", "sandbox")
    import pos_sync

    assert pos_sync._clover_oauth_base() == "https://custom.clover.example"
