"""
POS Integration Layer for RingAI

Provides adapters for various POS systems (Square, Toast, Clover, etc.)
Each adapter implements IPosAdapter interface for standardized order submission
and menu synchronization.
"""
import os
import json
import base64
import logging
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


# =============================================================================
# Encryption Utils (AES-256 via Fernet)
# =============================================================================

def _get_encryption_key() -> bytes:
    """Derive AES-256 key from secret."""
    secret = os.environ.get("POS_ENCRYPTION_SECRET", "ringai-default-secret-key-change-me")
    salt = os.environ.get("POS_ENCRYPTION_SALT", "ringai-salt").encode()
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key


def encrypt_token(token: str) -> str:
    """Encrypt access token with AES-256."""
    f = Fernet(_get_encryption_key())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt access token."""
    f = Fernet(_get_encryption_key())
    return f.decrypt(encrypted.encode()).decode()


# =============================================================================
# POS Adapter Interface
# =============================================================================

class IPosAdapter(ABC):
    """Interface for POS system adapters."""
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the POS provider (e.g., 'square', 'toast')."""
        pass
    
    @abstractmethod
    async def submit_order(self, order: Dict[str, Any], location_id: str) -> Dict[str, Any]:
        """
        Submit an order to the POS system.
        
        Args:
            order: Order JSON from Gemini conversation
            location_id: POS location identifier
            
        Returns:
            Dict with order_id, status, and any POS-specific data
        """
        pass
    
    @abstractmethod
    async def sync_menu(self, location_id: str) -> List[Dict[str, Any]]:
        """
        Pull menu items from POS catalog.
        
        Args:
            location_id: POS location identifier
            
        Returns:
            List of menu items in RingAI format
        """
        pass
    
    @abstractmethod
    async def get_locations(self) -> List[Dict[str, Any]]:
        """Get available locations/stores from POS."""
        pass
    
    @abstractmethod
    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Get OAuth authorization URL."""
        pass
    
    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange OAuth code for access token."""
        pass


# =============================================================================
# Square Adapter
# =============================================================================

