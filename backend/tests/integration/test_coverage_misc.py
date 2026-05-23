"""Miscellaneous coverage padding — utility helpers, error branches, edge cases."""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# get_current_user — real implementation (not the mock_clerk override)
# ---------------------------------------------------------------------------


async def test_get_current_user_real_path_succeeds_with_valid_token(
    client, patched_server_db, monkeypatch
):
    """Hit the un-mocked get_current_user by stubbing verify_clerk_token at the
    auth_helpers module level. Exercises lines 985-1019."""
    import server

    # server.py does `from auth_helpers import verify_clerk_token`, binding the
    # function into server's namespace at module load. Patch THAT binding.

    async def _fake_verify(token):
        return {
            "sub": "user_real_test",
            "email_addresses": [{"email_address": "real@example.test"}],
            "given_name": "Real",
            "family_name": "User",
            "picture": "https://example.test/avatar.png",
        }

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify)

    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer real_token_xyz"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == "user_real_test"
    assert body["user"]["email"] == "real@example.test"

    # User profile should be persisted on first auth (line 1017).
    saved = await patched_server_db.users.find_one({"id": "user_real_test"}, {"_id": 0})
    assert saved is not None
    assert saved["email"] == "real@example.test"


async def test_get_current_user_real_path_returns_401_for_bad_token(
    client, monkeypatch
):
    import server

    # server.py does `from auth_helpers import verify_clerk_token`, binding the
    # function into server's namespace at module load. Patch THAT binding.

    async def _fake_verify(token):
        raise ValueError("invalid token")

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify)

    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer bad_token"},
    )
    assert response.status_code == 401


async def test_get_current_user_email_as_string(client, patched_server_db, monkeypatch):
    """Cover the email string branch (line 1002): claims.get('email') as str."""
    import server

    # server.py does `from auth_helpers import verify_clerk_token`, binding the
    # function into server's namespace at module load. Patch THAT binding.

    async def _fake_verify(token):
        return {"sub": "user_string_email", "email": "plain@example.test"}

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify)

    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer string_email"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "plain@example.test"


async def test_get_current_user_returns_existing_user_doc(
    client, patched_server_db, monkeypatch
):
    """When the user already exists in db.users, the route returns the merged
    doc (line 1013-1015) instead of creating a new one."""
    import server

    # server.py does `from auth_helpers import verify_clerk_token`, binding the
    # function into server's namespace at module load. Patch THAT binding.

    async def _fake_verify(token):
        return {"sub": "user_existing"}

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify)

    await patched_server_db.users.insert_one(
        {
            "id": "user_existing",
            "email": "existing@example.test",
            "previously_seen": True,
        }
    )
    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer existing"},
    )
    assert response.status_code == 200


