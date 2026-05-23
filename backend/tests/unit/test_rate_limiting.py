"""
Unit tests for backend/rate_limiting.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import base64
import json
import time

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# get_rate_limit_key
# ---------------------------------------------------------------------------

def _make_request(headers: dict, path_params: dict = None, query_params: dict = None, client_host: str = "1.2.3.4"):
    """Build a minimal Starlette-style request object."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "path_params": path_params or {},
        "query_string": ("&".join(f"{k}={v}" for k, v in (query_params or {}).items())).encode(),
        "client": (client_host, 12345),
    }
    return Request(scope)


def _jwt_unsigned(sub: str) -> str:
    """Build an unsigned JWT (header.payload.) — verify_signature=False in code path."""
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}."


def test_rate_limit_key_uses_user_when_bearer_present():
    from rate_limiting import get_rate_limit_key

    token = _jwt_unsigned("user_abc")
    req = _make_request({"Authorization": f"Bearer {token}"})
    assert get_rate_limit_key(req) == "user:user_abc"


def test_rate_limit_key_falls_back_to_forwarded_ip():
    from rate_limiting import get_rate_limit_key

    req = _make_request({"X-Forwarded-For": "203.0.113.5, 10.0.0.1"})
    assert get_rate_limit_key(req) == "ip:203.0.113.5"


def test_rate_limit_key_falls_back_to_client_host():
    from rate_limiting import get_rate_limit_key

    req = _make_request({}, client_host="198.51.100.1")
    key = get_rate_limit_key(req)
    assert key.startswith("ip:")


def test_rate_limit_key_handles_malformed_jwt():
    """A non-JWT in the Bearer slot should not crash; fall back to IP."""
    from rate_limiting import get_rate_limit_key

    req = _make_request({"Authorization": "Bearer not-a-jwt-at-all"}, client_host="9.9.9.9")
    key = get_rate_limit_key(req)
    assert key.startswith("ip:")


def test_rate_limit_key_handles_empty_subject():
    """If the JWT decodes but has no 'sub', fall back to IP."""
    from rate_limiting import get_rate_limit_key

    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b'{}').rstrip(b"=").decode()
    token = f"{header}.{payload}."

    req = _make_request({"Authorization": f"Bearer {token}"}, client_host="9.9.9.9")
    key = get_rate_limit_key(req)
    assert key.startswith("ip:")


# ---------------------------------------------------------------------------
# get_restaurant_rate_key
# ---------------------------------------------------------------------------

def test_restaurant_key_prefers_path_param():
    from rate_limiting import get_restaurant_rate_key

    req = _make_request({}, path_params={"restaurant_id": "rest_abc"})
    assert get_restaurant_rate_key(req) == "restaurant:rest_abc"


def test_restaurant_key_falls_back_to_query_param():
    from rate_limiting import get_restaurant_rate_key

    req = _make_request({}, query_params={"restaurant_id": "rest_xyz"})
    assert get_restaurant_rate_key(req) == "restaurant:rest_xyz"


def test_restaurant_key_falls_back_to_user_or_ip():
    from rate_limiting import get_restaurant_rate_key

    req = _make_request({}, client_host="9.9.9.9")
    assert get_restaurant_rate_key(req).startswith("ip:")


# ---------------------------------------------------------------------------
# WebSocket connection limits
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_ws_state(monkeypatch):
    import rate_limiting
    monkeypatch.setattr(rate_limiting, "_ws_connections", {})
    yield


def test_ws_register_increments_and_under_limit_allows(fresh_ws_state):
    from rate_limiting import check_ws_connection_limit, register_ws_connection, get_ws_connection_count

    assert check_ws_connection_limit("rest_1") is True
    register_ws_connection("rest_1")
    assert get_ws_connection_count("rest_1") == 1


def test_ws_limit_blocks_at_max(fresh_ws_state, monkeypatch):
    import rate_limiting
    from rate_limiting import check_ws_connection_limit, register_ws_connection

    monkeypatch.setattr(rate_limiting, "MAX_WS_PER_RESTAURANT", 3)

    for _ in range(3):
        assert check_ws_connection_limit("rest_1") is True
        register_ws_connection("rest_1")

    assert check_ws_connection_limit("rest_1") is False


def test_ws_unregister_decrements(fresh_ws_state):
    from rate_limiting import register_ws_connection, unregister_ws_connection, get_ws_connection_count

    register_ws_connection("rest_1")
    register_ws_connection("rest_1")
    assert get_ws_connection_count("rest_1") == 2

    unregister_ws_connection("rest_1")
    assert get_ws_connection_count("rest_1") == 1

    unregister_ws_connection("rest_1")
    assert get_ws_connection_count("rest_1") == 0


def test_ws_unregister_for_unknown_restaurant_is_noop(fresh_ws_state):
    """Calling unregister on a restaurant that was never registered shouldn't crash."""
    from rate_limiting import unregister_ws_connection
    unregister_ws_connection("never_registered")  # must not raise


def test_ws_get_connection_count_global(fresh_ws_state):
    from rate_limiting import register_ws_connection, get_ws_connection_count

    register_ws_connection("rest_1")
    register_ws_connection("rest_1")
    register_ws_connection("rest_2")
    assert get_ws_connection_count() == 3


# ---------------------------------------------------------------------------
# RateLimitChecker
# ---------------------------------------------------------------------------

def test_rate_checker_under_limit_allows():
    from rate_limiting import RateLimitChecker
    checker = RateLimitChecker()
    for _ in range(5):
        assert checker.check("user_a", limit=10) is True


def test_rate_checker_blocks_at_limit():
    from rate_limiting import RateLimitChecker
    checker = RateLimitChecker()
    for _ in range(3):
        assert checker.check("user_a", limit=3) is True
    assert checker.check("user_a", limit=3) is False


def test_rate_checker_window_expires_resets_count(monkeypatch):
    """When the rolling window elapses, the counter is reset."""
    from rate_limiting import RateLimitChecker
    import time as _time

    checker = RateLimitChecker()
    checker._window_seconds = 60

    base = 1_000_000.0
    seq = iter([base, base + 10, base + 70])
    monkeypatch.setattr(_time, "time", lambda: next(seq))

    assert checker.check("user_a", limit=2) is True   # t=base, count=1
    assert checker.check("user_a", limit=2) is True   # t=base+10, count=2
    # Window expired at t=base+70 → counter resets
    assert checker.check("user_a", limit=2) is True


def test_rate_checker_reset_clears_counter():
    from rate_limiting import RateLimitChecker
    checker = RateLimitChecker()
    checker.check("user_a", limit=2)
    checker.check("user_a", limit=2)
    checker.reset("user_a")
    assert checker.check("user_a", limit=2) is True
    # Reset of non-existent key is a no-op
    checker.reset("never_seen")


# ---------------------------------------------------------------------------
# Rate limit exceeded handler
# ---------------------------------------------------------------------------

def test_rate_limit_exceeded_handler_raises_429():
    from rate_limiting import rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from fastapi import HTTPException

    class _FakeLimit:
        error_message = "test limit"

    req = _make_request({}, client_host="9.9.9.9")
    with pytest.raises(HTTPException) as exc_info:
        rate_limit_exceeded_handler(req, RateLimitExceeded(_FakeLimit()))
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "60"
