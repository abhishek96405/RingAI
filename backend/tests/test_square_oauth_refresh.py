"""Square OAuth token refresh + 401-retry resilience (PL-08 / PL-28) and the
PL-09 Cloudflare webhook bypass.

Mirrors the Clover refresh tests (test_clover_oauth.py) but exercises the
Square-specific differences: expires_at is an RFC3339 timestamp STRING (not a
unix int), and Square's refresh token does NOT rotate on every refresh.

Follows the function-level monkeypatch convention (see test_clover_oauth.py).

Part of Duuutah AI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

pytestmark = [pytest.mark.unit]

RID = "rest_sq"


def _rfc3339(delta_seconds: int) -> str:
    """An RFC3339 expiry string `delta_seconds` from now (Square's format)."""
    dt = datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)
    return dt.isoformat().replace("+00:00", "Z")


def _resp(status_code, json=None):
    return httpx.Response(status_code, json=json or {}, request=httpx.Request("GET", "https://x"))


# ---------------------------------------------------------------------------
# refresh_square_token — request shape + error handling.
# ---------------------------------------------------------------------------


async def test_refresh_square_token_posts_grant_type_refresh(monkeypatch):
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app")
    monkeypatch.setenv("SQUARE_APPLICATION_SECRET", "secret")
    monkeypatch.setenv("SQUARE_ENVIRONMENT", "sandbox")
    import pos_sync

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"access_token": "sq_new", "expires_at": _rfc3339(2592000)})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    out = await pos_sync.refresh_square_token("the_rt")
    assert out["access_token"] == "sq_new"
    assert "connect.squareupsandbox.com" in captured["url"]
    assert captured["url"].endswith("/oauth2/token")
    assert captured["json"]["grant_type"] == "refresh_token"
    assert captured["json"]["refresh_token"] == "the_rt"


async def test_refresh_square_token_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app")
    monkeypatch.setenv("SQUARE_APPLICATION_SECRET", "secret")
    import pos_sync

    async def fake_post(self, url, **kwargs):
        return httpx.Response(401, text="invalid")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(ValueError):
        await pos_sync.refresh_square_token("bad_rt")


# ---------------------------------------------------------------------------
# get_valid_square_token — passthrough vs proactive refresh.
# ---------------------------------------------------------------------------


async def test_get_valid_square_token_legacy_passthrough(async_db, monkeypatch):
    import pos_sync

    async def _must_not_refresh(rt):
        raise AssertionError("refresh_square_token must not be called for manual tokens")

    monkeypatch.setattr(pos_sync, "refresh_square_token", _must_not_refresh)

    # No refresh token → manual/legacy token, returned unchanged.
    restaurant = {"id": RID, "square_access_token": "manual_tok"}
    token = await pos_sync.get_valid_square_token(restaurant, async_db)
    assert token == "manual_tok"


async def test_get_valid_square_token_far_future_no_refresh(async_db, monkeypatch):
    import pos_sync

    async def _must_not_refresh(rt):
        raise AssertionError("refresh must not be called when token is fresh")

    monkeypatch.setattr(pos_sync, "refresh_square_token", _must_not_refresh)

    # Expires in 2 days → comfortably valid.
    restaurant = {
        "id": RID,
        "square_access_token": "current_tok",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(2 * 24 * 3600),
    }
    token = await pos_sync.get_valid_square_token(restaurant, async_db)
    assert token == "current_tok"


async def test_get_valid_square_token_near_expiry_refreshes_and_persists(async_db, monkeypatch):
    import pos_sync
    from encryption_utils import decrypt_value

    new_exp = _rfc3339(2592000)
    refresh_calls = []

    async def _fake_refresh(rt):
        refresh_calls.append(rt)
        # Square rotates the refresh token here (exercise the rotation branch).
        return {"access_token": "sq_new_at", "refresh_token": "sq_new_rt", "expires_at": new_exp}

    monkeypatch.setattr(pos_sync, "refresh_square_token", _fake_refresh)

    await async_db.restaurants.insert_one({"id": RID, "square_access_token": "enc:old"})

    restaurant = {
        "id": RID,
        "square_access_token": "old_tok",
        "square_refresh_token": "old_rt",
        "square_token_expires_at": _rfc3339(120),  # 2 min → within 5-min window
    }
    token = await pos_sync.get_valid_square_token(restaurant, async_db)

    assert refresh_calls == ["old_rt"]
    assert token == "sq_new_at"
    # In-memory dict updated with decrypted new values.
    assert restaurant["square_access_token"] == "sq_new_at"
    assert restaurant["square_refresh_token"] == "sq_new_rt"
    assert restaurant["square_token_expires_at"] == new_exp

    # Persisted encrypted, round-trips back. Expiry stays plaintext string.
    doc = await async_db.restaurants.find_one({"id": RID})
    assert doc["square_access_token"].startswith("enc:")
    assert decrypt_value(doc["square_access_token"]) == "sq_new_at"
    assert decrypt_value(doc["square_refresh_token"]) == "sq_new_rt"
    assert doc["square_token_expires_at"] == new_exp


