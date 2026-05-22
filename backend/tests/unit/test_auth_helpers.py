"""
Unit tests for backend/auth_helpers.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 90% (security-critical).

Note on HTTP mocking: we patch ``httpx.AsyncClient.get`` directly via
monkeypatch rather than using ``respx_mock``. The conftest autouse
``_block_unknown_outbound_http`` wraps ``httpx.AsyncClient.send`` and
raises before respx's lower-level transport patches get a chance to
intercept — see ``tests/FINDINGS.md`` 2026-05-22.
"""
from __future__ import annotations

import base64
import time
from unittest.mock import AsyncMock

import httpx
import pytest
from jose import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers — generate a real RSA keypair so we can mint and verify JWTs
# end-to-end without going near the network.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_numbers = private_key.public_key().public_numbers()

    def _b64url_uint(n: int) -> str:
        length = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    jwk = {
        "kty": "RSA",
        "kid": "test-kid-1",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return {"private_pem": private_pem, "jwk": jwk}


@pytest.fixture(autouse=True)
def _reset_jwks_cache():
    from auth_helpers import _JWKS_CACHE
    _JWKS_CACHE["keys"] = None
    _JWKS_CACHE["expires_at"] = 0.0
    yield
    _JWKS_CACHE["keys"] = None
    _JWKS_CACHE["expires_at"] = 0.0


@pytest.fixture
def patched_clerk_env(monkeypatch, rsa_keypair):
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.clerk.test/.well-known/jwks.json")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://example.clerk.test")
    monkeypatch.delenv("CLERK_JWT_AUDIENCE", raising=False)
    return rsa_keypair


def _sign(claims: dict, keypair: dict) -> str:
    headers = {"kid": keypair["jwk"]["kid"], "alg": "RS256"}
    return jwt.encode(claims, keypair["private_pem"], algorithm="RS256", headers=headers)


def _patch_jwks_response(monkeypatch, jwks_payload, status_code=200):
    """Patch httpx.AsyncClient.get to return a fake JWKS payload.

    This bypasses the conftest autouse _block_unknown_outbound_http guard,
    which only wraps ``send``. ``get`` is the high-level call our code uses.
    """
    response = httpx.Response(
        status_code=status_code,
        json=jwks_payload if status_code == 200 else None,
        request=httpx.Request("GET", "https://example.clerk.test/.well-known/jwks.json"),
    )

    async def fake_get(self, *args, **kwargs):
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


# ---------------------------------------------------------------------------
# _normalize_jwks_url
# ---------------------------------------------------------------------------

def test_normalize_jwks_url_prefers_explicit_env(monkeypatch):
    from auth_helpers import _normalize_jwks_url
    monkeypatch.setenv("CLERK_JWKS_URL", "https://explicit.test/jwks.json")
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://issuer.test")
    assert _normalize_jwks_url() == "https://explicit.test/jwks.json"


def test_normalize_jwks_url_derives_from_issuer(monkeypatch):
    from auth_helpers import _normalize_jwks_url
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.setenv("CLERK_JWT_ISSUER", "https://issuer.test/")
    assert _normalize_jwks_url() == "https://issuer.test/.well-known/jwks.json"


def test_normalize_jwks_url_uses_alt_issuer_env(monkeypatch):
    from auth_helpers import _normalize_jwks_url
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_JWT_ISSUER", raising=False)
    monkeypatch.setenv("CLERK_ISSUER", "https://alt.test")
    assert _normalize_jwks_url() == "https://alt.test/.well-known/jwks.json"


def test_normalize_jwks_url_returns_none_when_unconfigured(monkeypatch):
    from auth_helpers import _normalize_jwks_url
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_JWT_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    assert _normalize_jwks_url() is None


# ---------------------------------------------------------------------------
# get_clerk_jwks
# ---------------------------------------------------------------------------

