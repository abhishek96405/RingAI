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


# Square OAuth token endpoint — production base, matching the hardcoded authorize +
# catalog URLs elsewhere in the codebase. (If sandbox testing is ever needed, make the
# Square base URL env-switchable in one place.)
SQUARE_API_BASE = "https://connect.squareup.com"


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

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SQUARE_API_BASE}/oauth2/token",
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
    api_token = (restaurant or {}).get("clover_api_token", "")
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
    access_token = (restaurant or {}).get("square_access_token", "")

    if not access_token:
        return {"success": False, "error": "Square credentials not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://connect.squareup.com/v2/catalog/list",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                params={"types": "ITEM"},
            )
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


async def sync_menu_from_pos(restaurant_id: str, restaurant: Dict, db) -> Dict[str, Any]:
    """Route to correct POS sync based on restaurant pos_type."""
    pos_type = restaurant.get("pos_type")
    if pos_type == "clover":
        return await sync_menu_from_clover(restaurant_id, db, restaurant)
    elif pos_type == "square":
        return await sync_menu_from_square(restaurant_id, db, restaurant)
    else:
        return {"success": False, "error": "No POS configured for this restaurant"}