async def test_get_valid_square_token_keeps_refresh_token_when_not_rotated(async_db, monkeypatch):
    """Square does not rotate the refresh token on every refresh — when the
    response omits one, the existing refresh token must be preserved."""
    import pos_sync
    from encryption_utils import decrypt_value

    async def _fake_refresh(rt):
        # No refresh_token in the response (Square's typical behavior).
        return {"access_token": "sq_new_at", "expires_at": _rfc3339(2592000)}

    monkeypatch.setattr(pos_sync, "refresh_square_token", _fake_refresh)
    await async_db.restaurants.insert_one({"id": RID, "square_access_token": "enc:old"})

    restaurant = {
        "id": RID,
        "square_access_token": "old_tok",
        "square_refresh_token": "keep_this_rt",
        "square_token_expires_at": _rfc3339(120),
    }
    token = await pos_sync.get_valid_square_token(restaurant, async_db)

    assert token == "sq_new_at"
    assert restaurant["square_refresh_token"] == "keep_this_rt"
    doc = await async_db.restaurants.find_one({"id": RID})
    assert decrypt_value(doc["square_refresh_token"]) == "keep_this_rt"


async def test_get_valid_square_token_refresh_failure_returns_stale(async_db, monkeypatch):
    import pos_sync

    async def _boom(rt):
        raise ValueError("Square token refresh failed: 400")

    monkeypatch.setattr(pos_sync, "refresh_square_token", _boom)

    restaurant = {
        "id": RID,
        "square_access_token": "stale_tok",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(60),  # near expiry → tries refresh
    }
    # Refresh fails → stale token returned, no raise.
    token = await pos_sync.get_valid_square_token(restaurant, async_db)
    assert token == "stale_tok"


async def test_get_valid_square_token_unparseable_expiry_returns_current(async_db, monkeypatch):
    import pos_sync

    async def _must_not_refresh(rt):
        raise AssertionError("refresh must not be called on an unparseable expiry")

    monkeypatch.setattr(pos_sync, "refresh_square_token", _must_not_refresh)

    restaurant = {
        "id": RID,
        "square_access_token": "current_tok",
        "square_refresh_token": "rt",
        "square_token_expires_at": "not-a-timestamp",
    }
    token = await pos_sync.get_valid_square_token(restaurant, async_db)
    assert token == "current_tok"


# ---------------------------------------------------------------------------
# square_call_with_refresh — proactive refresh + exactly-one 401 retry (PL-28).
# ---------------------------------------------------------------------------


async def test_square_401_triggers_one_refresh_and_retry(async_db, monkeypatch):
    import pos_sync

    refresh_calls = []

    async def _fake_refresh(rt):
        refresh_calls.append(rt)
        return {"access_token": "sq_fresh", "expires_at": _rfc3339(2592000)}

    monkeypatch.setattr(pos_sync, "refresh_square_token", _fake_refresh)
    await async_db.restaurants.insert_one({"id": RID, "square_access_token": "enc:old"})

    restaurant = {
        "id": RID,
        "square_access_token": "old_tok",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(2 * 24 * 3600),  # NOT near expiry
    }

    tokens_used = []

    async def request_fn(token):
        tokens_used.append(token)
        if len(tokens_used) == 1:
            return _resp(401)  # token revoked early
        return _resp(200, json={"objects": []})

    resp = await pos_sync.square_call_with_refresh(restaurant, async_db, request_fn)

    assert resp.status_code == 200
    # No proactive refresh (token wasn't near expiry); exactly one reactive refresh.
    assert refresh_calls == ["rt"]
    # First attempt with the old token, retry with the refreshed token. Exactly one retry.
    assert tokens_used == ["old_tok", "sq_fresh"]


async def test_square_second_401_surfaces_error_only_one_retry(async_db, monkeypatch):
    import pos_sync

    async def _fake_refresh(rt):
        return {"access_token": "sq_fresh", "expires_at": _rfc3339(2592000)}

    monkeypatch.setattr(pos_sync, "refresh_square_token", _fake_refresh)
    await async_db.restaurants.insert_one({"id": RID, "square_access_token": "enc:old"})

    restaurant = {
        "id": RID,
        "square_access_token": "old_tok",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(2 * 24 * 3600),
    }

    tokens_used = []

    async def request_fn(token):
        tokens_used.append(token)
        return _resp(401)  # always 401

    resp = await pos_sync.square_call_with_refresh(restaurant, async_db, request_fn)

    assert resp.status_code == 401
    # Exactly one retry: original attempt + one retry, never a loop.
    assert len(tokens_used) == 2