async def test_get_clerk_jwks_fetches_and_caches(patched_clerk_env, monkeypatch):
    from auth_helpers import get_clerk_jwks, _JWKS_CACHE

    payload = {"keys": [patched_clerk_env["jwk"]]}
    call_count = {"n": 0}

    async def fake_get(self, *args, **kwargs):
        call_count["n"] += 1
        return httpx.Response(
            200,
            json=payload,
            request=httpx.Request("GET", "https://example.clerk.test/.well-known/jwks.json"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await get_clerk_jwks()
    assert result == payload
    assert call_count["n"] == 1

    # Second call should hit the cache, not the network.
    result2 = await get_clerk_jwks()
    assert result2 == payload
    assert call_count["n"] == 1
    assert _JWKS_CACHE["expires_at"] > time.time()


async def test_get_clerk_jwks_raises_when_not_configured(monkeypatch):
    from auth_helpers import get_clerk_jwks
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_JWT_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    with pytest.raises(RuntimeError, match="JWKS configuration missing"):
        await get_clerk_jwks()


async def test_get_clerk_jwks_raises_on_http_error(patched_clerk_env, monkeypatch):
    from auth_helpers import get_clerk_jwks

    async def fake_get(self, *args, **kwargs):
        return httpx.Response(
            500,
            text="boom",
            request=httpx.Request("GET", "https://example.clerk.test/.well-known/jwks.json"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(httpx.HTTPStatusError):
        await get_clerk_jwks()


# ---------------------------------------------------------------------------
# verify_clerk_token — happy path
# ---------------------------------------------------------------------------

async def test_verify_clerk_token_happy_path(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    claims = {
        "iss": "https://example.clerk.test",
        "sub": "user_123",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    token = _sign(claims, patched_clerk_env)

    result = await verify_clerk_token(token)
    assert result["sub"] == "user_123"
    assert result["iss"] == "https://example.clerk.test"


async def test_verify_clerk_token_with_audience(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    monkeypatch.setenv("CLERK_JWT_AUDIENCE", "duuutah-api")
    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    claims = {
        "iss": "https://example.clerk.test",
        "sub": "user_123",
        "aud": "duuutah-api",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    token = _sign(claims, patched_clerk_env)

    result = await verify_clerk_token(token)
    assert result["aud"] == "duuutah-api"


# ---------------------------------------------------------------------------
# verify_clerk_token — failure modes
# ---------------------------------------------------------------------------

async def test_verify_clerk_token_with_expired_token_raises(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    claims = {
        "iss": "https://example.clerk.test",
        "sub": "user_123",
        "exp": int(time.time()) - 60,
        "iat": int(time.time()) - 3600,
    }
    token = _sign(claims, patched_clerk_env)

    with pytest.raises(Exception) as exc_info:
        await verify_clerk_token(token)
    assert "expired" in str(exc_info.value).lower() or "Signature" in str(exc_info.value)


async def test_verify_clerk_token_with_wrong_issuer_raises(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    claims = {
        "iss": "https://attacker.test",
        "sub": "user_123",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    token = _sign(claims, patched_clerk_env)

    with pytest.raises(Exception):
        await verify_clerk_token(token)


async def test_verify_clerk_token_with_unknown_kid_raises(patched_clerk_env, monkeypatch):
    """A token signed with an unknown kid (key rotation gone wrong, or forgery) is rejected."""
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    headers = {"kid": "unknown-kid", "alg": "RS256"}
    claims = {"sub": "user_123", "exp": int(time.time()) + 600}
    token = jwt.encode(claims, patched_clerk_env["private_pem"], algorithm="RS256", headers=headers)

    with pytest.raises(ValueError, match="Matching JWKS key not found"):
        await verify_clerk_token(token)


async def test_verify_clerk_token_with_wrong_audience_raises(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    monkeypatch.setenv("CLERK_JWT_AUDIENCE", "duuutah-api")
    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    claims = {
        "iss": "https://example.clerk.test",
        "sub": "user_123",
        "aud": "wrong-audience",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    token = _sign(claims, patched_clerk_env)

    with pytest.raises(Exception):
        await verify_clerk_token(token)


async def test_verify_clerk_token_with_malformed_token_raises(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    with pytest.raises(Exception):
        await verify_clerk_token("not.a.valid.jwt.token")


async def test_verify_clerk_token_with_empty_token_raises(patched_clerk_env, monkeypatch):
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    with pytest.raises(Exception):
        await verify_clerk_token("")


async def test_verify_clerk_token_with_tampered_signature_raises(patched_clerk_env, monkeypatch):
    """Modifying the payload after signing must invalidate the signature."""
    from auth_helpers import verify_clerk_token

    _patch_jwks_response(monkeypatch, {"keys": [patched_clerk_env["jwk"]]})

    claims = {
        "iss": "https://example.clerk.test",
        "sub": "user_123",
        "exp": int(time.time()) + 600,
    }
    token = _sign(claims, patched_clerk_env)

    header, _, signature = token.split(".")
    tampered_payload = base64.urlsafe_b64encode(
        b'{"sub":"attacker","exp":9999999999}'
    ).rstrip(b"=").decode()
    tampered = f"{header}.{tampered_payload}.{signature}"

    with pytest.raises(Exception):
        await verify_clerk_token(tampered)
