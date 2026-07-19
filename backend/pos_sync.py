"""
POS Menu Sync — Clover & Square
Fetches inventory from connected POS and upserts into db.menu_items.
Uses pos_item_id as the stable key to avoid duplicates.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

import httpx

logger = logging.getLogger(__name__)


async def exchange_square_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange a Square OAuth authorization code for an access token (A5-3).

    Returns Square's token payload (access_token, refresh_token, merchant_id, ...).
    Raises ValueError if Square credentials are unset or the exchange fails.
    """
    import os
    application_id = os.environ.get("SQUARE_APPLICATION_ID", "")
    application_secret = os.environ.get("SQUARE_APPLICATION_SECRET", "")
    if not application_id or not application_secret:
        raise ValueError("Square credentials not configured")

    # Sandbox vs production base — mirrors _send_to_square (gemini_service.py) and the
    # Clover env-switch. OAuth uses the global app environment (no per-restaurant override).
    square_env = os.environ.get("SQUARE_ENVIRONMENT", "sandbox")
    square_base = "https://connect.squareupsandbox.com" if square_env == "sandbox" else "https://connect.squareup.com"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{square_base}/oauth2/token",
            headers={"Content-Type": "application/json"},
            json={
                "client_id": application_id,
                "client_secret": application_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Square token exchange failed: {resp.status_code}")
    return resp.json()


def _clover_oauth_base() -> str:
    """Token/refresh API host for Clover v2 OAuth (server-to-server).

    This is the host for POST /oauth/v2/token and /oauth/v2/refresh — distinct
    from BOTH the browser authorize host (built inline in server.clover_connect:
    sandbox.dev.clover.com / www.clover.com) AND the data-API host in
    sync_menu_from_clover (sandbox.dev.clover.com / api.clover.com).

    Clover's docs conflict on the sandbox host: the OAuth FAQ says
    sandbox.dev.clover.com, but every official curl walkthrough for
    /oauth/v2/token and /oauth/v2/refresh uses the API subdomain
    apisandbox.dev.clover.com — so the official-curl value is the default here
    (sandbox.dev.clover.com 401s "Failed to validate authentication code").

    The PRODUCTION host must be verified before go-live (the FAQ suggests
    www.clover.com); CLOVER_OAUTH_TOKEN_BASE is the override lever for either env.
    """
    import os
    override = os.environ.get("CLOVER_OAUTH_TOKEN_BASE", "").strip()
    if override:
        return override
    clover_env = os.environ.get("CLOVER_ENV", "sandbox")
    return "https://apisandbox.dev.clover.com" if clover_env == "sandbox" else "https://api.clover.com"


async def exchange_clover_code(code: str) -> Dict[str, Any]:
    """Exchange a Clover v2 OAuth authorization code for a token pair.

    Returns Clover's token payload (access_token, access_token_expiration,
    refresh_token, refresh_token_expiration). Raises ValueError if Clover
    credentials are unset or the exchange fails. Never logs the code or tokens.
    """
    import os
    app_id = os.environ.get("CLOVER_APP_ID", "")
    app_secret = os.environ.get("CLOVER_APP_SECRET", "")
    if not app_id or not app_secret:
        raise ValueError("Clover credentials not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_clover_oauth_base()}/oauth/v2/token",
            json={
                "client_id": app_id,
                "client_secret": app_secret,
                "code": code,
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Clover token exchange failed: {resp.status_code}")
    return resp.json()


async def refresh_clover_token(refresh_token: str) -> Dict[str, Any]:
    """Refresh a Clover v2 OAuth access token, returning a NEW rotated token pair.

    POSTs to /oauth/v2/refresh. Returns Clover's token payload (new access_token,
    access_token_expiration, refresh_token, refresh_token_expiration). Both the
    access and refresh tokens rotate and must be persisted. Never logs tokens.
    """
    import os
    app_id = os.environ.get("CLOVER_APP_ID", "")
    app_secret = os.environ.get("CLOVER_APP_SECRET", "")
    if not app_id or not app_secret:
        raise ValueError("Clover credentials not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_clover_oauth_base()}/oauth/v2/refresh",
            json={
                "client_id": app_id,
                "refresh_token": refresh_token,
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Clover token refresh failed: {resp.status_code}")
    return resp.json()


async def get_valid_clover_token(restaurant: Dict, db) -> str:
    """Return a valid Clover access token, refreshing + persisting if near expiry.

    `restaurant` MUST be the already-decrypted doc (callers decrypt via
    decrypt_sensitive_fields first). Manual/legacy tokens (no refresh fields)
    are returned unchanged. On refresh, the rotated pair is persisted encrypted
    to all business collections and the in-memory dict is updated with the
    decrypted values so the caller proceeds with a working token.
    """
    from encryption_utils import encrypt_value

    refresh_token = restaurant.get("clover_refresh_token")
    expiration = restaurant.get("clover_access_token_expiration")

    # Manual/legacy tokens never refresh.
    if not refresh_token or not expiration:
        return restaurant.get("clover_api_token", "")

    now = int(datetime.now(timezone.utc).timestamp())
    # Still comfortably valid (>5 min of runway) — use the current token.
    if int(expiration) - now > 300:
        return restaurant.get("clover_api_token", "")

    try:
        token_data = await refresh_clover_token(refresh_token)
    except Exception as e:
        logger.error(f"[Clover OAuth] token refresh failed: {e}", exc_info=True)
        # Return the stale token; the downstream API call will 401 and surface
        # the real failure rather than masking it here.
        return restaurant.get("clover_api_token", "")

    new_access = token_data.get("access_token", "")
    new_refresh = token_data.get("refresh_token", "")
    new_access_exp = int(token_data.get("access_token_expiration") or 0)
    new_refresh_exp = int(token_data.get("refresh_token_expiration") or 0)

    for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
        await _coll.update_one(
            {"id": restaurant["id"]},
            {"$set": {
                "clover_api_token": encrypt_value(new_access),
                "clover_refresh_token": encrypt_value(new_refresh),
                "clover_access_token_expiration": new_access_exp,
                "clover_refresh_token_expiration": new_refresh_exp,
            }},
        )

    # Update the in-memory (decrypted) dict so the caller works with live values.
    restaurant["clover_api_token"] = new_access
    restaurant["clover_refresh_token"] = new_refresh
    restaurant["clover_access_token_expiration"] = new_access_exp
    restaurant["clover_refresh_token_expiration"] = new_refresh_exp

    return new_access


def _square_oauth_base() -> str:
    """OAuth token/refresh host for Square (sandbox vs production).

    Mirrors the env switch in exchange_square_code / _send_to_square. OAuth uses
    the global app environment (SQUARE_ENVIRONMENT), no per-restaurant override.
    """
    import os
    square_env = os.environ.get("SQUARE_ENVIRONMENT", "sandbox")
    return "https://connect.squareupsandbox.com" if square_env == "sandbox" else "https://connect.squareup.com"


async def refresh_square_token(refresh_token: str) -> Dict[str, Any]:
    """Refresh a Square OAuth access token.

    POSTs to /oauth2/token with grant_type=refresh_token. Returns Square's token
    payload (access_token, expires_at, and — only if it rotated — refresh_token).
    Unlike Clover, Square does NOT rotate the refresh token on each refresh, so
    callers must keep the existing refresh token if the response omits one.
    Never logs the token or secret.
    """
    import os
    application_id = os.environ.get("SQUARE_APPLICATION_ID", "")
    application_secret = os.environ.get("SQUARE_APPLICATION_SECRET", "")
    if not application_id or not application_secret:
        raise ValueError("Square credentials not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{_square_oauth_base()}/oauth2/token",
            headers={"Content-Type": "application/json"},
            json={
                "client_id": application_id,
                "client_secret": application_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    if resp.status_code != 200:
        raise ValueError(f"Square token refresh failed: {resp.status_code}")
    return resp.json()


async def _persist_square_token(restaurant: Dict, db, new_access: str, new_refresh: str, new_expires_at: str) -> None:
    """Persist a refreshed Square token pair encrypted to all business collections
    and update the in-memory (decrypted) restaurant dict so the caller proceeds
    with live values. Expiry is an RFC3339 string, stored plaintext (like Clover's
    integer expirations)."""
    from encryption_utils import encrypt_value

    for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
        await _coll.update_one(
            {"id": restaurant["id"]},
            {"$set": {
                "square_access_token": encrypt_value(new_access),
                "square_refresh_token": encrypt_value(new_refresh),
                "square_token_expires_at": new_expires_at,
            }},
        )

    restaurant["square_access_token"] = new_access
    restaurant["square_refresh_token"] = new_refresh
    restaurant["square_token_expires_at"] = new_expires_at


async def _do_square_refresh(restaurant: Dict, db) -> str:
    """Force a Square token refresh + persist, regardless of expiry.

    Returns the new access token, or "" if there is no stored refresh token or
    the refresh call fails. Used by both the proactive (near-expiry) path and the
    reactive 401-retry path.
    """
    refresh_token = restaurant.get("square_refresh_token")
    if not refresh_token:
        return ""
    try:
        token_data = await refresh_square_token(refresh_token)
    except Exception as e:
        logger.error(f"[Square OAuth] token refresh failed: {e}", exc_info=True)
        return ""

    new_access = token_data.get("access_token", "")
    # Square's refresh token does not rotate on refresh — keep the existing one
    # if the response omits it.
    new_refresh = token_data.get("refresh_token") or refresh_token
    new_expires_at = token_data.get("expires_at") or restaurant.get("square_token_expires_at", "")
    if not new_access:
        return ""
    await _persist_square_token(restaurant, db, new_access, new_refresh, new_expires_at)
    return new_access


async def get_valid_square_token(restaurant: Dict, db) -> str:
    """Return a valid Square access token, refreshing + persisting if near expiry.

    `restaurant` MUST be the already-decrypted doc (same contract as
    get_valid_clover_token). Manual/legacy tokens (no refresh token or no expiry)
    are returned unchanged. Square's expiry is an RFC3339 timestamp STRING (e.g.
    "2026-07-20T00:00:00Z"), not a unix-seconds int like Clover — it is parsed and
    compared with a 5-minute runway. On refresh failure the stale token is
    returned so the downstream call 401s and surfaces the real failure.
    """
    refresh_token = restaurant.get("square_refresh_token")
    expires_at = restaurant.get("square_token_expires_at")

    # Manual/legacy tokens never refresh.
    if not refresh_token or not expires_at:
        return restaurant.get("square_access_token", "")

    # Square returns expires_at as an RFC3339 string, not a unix int.
    try:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("[Square OAuth] unparseable square_token_expires_at; using current token")
        return restaurant.get("square_access_token", "")

    now = datetime.now(timezone.utc)
    # Still comfortably valid (>5 min of runway) — use the current token.
    if (expiry - now).total_seconds() > 300:
        return restaurant.get("square_access_token", "")

    new_access = await _do_square_refresh(restaurant, db)
    if not new_access:
        # Refresh failed — return the stale token; the downstream call will 401
        # and surface the real failure rather than masking it here.
        return restaurant.get("square_access_token", "")
    return new_access


async def square_call_with_refresh(restaurant: Dict, db, request_fn):
    """Run a Square API call with proactive refresh + one reactive 401-retry.

    `request_fn(token)` is an async callable returning an httpx.Response. The
    token is first resolved via get_valid_square_token (proactive refresh near
    expiry). If the call still returns 401 (e.g. the token was revoked early), a
    refresh is forced and the request retried EXACTLY once with the new token. A
    second 401 (or no refresh token) surfaces the original error.
    """
    token = await get_valid_square_token(restaurant, db)
    resp = await request_fn(token)
    if resp.status_code == 401:
        logger.warning("[Square OAuth] 401 from Square — forcing refresh and retrying once")
        new_token = await _do_square_refresh(restaurant, db)
        if new_token and new_token != token:
            resp = await request_fn(new_token)
    return resp


def _map_clover_item(item: Dict, restaurant_id: str) -> Dict:
    """Map a Clover inventory item to Duuutah AI MenuItem format."""
    price_elements = item.get("price", 0)
    category = "Uncategorized"
    cats = item.get("categories", {}).get("elements", [])
    if cats:
        category = cats[0].get("name", "Uncategorized")
    return {
        "id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "pos_item_id": item.get("id"),
        "name": item.get("name", "Unknown Item"),
        "description": item.get("description") or None,
        "category": category,
        "price": price_elements,
        "available": item.get("available", True),
        "allergens": [],
        "modifiers": [],
        "modifier_group_assignments": [],
        "special_instructions_enabled": True,
        "image_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _map_square_item(item: Dict, restaurant_id: str) -> Dict:
    """Map a Square catalog item to Duuutah AI MenuItem format."""
    item_data = item.get("item_data", {})
    variation = item_data.get("variations", [{}])[0]
    variation_data = variation.get("item_variation_data", {})
    price = variation_data.get("price_money", {}).get("amount", 0)
    category = item_data.get("category", {}).get("name", "Uncategorized")
    return {
        "id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "pos_item_id": item.get("id"),
        "name": item_data.get("name", "Unknown Item"),
        "description": item_data.get("description") or None,
        "category": category,
        "price": price,
        "available": True,
        "allergens": [],
        "modifiers": [],
        "modifier_group_assignments": [],
        "special_instructions_enabled": True,
        "image_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def sync_menu_from_clover(restaurant_id: str, db, restaurant: Dict = None) -> Dict[str, Any]:
    """Fetch Clover inventory and upsert into menu_items."""
    import os
    api_token = await get_valid_clover_token(restaurant or {}, db)
    merchant_id = (restaurant or {}).get("clover_merchant_id", "")
    clover_env = (restaurant or {}).get("pos_env") or os.environ.get("CLOVER_ENV", "sandbox")

    if not api_token or not merchant_id:
        return {"success": False, "error": "Clover credentials not configured"}

    base_url = "https://sandbox.dev.clover.com" if clover_env == "sandbox" else "https://api.clover.com"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base_url}/v3/merchants/{merchant_id}/items",
                headers={"Authorization": f"Bearer {api_token}"},
                params={"expand": "categories", "limit": 1000},
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"Clover API error: {resp.status_code}"}

            items = resp.json().get("elements", [])

        synced = 0
        for item in items:
            mapped = _map_clover_item(item, restaurant_id)
            existing = await db.menu_items.find_one(
                {"restaurant_id": restaurant_id, "pos_item_id": mapped["pos_item_id"]},
                {"_id": 0}
            )
            if existing:
                await db.menu_items.update_one(
                    {"restaurant_id": restaurant_id, "pos_item_id": mapped["pos_item_id"]},
                    {"$set": {
                        "name": mapped["name"],
                        "description": mapped["description"],
                        "category": mapped["category"],
                        "price": mapped["price"],
                        "available": mapped["available"],
                    }}
                )
            else:
                await db.menu_items.insert_one(mapped)
            synced += 1

        logger.info(f"[POS Sync] Clover: {synced} items synced for restaurant {restaurant_id}")
        return {"success": True, "synced": synced, "source": "clover"}

    except Exception as e:
        logger.error(f"[POS Sync] Clover sync error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def sync_menu_from_square(restaurant_id: str, db, restaurant: Dict = None) -> Dict[str, Any]:
    """Fetch Square catalog and upsert into menu_items."""
    import os
    restaurant = restaurant or {}

    if not restaurant.get("square_access_token"):
        return {"success": False, "error": "Square credentials not configured"}

    # Sandbox vs production base — mirrors _send_to_square / the Clover env-switch.
    # Per-restaurant pos_env wins, else the global SQUARE_ENVIRONMENT.
    square_env = restaurant.get("pos_env") or os.environ.get("SQUARE_ENVIRONMENT", "sandbox")
    square_base = "https://connect.squareupsandbox.com" if square_env == "sandbox" else "https://connect.squareup.com"

    async def _do_request(token: str):
        # A fresh client per attempt so the 401-retry issues a clean request.
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.get(
                f"{square_base}/v2/catalog/list",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params={"types": "ITEM"},
            )

    try:
        # Proactive OAuth refresh near expiry + one 401-retry (PL-08 / PL-28).
        resp = await square_call_with_refresh(restaurant, db, _do_request)
        if resp.status_code != 200:
            return {"success": False, "error": f"Square API error: {resp.status_code}"}

        items = resp.json().get("objects", [])

        synced = 0
        for item in items:
            mapped = _map_square_item(item, restaurant_id)
            existing = await db.menu_items.find_one(
                {"restaurant_id": restaurant_id, "pos_item_id": mapped["pos_item_id"]},
                {"_id": 0}
            )
            if existing:
                await db.menu_items.update_one(
                    {"restaurant_id": restaurant_id, "pos_item_id": mapped["pos_item_id"]},
                    {"$set": {
                        "name": mapped["name"],
                        "description": mapped["description"],
                        "category": mapped["category"],
                        "price": mapped["price"],
                        "available": mapped["available"],
                    }}
                )
            else:
                await db.menu_items.insert_one(mapped)
            synced += 1

        logger.info(f"[POS Sync] Square: {synced} items synced for restaurant {restaurant_id}")
        return {"success": True, "synced": synced, "source": "square"}

    except Exception as e:
        logger.error(f"[POS Sync] Square sync error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def push_modifier_group_to_clover(
    restaurant: Dict,
    modifier_group: Dict,
    db,
) -> Dict[str, Any]:
    """Push a Duuutah modifier group + its options to Clover inventory.

    `restaurant` MUST be the already-decrypted doc (same contract as
    get_valid_clover_token — callers decrypt via decrypt_sensitive_fields first).

    Steps:
    1. Create the modifier group in Clover (skipped if clover_modifier_group_id set)
    2. Create each option that doesn't yet have a clover_modifier_id
    3. Store the Clover IDs back on the group / options in MongoDB
    4. Associate the group with every inventory-bound menu item that uses it

    Idempotent: options already carrying a clover_modifier_id are skipped, so a
    re-push after an option/name change only creates the new pieces.
    """
    import os

    api_token = await get_valid_clover_token(restaurant, db)
    merchant_id = restaurant.get("clover_merchant_id", "")
    clover_env = restaurant.get("pos_env") or os.environ.get("CLOVER_ENV", "sandbox")

    if not api_token or not merchant_id:
        return {"success": False, "error": "Clover credentials not configured"}

    base_url = "https://sandbox.dev.clover.com" if clover_env == "sandbox" else "https://api.clover.com"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:

            # Step 1 — create or reuse the modifier group in Clover
            clover_group_id = modifier_group.get("clover_modifier_group_id", "")

            if not clover_group_id:
                resp = await client.post(
                    f"{base_url}/v3/merchants/{merchant_id}/modifier_groups",
                    headers=headers,
                    json={
                        "name": modifier_group["name"],
                        "minRequired": modifier_group.get("min_selections", 0),
                        "maxAllowed": modifier_group.get("max_selections", 1),
                        "showByDefault": True,
                    },
                )
                if resp.status_code not in (200, 201):
                    return {"success": False, "error": f"Create modifier group failed: {resp.status_code} {resp.text}"}

                clover_group_id = resp.json().get("id")
                logger.info(f"[Clover] Created modifier group '{modifier_group['name']}' -> {clover_group_id}")

                await db.modifier_groups.update_one(
                    {"id": modifier_group["id"]},
                    {"$set": {"clover_modifier_group_id": clover_group_id}},
                )

            # Step 2 — create each option not already pushed
            for option in modifier_group.get("options", []):
                if option.get("clover_modifier_id"):
                    continue  # already pushed

                resp = await client.post(
                    f"{base_url}/v3/merchants/{merchant_id}/modifier_groups/{clover_group_id}/modifiers",
                    headers=headers,
                    json={
                        "name": option["name"],
                        "price": option.get("price_delta", 0),  # cents
                    },
                )
                if resp.status_code not in (200, 201):
                    logger.warning(f"[Clover] Create modifier '{option['name']}' failed: {resp.status_code}")
                    continue

                clover_mod_id = resp.json().get("id")
                logger.info(f"[Clover] Created modifier '{option['name']}' -> {clover_mod_id}")

                # Positional $ updates the specific option in the array
                await db.modifier_groups.update_one(
                    {"id": modifier_group["id"], "options.id": option["id"]},
                    {"$set": {"options.$.clover_modifier_id": clover_mod_id}},
                )

            # Step 3 — associate the group with every inventory-bound item using it
            items_with_group = await db.menu_items.find(
                {
                    "restaurant_id": modifier_group["restaurant_id"],
                    "modifier_group_assignments.modifier_group_id": modifier_group["id"],
                    "pos_item_id": {"$exists": True, "$ne": ""},
                },
                {"pos_item_id": 1},
            ).to_list(500)

            if items_with_group:
                elements = [
                    {
                        "modifierGroup": {"id": clover_group_id},
                        "item": {"id": item["pos_item_id"]},
                    }
                    for item in items_with_group
                ]
                resp = await client.post(
                    f"{base_url}/v3/merchants/{merchant_id}/item_modifier_groups",
                    headers=headers,
                    json={"elements": elements},
                )
                if resp.status_code not in (200, 201):
                    logger.warning(f"[Clover] Associate modifier group failed: {resp.status_code} {resp.text}")
                else:
                    logger.info(f"[Clover] Associated modifier group {clover_group_id} with {len(elements)} item(s)")

        return {"success": True, "clover_modifier_group_id": clover_group_id}

    except Exception as e:
        logger.error(f"[Clover] Push modifier group failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def sync_menu_from_pos(restaurant_id: str, restaurant: Dict, db) -> Dict[str, Any]:
    """Route to correct POS sync based on restaurant pos_type."""
    pos_type = restaurant.get("pos_type")
    if pos_type == "clover":
        return await sync_menu_from_clover(restaurant_id, db, restaurant)
    elif pos_type == "square":
        return await sync_menu_from_square(restaurant_id, db, restaurant)
    else:
        return {"success": False, "error": "No POS configured for this restaurant"}