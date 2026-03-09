import os
import time
from typing import Any, Dict, Optional

import httpx
from jose import jwt

_JWKS_CACHE: dict[str, Any] = {"keys": None, "expires_at": 0.0}


def _normalize_jwks_url() -> Optional[str]:
    explicit = os.getenv("CLERK_JWKS_URL")
    if explicit:
        return explicit
    issuer = os.getenv("CLERK_JWT_ISSUER") or os.getenv("CLERK_ISSUER")
    if issuer:
        return issuer.rstrip("/") + "/.well-known/jwks.json"
    return None


async def get_clerk_jwks() -> Dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["keys"] and _JWKS_CACHE["expires_at"] > now:
        return _JWKS_CACHE["keys"]

    jwks_url = _normalize_jwks_url()
    if not jwks_url:
        raise RuntimeError("Clerk JWKS configuration missing")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        payload = response.json()

    _JWKS_CACHE["keys"] = payload
    _JWKS_CACHE["expires_at"] = now + 3600
    return payload


async def verify_clerk_token(token: str) -> Dict[str, Any]:
    jwks = await get_clerk_jwks()
    issuer = os.getenv("CLERK_JWT_ISSUER") or os.getenv("CLERK_ISSUER")
    audience = os.getenv("CLERK_JWT_AUDIENCE")

    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise ValueError("Matching JWKS key not found")

    options = {"verify_aud": bool(audience)}
    return jwt.decode(
        token,
        key,
        algorithms=[key.get("alg", "RS256"), "RS256"],
        issuer=issuer,
        audience=audience if audience else None,
        options=options,
    )