class SquareAdapter(IPosAdapter):
    """Square POS adapter implementation."""
    
    SANDBOX_BASE_URL = "https://connect.squareupsandbox.com"
    PRODUCTION_BASE_URL = "https://connect.squareup.com"
    
    def __init__(self, access_token: str, sandbox: bool = True):
        self.access_token = access_token
        self.sandbox = sandbox
        self.base_url = self.SANDBOX_BASE_URL if sandbox else self.PRODUCTION_BASE_URL
        self.api_url = f"{self.base_url}/v2"
    
    @property
    def provider_name(self) -> str:
        return "square"
    
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Square-Version": "2025-01-23",
        }
    
    async def get_locations(self) -> List[Dict[str, Any]]:
        """Get Square locations."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/locations",
                headers=self._headers(),
            )
            if response.status_code != 200:
                logger.error(f"Square get_locations error: {response.text}")
                return []
            
            data = response.json()
            locations = data.get("locations", [])
            return [
                {
                    "id": loc.get("id"),
                    "name": loc.get("name"),
                    "address": loc.get("address", {}).get("address_line_1", ""),
                    "timezone": loc.get("timezone"),
                    "status": loc.get("status"),
                }
                for loc in locations
            ]
    
    async def sync_menu(self, location_id: str) -> List[Dict[str, Any]]:
        """
        Pull menu from Square Catalog API.
        Converts Square catalog items to RingAI menu format.
        """
        items = []
        cursor = None
        
        async with httpx.AsyncClient() as client:
            while True:
                params = {"types": "ITEM", "location_ids": location_id}
                if cursor:
                    params["cursor"] = cursor
                
                response = await client.get(
                    f"{self.api_url}/catalog/list",
                    headers=self._headers(),
                    params=params,
                )
                
                if response.status_code != 200:
                    logger.error(f"Square sync_menu error: {response.text}")
                    break
                
                data = response.json()
                catalog_objects = data.get("objects", [])
                
                for obj in catalog_objects:
                    if obj.get("type") != "ITEM":
                        continue
                    
                    item_data = obj.get("item_data", {})
                    variations = item_data.get("variations", [])
                    
                    # Get price from first variation
                    price_cents = 0
                    if variations:
                        var_data = variations[0].get("item_variation_data", {})
                        price_money = var_data.get("price_money", {})
                        price_cents = price_money.get("amount", 0)
                    
                    menu_item = {
                        "pos_item_id": obj.get("id"),
                        "name": item_data.get("name", "Unknown Item"),
                        "description": item_data.get("description", ""),
                        "price": price_cents,  # In cents
                        "category": item_data.get("category_id", "Uncategorized"),
                        "available": not item_data.get("is_deleted", False),
                        "allergens": [],
                        "variations": [
                            {
                                "id": v.get("id"),
                                "name": v.get("item_variation_data", {}).get("name", ""),
                                "price": v.get("item_variation_data", {}).get("price_money", {}).get("amount", 0),
                            }
                            for v in variations
                        ],
                    }
                    items.append(menu_item)
                
                cursor = data.get("cursor")
                if not cursor:
                    break
        
        logger.info(f"Synced {len(items)} menu items from Square")
        return items
    
    async def submit_order(self, order: Dict[str, Any], location_id: str) -> Dict[str, Any]:
        """
        Submit order to Square Orders API.
        
        Args:
            order: Order from Gemini with items, customer info
            location_id: Square location ID
        """
        import uuid
        
        # Build line items
        line_items = []
        for item in order.get("items", []):
            line_item = {
                "name": item.get("name"),
                "quantity": str(item.get("quantity", 1)),
                "base_price_money": {
                    "amount": item.get("price", 0),
                    "currency": "USD",
                },
            }
            
            # If we have a POS item ID, use it
            if item.get("pos_item_id"):
                line_item["catalog_object_id"] = item.get("pos_item_id")
                del line_item["name"]
                del line_item["base_price_money"]
            
            line_items.append(line_item)
        
        # Build order payload
        order_payload = {
            "idempotency_key": str(uuid.uuid4()),
            "order": {
                "location_id": location_id,
                "line_items": line_items,
                "fulfillments": [
                    {
                        "type": order.get("type", "PICKUP").upper(),
                        "state": "PROPOSED",
                        "pickup_details": {
                            "recipient": {
                                "display_name": order.get("customer_name", "Guest"),
                            },
                            "schedule_type": "ASAP",
                        } if order.get("type", "pickup").lower() == "pickup" else None,
                    }
                ],
            },
        }
        
        # Remove None fulfillment details
        if not order_payload["order"]["fulfillments"][0].get("pickup_details"):
            del order_payload["order"]["fulfillments"][0]["pickup_details"]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/orders",
                headers=self._headers(),
                json=order_payload,
            )
            
            if response.status_code not in [200, 201]:
                logger.error(f"Square submit_order error: {response.text}")
                return {
                    "success": False,
                    "error": response.json().get("errors", [{"detail": "Unknown error"}])[0].get("detail"),
                }
            
            data = response.json()
            square_order = data.get("order", {})
            
            return {
                "success": True,
                "order_id": square_order.get("id"),
                "pos_provider": "square",
                "status": square_order.get("state"),
                "total": square_order.get("total_money", {}).get("amount", 0),
                "created_at": square_order.get("created_at"),
            }
    
    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Get Square OAuth authorization URL."""
        client_id = os.environ.get("SQUARE_APPLICATION_ID", "")
        scopes = "MERCHANT_PROFILE_READ+ITEMS_READ+ITEMS_WRITE+ORDERS_READ+ORDERS_WRITE+INVENTORY_READ"
        
        return (
            f"{self.base_url}/oauth2/authorize"
            f"?client_id={client_id}"
            f"&scope={scopes}"
            f"&session=false"
            f"&state={state}"
            f"&redirect_uri={redirect_uri}"
        )
    
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange OAuth code for access token."""
        client_id = os.environ.get("SQUARE_APPLICATION_ID", "")
        client_secret = os.environ.get("SQUARE_APPLICATION_SECRET", "")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            
            if response.status_code != 200:
                logger.error(f"Square token exchange error: {response.text}")
                return {"success": False, "error": response.text}
            
            data = response.json()
            return {
                "success": True,
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_at": data.get("expires_at"),
                "merchant_id": data.get("merchant_id"),
            }


# =============================================================================
# POS Factory
# =============================================================================

class PosFactory:
    """Factory for creating POS adapters."""
    
    @staticmethod
    def create_adapter(provider: str, access_token: str, sandbox: bool = True) -> IPosAdapter:
        """
        Create a POS adapter for the given provider.
        
        Args:
            provider: POS provider name ('square', 'toast', 'clover')
            access_token: Decrypted access token
            sandbox: Whether to use sandbox/test mode
            
        Returns:
            IPosAdapter implementation
        """
        adapters = {
            "square": SquareAdapter,
            # Future: "toast": ToastAdapter,
            # Future: "clover": CloverAdapter,
        }
        
        adapter_class = adapters.get(provider.lower())
        if not adapter_class:
            raise ValueError(f"Unsupported POS provider: {provider}")
        
        return adapter_class(access_token, sandbox)
    
    @staticmethod
    def get_supported_providers() -> List[str]:
        """Get list of supported POS providers."""
        return ["square"]  # Add more as implemented


# =============================================================================
# Order Processor
# =============================================================================

class OrderProcessor:
    """Processes orders from Gemini and submits to POS."""
    
    def __init__(self, db):
        self.db = db
    
    async def process_order(
        self, 
        restaurant_id: str, 
        order_json: Dict[str, Any],
        customer_name: str = "Guest",
    ) -> Dict[str, Any]:
        """
        Process an order and submit to the restaurant's POS.
        
        Args:
            restaurant_id: RingAI restaurant ID
            order_json: Order JSON from Gemini conversation
            customer_name: Customer name from call
            
        Returns:
            Dict with order status and POS details
        """
        # Get POS connection for restaurant
        connection = await self.db.pos_connections.find_one(
            {"restaurant_id": restaurant_id, "is_active": True},
            {"_id": 0}
        )
        
        if not connection:
            logger.info(f"No POS connection for restaurant {restaurant_id}")
            return {
                "submitted_to_pos": False,
                "reason": "No POS connection configured",
            }
        
        try:
            # Decrypt access token
            access_token = decrypt_token(connection["encrypted_access_token"])
            
            # Create adapter
            adapter = PosFactory.create_adapter(
                provider=connection["provider"],
                access_token=access_token,
                sandbox=connection.get("sandbox", True),
            )
            
            # Enrich order with customer name
            order_json["customer_name"] = customer_name
            
            # Submit order
            result = await adapter.submit_order(
                order=order_json,
                location_id=connection["location_id"],
            )
            
            # Log submission
            if result.get("success"):
                logger.info(f"Order submitted to {connection['provider']}: {result.get('order_id')}")
            else:
                logger.error(f"Order submission failed: {result.get('error')}")
            
            return {
                "submitted_to_pos": result.get("success", False),
                "pos_provider": connection["provider"],
                "pos_order_id": result.get("order_id"),
                "pos_status": result.get("status"),
                "error": result.get("error"),
            }
            
        except Exception as e:
            logger.error(f"Order processing error: {e}")
            return {
                "submitted_to_pos": False,
                "error": str(e),
            }
    
    async def sync_menu_from_pos(self, restaurant_id: str) -> Dict[str, Any]:
        """
        Sync menu items from POS to RingAI.
        
        Args:
            restaurant_id: RingAI restaurant ID
            
        Returns:
            Dict with sync status and item count
        """
        connection = await self.db.pos_connections.find_one(
            {"restaurant_id": restaurant_id, "is_active": True},
            {"_id": 0}
        )
        
        if not connection:
            return {"success": False, "error": "No POS connection"}
        
        try:
            access_token = decrypt_token(connection["encrypted_access_token"])
            adapter = PosFactory.create_adapter(
                provider=connection["provider"],
                access_token=access_token,
                sandbox=connection.get("sandbox", True),
            )
            
            # Get menu from POS
            pos_items = await adapter.sync_menu(connection["location_id"])
            
            # Clear existing menu items (optional - could merge instead)
            await self.db.menu_items.delete_many({"restaurant_id": restaurant_id})
            
            # Insert new items
            import uuid
            for item in pos_items:
                item["id"] = str(uuid.uuid4())
                item["restaurant_id"] = restaurant_id
                item["synced_from_pos"] = True
                item["pos_provider"] = connection["provider"]
                item["synced_at"] = datetime.now(timezone.utc).isoformat()
                await self.db.menu_items.insert_one(item)
            
            # Update sync timestamp
            await self.db.pos_connections.update_one(
                {"restaurant_id": restaurant_id, "provider": connection["provider"]},
                {"$set": {"last_menu_sync": datetime.now(timezone.utc).isoformat()}}
            )
            
            return {
                "success": True,
                "items_synced": len(pos_items),
                "provider": connection["provider"],
            }
            
        except Exception as e:
            logger.error(f"Menu sync error: {e}")
            return {"success": False, "error": str(e)}
