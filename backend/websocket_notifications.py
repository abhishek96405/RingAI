"""
WebSocket Notification Service for RingAI

Provides real-time push notifications to connected dashboard clients.
Uses a pub/sub pattern for broadcasting events.

Events:
- new_call: New call started/completed
- new_order: New order received
- new_appointment: New appointment booked
- appointment_reminder: Reminder sent
- call_escalated: Call escalated to human
- system: System notifications
"""
import asyncio
import logging
import json
from typing import Dict, Set, Any, Optional
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.
    Connections are grouped by restaurant_id for targeted notifications.
    """
    
    def __init__(self):
        # restaurant_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> restaurant_id (reverse lookup)
        self.connection_restaurants: Dict[WebSocket, str] = {}
        # Global connections (admin/system)
        self.global_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, restaurant_id: Optional[str] = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        
        async with self._lock:
            if restaurant_id:
                if restaurant_id not in self.active_connections:
                    self.active_connections[restaurant_id] = set()
                self.active_connections[restaurant_id].add(websocket)
                self.connection_restaurants[websocket] = restaurant_id
                logger.info(f"WebSocket connected for restaurant {restaurant_id}")
            else:
                self.global_connections.add(websocket)
                logger.info("Global WebSocket connected")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.connection_restaurants:
                restaurant_id = self.connection_restaurants[websocket]
                if restaurant_id in self.active_connections:
                    self.active_connections[restaurant_id].discard(websocket)
                    if not self.active_connections[restaurant_id]:
                        del self.active_connections[restaurant_id]
                del self.connection_restaurants[websocket]
                logger.info(f"WebSocket disconnected from restaurant {restaurant_id}")
            elif websocket in self.global_connections:
                self.global_connections.discard(websocket)
                logger.info("Global WebSocket disconnected")
    
    async def send_to_restaurant(self, restaurant_id: str, message: Dict[str, Any]):
        """Send a message to all connections for a specific restaurant."""
        if restaurant_id not in self.active_connections:
            return
        
        dead_connections = set()
        message_json = json.dumps(message)
        
        for connection in self.active_connections[restaurant_id].copy():
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for dead in dead_connections:
            await self.disconnect(dead)
    
    async def send_global(self, message: Dict[str, Any]):
        """Send a message to all global connections."""
        dead_connections = set()
        message_json = json.dumps(message)
        
        for connection in self.global_connections.copy():
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to global WebSocket: {e}")
                dead_connections.add(connection)
        
        for dead in dead_connections:
            await self.disconnect(dead)
    
    async def broadcast(self, message: Dict[str, Any]):
        """Send a message to ALL connections."""
        await self.send_global(message)
        for restaurant_id in list(self.active_connections.keys()):
            await self.send_to_restaurant(restaurant_id, message)
    
    def get_connection_count(self, restaurant_id: Optional[str] = None) -> int:
        """Get the number of active connections."""
        if restaurant_id:
            return len(self.active_connections.get(restaurant_id, set()))
        return sum(len(conns) for conns in self.active_connections.values()) + len(self.global_connections)


# Global connection manager instance
manager = ConnectionManager()


# ============================================================
# Notification Event Builders
# ============================================================

def build_notification(
    event_type: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    priority: str = "normal",
) -> Dict[str, Any]:
    """Build a standardized notification object."""
    return {
        "type": "notification",
        "event": event_type,
        "title": title,
        "message": message,
        "data": data or {},
        "priority": priority,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def notify_new_call(
    restaurant_id: str,
    call_sid: str,
    caller_number: str,
    status: str = "started",
    order_total: int = 0,
    caller_name: str = None,
):
    """Notify about a new or completed call."""
    if status == "started":
        title = "New Call"
        message = f"Incoming call from {caller_number[-4:] if len(caller_number) > 4 else caller_number}"
    elif status == "COMPLETED":
        title = "Call Completed"
        order_str = f" - ${order_total/100:.2f}" if order_total else ""
        message = f"AI handled call from ****{caller_number[-4:]}{order_str}"
    elif status == "ESCALATED":
        title = "Call Escalated"
        message = f"Call from ****{caller_number[-4:]} transferred to human"
    else:
        title = "Call Update"
        message = f"Call status: {status}"
    
    notification = build_notification(
        event_type="call",
        title=title,
        message=message,
        data={
            "call_sid": call_sid,
            "caller_number": caller_number[-4:] if len(caller_number) > 4 else "****",
            "status": status,
            "order_total": order_total,
        },
        priority="high" if status == "ESCALATED" else "normal",
    )
    
    await manager.send_to_restaurant(restaurant_id, notification)


async def notify_new_order(
    restaurant_id: str,
    order_id: str,
    total: int,
    order_type: str = "pickup",
    items_count: int = 0,
):
    """Notify about a new order."""
    notification = build_notification(
        event_type="order",
        title="New Order",
        message=f"Order #{order_id[-6:]} - ${total/100:.2f} ({order_type})",
        data={
            "order_id": order_id,
            "total": total,
            "type": order_type,
            "items_count": items_count,
        },
    )
    
    await manager.send_to_restaurant(restaurant_id, notification)


async def notify_new_appointment(
    restaurant_id: str,
    appointment_id: str,
    customer_name: str,
    service_name: str,
    scheduled_date: str,
    scheduled_time: str,
):
    """Notify about a new appointment booking."""
    notification = build_notification(
        event_type="appointment",
        title="New Appointment",
        message=f"{service_name} booked for {customer_name} on {scheduled_date}",
        data={
            "appointment_id": appointment_id,
            "customer_name": customer_name,
            "service_name": service_name,
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
        },
    )
    
    await manager.send_to_restaurant(restaurant_id, notification)


async def notify_appointment_reminder(
    restaurant_id: str,
    appointment_id: str,
    customer_name: str,
    service_name: str,
):
    """Notify that an appointment reminder was sent."""
    notification = build_notification(
        event_type="reminder",
        title="Reminder Sent",
        message=f"24h reminder sent to {customer_name} for {service_name}",
        data={
            "appointment_id": appointment_id,
            "customer_name": customer_name,
        },
        priority="low",
    )
    
    await manager.send_to_restaurant(restaurant_id, notification)


async def notify_system(
    restaurant_id: Optional[str],
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
):
    """Send a system notification."""
    notification = build_notification(
        event_type="system",
        title=title,
        message=message,
        data=data,
        priority="normal",
    )
    
    if restaurant_id:
        await manager.send_to_restaurant(restaurant_id, notification)
    else:
        await manager.broadcast(notification)
