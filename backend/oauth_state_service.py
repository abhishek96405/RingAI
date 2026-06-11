"""
OAuth state-token helpers for CSRF protection on Square + Stripe Connect flows.

Tokens are cryptographically random, single-use, and bound to the issuing
user + tenant. Storage is MongoDB with a TTL index for automatic expiry.

Threat model: an attacker who knows a victim restaurant_id must not be able
to complete an OAuth handshake that connects their account to the victim's
tenant. The state token is the binding that prevents this — Stripe / Square
echo it back unchanged, and the callback verifies the token was issued by
us and not yet redeemed.

Storage: db.oauth_states collection.
TTL: 10 minutes (long enough for slow OAuth flows; short enough to bound risk).

Part of Duuutah AI.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


def _get_db():
    # Lazy import to avoid circular import with server.py at module load.
    from server import db

    return db


OAUTH_STATE_TTL_MINUTES = 10


async def issue_oauth_state(
    *,
    restaurant_id: str,
    user_id: str,
    provider: str,
) -> str:
    """Generate, persist, and return a fresh single-use state token.

    Caller passes restaurant_id and user_id derived from the authenticated
    request. The token is stored alongside these so the callback can verify.
    """
    if provider not in ("square", "stripe", "stripe_connect", "google_calendar"):
        raise ValueError(f"unsupported provider: {provider}")

    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)

    db = _get_db()
    await db.oauth_states.insert_one(
        {
            "state": state,
            "restaurant_id": restaurant_id,
            "user_id": user_id,
            "provider": provider,
            "issued_at": now,
            "expires_at": expires_at,
            "consumed": False,
        }
    )
    return state


async def consume_oauth_state(*, state: str, provider: str) -> dict:
    """Look up, validate, and consume a state token.

    Returns the original record's restaurant_id (and other fields) for use
    by the callback handler. Single-use: once consumed, the token cannot be
    redeemed again.

    Raises HTTPException(400) on any failure mode (missing, expired, already
    consumed, provider mismatch). The single 400 surface intentionally does
    not distinguish between failure modes to avoid leaking which states exist.
    """
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state")

    db = _get_db()
    now = datetime.now(timezone.utc)

    record = await db.oauth_states.find_one_and_update(
        {
            "state": state,
            "provider": provider,
            "consumed": False,
            "expires_at": {"$gt": now},
        },
        {"$set": {"consumed": True, "consumed_at": now}},
    )
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    return {
        "restaurant_id": record["restaurant_id"],
        "user_id": record["user_id"],
        "provider": record["provider"],
    }
