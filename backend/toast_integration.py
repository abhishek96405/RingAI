"""
Toast POS Integration for RingAI

Provides:
- OAuth2 token management with caching
- Menu catalog sync
- Order dispatch
- Kitchen queue depth monitoring

Part of Prompt 7 - Unified POS Integration

Environment Variables:
- TOAST_CLIENT_ID: OAuth client ID
- TOAST_CLIENT_SECRET: OAuth client secret
- TOAST_ENV: 'sandbox' or 'production' (default: sandbox)
"""
import os
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)

# Toast API base URLs
TOAST_SANDBOX_URL = "https://api.toasttab.com"
TOAST_PRODUCTION_URL = "https://api.toasttab.com"

# Token cache: restaurant_id -> {access_token, expires_at}
_token_cache: Dict[str, Dict[str, Any]] = {}


def _get_toast_base_url(env: str = None) -> str:
    """Get Toast API base URL based on environment."""
    env = env or os.environ.get("TOAST_ENV", "sandbox")
    # Toast uses same URL for both, but we keep the pattern for future-proofing
    return TOAST_SANDBOX_URL if env == "sandbox" else TOAST_PRODUCTION_URL


async def get_toast_access_token(
    restaurant_id: str,
    client_id: str,
    client_secret: str,
    restaurant_guid: str,
    env: str = "sandbox"
) -> Optional[str]:
    """
    Get Toast OAuth2 access token with caching.
    Tokens are cached per-restaurant and refreshed before expiry.
    
    Returns:
        Access token string, or None if authentication fails
    """
    cache_key = f"{restaurant_id}:{restaurant_guid}"
    
    # Check cache
    if cache_key in _token_cache:
        cached = _token_cache[cache_key]
        # Refresh if within 5 minutes of expiry
        if cached.get("expires_at", 0) > time.time() + 300:
            return cached.get("access_token")
    
    # Get new token
    base_url = _get_toast_base_url(env)
    token_url = f"{base_url}/authentication/v1/authentication/login"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                token_url,
                json={
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "userAccessType": "TOAST_MACHINE_CLIENT"
                },
                headers={
                    "Content-Type": "application/json",
                    "Toast-Restaurant-External-ID": restaurant_guid
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Toast auth failed: {response.status_code} {response.text[:200]}")
                return None
            
            data = response.json()
            access_token = data.get("token", {}).get("accessToken")
            # Toast tokens typically expire in 1 hour
            expires_in = data.get("token", {}).get("expiresIn", 3600)
            
            if access_token:
                _token_cache[cache_key] = {
                    "access_token": access_token,
                    "expires_at": time.time() + expires_in
                }
                logger.info(f"Toast token obtained for restaurant {restaurant_id}")
                return access_token
            
            return None
            
    except Exception as e:
        logger.error(f"Toast auth error: {e}")
        return None


def clear_toast_token_cache(restaurant_id: str = None):
    """Clear cached Toast tokens."""
    global _token_cache
    if restaurant_id:
        keys_to_remove = [k for k in _token_cache if k.startswith(f"{restaurant_id}:")]
        for k in keys_to_remove:
            del _token_cache[k]
    else:
        _token_cache = {}


async def sync_menu_from_toast(
    restaurant_id: str,
    db,
    restaurant: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Sync menu items from Toast POS to database.
    
    Returns:
        Dict with success status, synced count, or error
    """
    from encryption_utils import decrypt_value
    
    # Get decrypted credentials
    client_id = decrypt_value(restaurant.get("toast_client_id", ""))
    client_secret = decrypt_value(restaurant.get("toast_client_secret", ""))
    restaurant_guid = decrypt_value(restaurant.get("toast_restaurant_guid", ""))
    env = restaurant.get("pos_env", "sandbox")
    
    if not all([client_id, client_secret, restaurant_guid]):
        return {"success": False, "error": "Toast credentials not configured"}
    
    # Get access token
    access_token = await get_toast_access_token(
        restaurant_id, client_id, client_secret, restaurant_guid, env
    )
    if not access_token:
        return {"success": False, "error": "Toast authentication failed"}
    
    base_url = _get_toast_base_url(env)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get menu items from Toast
            response = await client.get(
                f"{base_url}/menus/v2/menus",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Toast-Restaurant-External-ID": restaurant_guid,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Toast menu fetch failed: {response.status_code}")
                return {"success": False, "error": f"Toast API error: {response.status_code}"}
            
            menus = response.json()
            
            # Process and upsert items
            import uuid
            synced = 0
            
            for menu in menus:
                menu_groups = menu.get("menuGroups", [])
                for group in menu_groups:
                    category = group.get("name", "Uncategorized")
                    items = group.get("menuItems", [])
                    
                    for item in items:
                        toast_item_id = item.get("guid")
                        name = item.get("name", "Unknown Item")
                        description = item.get("description", "")
                        price = int(float(item.get("price", 0)) * 100)  # Convert to cents
                        
                        mapped_item = {
                            "id": str(uuid.uuid4()),
                            "restaurant_id": restaurant_id,
                            "pos_item_id": toast_item_id,
                            "pos_type": "toast",
                            "name": name,
                            "description": description or None,
                            "category": category,
                            "price": price,
                            "available": True,
                            "allergens": [],
                            "modifiers": [],
                            "modifier_group_assignments": [],
                            "special_instructions_enabled": True,
                            "prep_time_minutes": None,
                            "image_url": item.get("imageUrl"),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                        
                        # Upsert by pos_item_id
                        existing = await db.menu_items.find_one(
                            {"restaurant_id": restaurant_id, "pos_item_id": toast_item_id},
                            {"_id": 0}
                        )
                        
                        if existing:
                            await db.menu_items.update_one(
                                {"restaurant_id": restaurant_id, "pos_item_id": toast_item_id},
                                {"$set": {
                                    "name": name,
                                    "description": description or None,
                                    "category": category,
                                    "price": price,
                                }}
                            )
                        else:
                            await db.menu_items.insert_one(mapped_item)
                        
                        synced += 1
            
            logger.info(f"Toast sync complete: {synced} items for restaurant {restaurant_id}")
            return {"success": True, "synced": synced, "source": "toast"}
            
    except Exception as e:
        logger.error(f"Toast sync error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def send_order_to_toast(
    order,  # LiveOrder object
    restaurant: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Send an order to Toast POS.
    
    Returns:
        Dict with success status, order_id, and method
    """
    from encryption_utils import decrypt_value
    
    restaurant_id = order.restaurant_id
    
    # Get decrypted credentials
    client_id = decrypt_value(restaurant.get("toast_client_id", ""))
    client_secret = decrypt_value(restaurant.get("toast_client_secret", ""))
    restaurant_guid = decrypt_value(restaurant.get("toast_restaurant_guid", ""))
    env = restaurant.get("pos_env", "sandbox")
    
    if not all([client_id, client_secret, restaurant_guid]):
        return {"success": False, "order_id": "", "method": "toast"}
    
    # Get access token
    access_token = await get_toast_access_token(
        restaurant_id, client_id, client_secret, restaurant_guid, env
    )
    if not access_token:
        return {"success": False, "order_id": "", "method": "toast"}
    
    base_url = _get_toast_base_url(env)
    
    try:
        # Build order payload
        order_payload = {
            "entityType": "Order",
            "externalId": order.call_sid,
            "source": "PHONE",
            "diningOption": {
                "guid": "TAKEOUT" if order.order_type == "pickup" else "DELIVERY"
            },
            "customer": {
                "firstName": order.customer_name or "Phone",
                "lastName": "Customer",
                "phone": order.caller_number
            },
            "selections": []
        }
        
        # Add items
        for item in order.items:
            selection = {
                "entityType": "MenuItemSelection",
                "itemGroup": {
                    "guid": item.menu_item_id  # Assuming this is the Toast GUID
                },
                "quantity": item.quantity,
                "specialInstructions": item.special_instructions or None
            }
            order_payload["selections"].append(selection)
        
        # Add delivery address if applicable
        if order.order_type == "delivery" and order.delivery_address:
            order_payload["deliveryInfo"] = {
                "address1": order.delivery_address
            }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/orders/v2/orders",
                json=order_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Toast-Restaurant-External-ID": restaurant_guid,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                toast_order_id = data.get("guid", "")
                logger.info(f"Toast order created: {toast_order_id}")
                return {"success": True, "order_id": toast_order_id, "method": "toast"}
            else:
                logger.error(f"Toast order failed: {response.status_code} {response.text[:200]}")
                return {"success": False, "order_id": "", "method": "toast"}
                
    except Exception as e:
        logger.error(f"Toast order dispatch error: {e}", exc_info=True)
        return {"success": False, "order_id": "", "method": "toast"}


async def get_toast_queue_depth(
    restaurant: Dict[str, Any],
    config: Dict[str, Any]
) -> Optional[int]:
    """
    Get the number of open orders in Toast kitchen.
    Used for dynamic ETA calculation.
    
    Returns:
        Number of open orders, or None if unavailable
    """
    from encryption_utils import decrypt_value
    
    restaurant_id = restaurant.get("id", "")
    client_id = decrypt_value(restaurant.get("toast_client_id", ""))
    client_secret = decrypt_value(restaurant.get("toast_client_secret", ""))
    restaurant_guid = decrypt_value(restaurant.get("toast_restaurant_guid", ""))
    env = restaurant.get("pos_env", "sandbox")
    
    if not all([client_id, client_secret, restaurant_guid]):
        return None
    
    access_token = await get_toast_access_token(
        restaurant_id, client_id, client_secret, restaurant_guid, env
    )
    if not access_token:
        return None
    
    base_url = _get_toast_base_url(env)
    
    try:
        # Get orders from the last 30 minutes that are not completed
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{base_url}/orders/v2/ordersBulk",
                params={
                    "startDate": (datetime.now(timezone.utc).timestamp() - 1800) * 1000,
                    "endDate": datetime.now(timezone.utc).timestamp() * 1000,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Toast-Restaurant-External-ID": restaurant_guid,
                }
            )
            
            if response.status_code == 200:
                orders = response.json()
                # Count orders not yet completed
                open_statuses = {"OPEN", "NEW", "IN_PROGRESS", "PENDING"}
                open_count = sum(
                    1 for o in orders
                    if o.get("displayStatus", "").upper() in open_statuses
                )
                logger.info(f"Toast queue depth: {open_count} open orders")
                return open_count
                
            return None
            
    except Exception as e:
        logger.warning(f"Toast queue depth check failed: {e}")
        return None


async def test_toast_connection(
    client_id: str,
    client_secret: str,
    restaurant_guid: str,
    env: str = "sandbox"
) -> Dict[str, Any]:
    """
    Test Toast API connection with provided credentials.
    
    Returns:
        Dict with success status and restaurant info or error
    """
    access_token = await get_toast_access_token(
        "test", client_id, client_secret, restaurant_guid, env
    )
    
    if not access_token:
        return {"success": False, "error": "Authentication failed"}
    
    base_url = _get_toast_base_url(env)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/restaurants/v1/restaurants/{restaurant_guid}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Toast-Restaurant-External-ID": restaurant_guid,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "restaurant_name": data.get("general", {}).get("name", "Unknown"),
                    "location": data.get("general", {}).get("locationName", ""),
                }
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
    except Exception as e:
        return {"success": False, "error": str(e)}