def test_get_current_user_missing_sub_returns_401(client, monkeypatch):
    """If verify returns claims without 'sub', the route rejects with 401."""
    import server

    # server.py does `from auth_helpers import verify_clerk_token`, binding the
    # function into server's namespace at module load. Patch THAT binding.

    async def _fake_verify(token):
        return {"email": "no-sub@example.test"}

    monkeypatch.setattr(server, "verify_clerk_token", _fake_verify)

    response = client.get(
        "/api/me/bootstrap",
        headers={"Authorization": "Bearer no_sub"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# strip_sensitive_fields / serialize_mongo_doc / get_business_collection
# ---------------------------------------------------------------------------


def test_strip_sensitive_fields_removes_credentials():
    import server

    doc = {
        "name": "X",
        "clover_api_token": "secret",
        "square_access_token": "secret",
        "toast_client_id": "secret",
        "google_calendar_tokens": {"access_token": "x"},
    }
    cleaned = server.strip_sensitive_fields(doc)
    assert "name" in cleaned
    assert "clover_api_token" not in cleaned
    assert "square_access_token" not in cleaned
    assert "toast_client_id" not in cleaned
    assert "google_calendar_tokens" not in cleaned


def test_strip_sensitive_fields_handles_none():
    import server

    assert server.strip_sensitive_fields(None) is None
    assert server.strip_sensitive_fields({}) == {}


def test_get_business_collection_for_each_type(patched_server_db):
    import server

    for biz_type, attr in (
        ("restaurant", "restaurants"),
        ("clinic", "clinics"),
        ("salon", "salons"),
        ("home_services", "home_services"),
        ("legal", "legal"),
    ):
        coll = server.get_business_collection(biz_type)
        assert coll is not None
    # Unknown type falls back to restaurants
    coll = server.get_business_collection("unknown")
    assert coll is not None


def test_get_config_collection_for_each_type(patched_server_db):
    import server

    for biz_type in (
        "restaurant",
        "clinic",
        "salon",
        "home_services",
        "legal",
        "unknown",
    ):
        coll = server.get_config_collection(biz_type)
        assert coll is not None


def test_demo_mode_enabled_reads_env(monkeypatch):
    import server

    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    assert server.demo_mode_enabled() is True
    monkeypatch.setenv("ENABLE_DEMO_MODE", "false")
    assert server.demo_mode_enabled() is False


def test_get_cors_origins_includes_default_dev_ports():
    import server

    origins = server.get_cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://localhost:5173" in origins


def test_get_cors_origins_includes_configured_frontend_url(monkeypatch):
    import server

    monkeypatch.setenv("FRONTEND_URL", "https://app.duuutah.com")
    origins = server.get_cors_origins()
    assert "https://app.duuutah.com" in origins


def test_get_backend_public_url(monkeypatch):
    import server

    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://api.duuutah.com")
    assert server.get_backend_public_url() == "https://api.duuutah.com"
    # Default when unset (in test env it's http://localhost:8000)
    monkeypatch.delenv("BACKEND_PUBLIC_URL", raising=False)
    assert server.get_backend_public_url().startswith("http")


def test_get_frontend_url(monkeypatch):
    import server

    monkeypatch.setenv("FRONTEND_URL", "https://web.duuutah.com")
    assert server.get_frontend_url() == "https://web.duuutah.com"


def test_get_plan_features_starter():
    import server

    feats = server.get_plan_features("STARTER")
    assert feats["monthly_call_limit"] == 500
    assert feats["delivery_enabled"] is False


def test_get_plan_features_pro():
    import server

    feats = server.get_plan_features("PRO")
    assert feats["delivery_enabled"] is True
    assert feats["upsell_enabled"] is True


def test_get_plan_features_unknown_falls_back_to_starter():
    import server

    feats = server.get_plan_features("WHATEVER")
    assert feats["monthly_call_limit"] == 500


def test_get_price_id_to_plan_map(monkeypatch):
    import server

    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter_xyz")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_xyz")
    mapping = server.get_price_id_to_plan_map()
    assert mapping.get("price_starter_xyz") == "STARTER"
    assert mapping.get("price_pro_xyz") == "PRO"


# ---------------------------------------------------------------------------
# auto_detect_timezone — happy path with mocked httpx
# ---------------------------------------------------------------------------


async def test_auto_detect_timezone_returns_none_when_unconfigured(monkeypatch):
    import server

    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    result = await server.auto_detect_timezone("123 Main St")
    assert result is None


async def test_auto_detect_timezone_returns_none_for_empty_address():
    import server

    result = await server.auto_detect_timezone("")
    assert result is None


# ---------------------------------------------------------------------------
# graceful_shutdown_handler / register/unregister WebSocket
# ---------------------------------------------------------------------------


def test_register_unregister_websocket_round_trip():
    import server

    class _WSStub:
        pass

    ws = _WSStub()
    before = len(server._active_websockets)
    server.register_active_websocket(ws)
    assert len(server._active_websockets) == before + 1
    server.unregister_active_websocket(ws)
    assert len(server._active_websockets) == before


def test_is_shutdown_requested():
    import server

    assert isinstance(server.is_shutdown_requested(), bool)


# ---------------------------------------------------------------------------
# Update restaurant — slot_capacity zero handling (line 1158-1160)
# ---------------------------------------------------------------------------


async def test_update_restaurant_zero_int_field_persists(
    client, two_tenant_with_memberships, patched_server_db
):
    """Test that zero values for valid int fields on RestaurantUpdate persist.

    NOTE: the route's special-case loop at server.py:1156-1160 names
    ``slot_capacity``, ``slot_interval_minutes``, ``delivery_minimum`` — but
    NONE of those fields exist on the ``RestaurantUpdate`` model. They live on
    ``RestaurantConfigUpdate`` instead. See FINDINGS — dead defensive code.

    The test uses ``delivery_fee`` which IS a valid RestaurantUpdate field.
    Setting it to 0 should persist via the normal model_dump path because
    ``0 is not None`` is True.
    """
    response = client.put(
        f"/api/restaurants/{TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
        json={"delivery_fee": 0},
    )
    assert response.status_code == 200
    saved = await patched_server_db.restaurants.find_one(
        {"id": TENANT_A_ID}, {"_id": 0}
    )
    assert saved["delivery_fee"] == 0