async def test_square_401_without_refresh_token_does_not_retry(async_db, monkeypatch):
    import pos_sync

    async def _must_not_refresh(rt):
        raise AssertionError("no refresh token → must not attempt a refresh")

    monkeypatch.setattr(pos_sync, "refresh_square_token", _must_not_refresh)

    restaurant = {"id": RID, "square_access_token": "manual_tok"}  # no refresh token

    tokens_used = []

    async def request_fn(token):
        tokens_used.append(token)
        return _resp(401)

    resp = await pos_sync.square_call_with_refresh(restaurant, async_db, request_fn)
    assert resp.status_code == 401
    assert tokens_used == ["manual_tok"]  # no retry


# ---------------------------------------------------------------------------
# Wiring — both Square call paths go through get_valid_square_token.
# ---------------------------------------------------------------------------


async def test_sync_menu_from_square_routes_through_get_valid_token(async_db, monkeypatch):
    import pos_sync

    async def _fake_refresh(rt):
        return {"access_token": "sq_synced", "expires_at": _rfc3339(2592000)}

    monkeypatch.setattr(pos_sync, "refresh_square_token", _fake_refresh)
    await async_db.restaurants.insert_one({"id": RID, "square_access_token": "enc:old"})

    used = []

    async def fake_get(self, url, **kwargs):
        used.append((kwargs.get("headers") or {}).get("Authorization"))
        return httpx.Response(200, json={"objects": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    restaurant = {
        "id": RID,
        "square_access_token": "old_tok",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(120),  # near expiry → refresh first
    }
    result = await pos_sync.sync_menu_from_square(RID, async_db, restaurant=restaurant)
    assert result["success"] is True
    # The catalog GET carried the refreshed token, proving it went through
    # get_valid_square_token.
    assert used == ["Bearer sq_synced"]


async def test_send_to_square_routes_through_get_valid_token(async_db, monkeypatch):
    import pos_sync
    from gemini_service import _send_to_square, LiveOrder, OrderItem

    async def _fake_refresh(rt):
        return {"access_token": "sq_pushed", "expires_at": _rfc3339(2592000)}

    monkeypatch.setattr(pos_sync, "refresh_square_token", _fake_refresh)
    await async_db.restaurants.insert_one({"id": RID, "square_access_token": "enc:old"})

    used = []

    async def fake_post(self, url, **kwargs):
        used.append((kwargs.get("headers") or {}).get("Authorization"))
        return httpx.Response(200, json={"order": {"id": "sq_1"}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = LiveOrder(
        restaurant_id=RID, call_sid="call_abcd1234", caller_number="+15551234567",
        customer_name="Joe", order_type="pickup", delivery_address="",
        special_instructions="",
    )
    order.items.append(OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                                 unit_price=1299, quantity=1))

    restaurant = {
        "id": RID,
        "square_access_token": "old_tok",
        "square_location_id": "loc_1",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(120),  # near expiry → refresh first
    }
    out = await _send_to_square(order, restaurant, async_db)
    assert out["success"] is True
    assert used == ["Bearer sq_pushed"]


async def test_send_to_square_db_none_uses_raw_token_no_refresh(monkeypatch):
    """Legacy path: db=None uses the raw token verbatim and never refreshes."""
    import pos_sync
    from gemini_service import _send_to_square, LiveOrder, OrderItem

    def _must_not_refresh(*a, **k):
        raise AssertionError("refresh must not be called when db is None")

    monkeypatch.setattr(pos_sync, "refresh_square_token", _must_not_refresh)

    used = []

    async def fake_post(self, url, **kwargs):
        used.append((kwargs.get("headers") or {}).get("Authorization"))
        return httpx.Response(200, json={"order": {"id": "sq_1"}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    order = LiveOrder(
        restaurant_id=RID, call_sid="call_abcd1234", caller_number="+15551234567",
        customer_name="Joe", order_type="pickup", delivery_address="",
        special_instructions="",
    )
    order.items.append(OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                                 unit_price=1299, quantity=1))

    out = await _send_to_square(order, {
        "square_access_token": "raw_tok",
        "square_location_id": "loc_1",
        "square_refresh_token": "rt",
        "square_token_expires_at": _rfc3339(1),  # would be near-expiry IF db passed
    })  # db defaults to None
    assert out["success"] is True
    assert used == ["Bearer raw_tok"]


# ---------------------------------------------------------------------------
# PL-09 — Square webhook path is exempt from the Cloudflare-origin check.
# ---------------------------------------------------------------------------


def test_square_webhook_in_cf_bypass_prefixes():
    import server
    assert "/api/webhooks/square" in server.CF_BYPASS_PREFIXES
