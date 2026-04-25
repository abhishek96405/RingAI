"""
Dynamic ETA Service for RingAI

Provides:
- Item-level prep time weighting
- Kitchen queue depth integration
- Dynamic ETA calculation

Part of Prompt 4 - Dynamic ETA with Item-Level Weights
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Default prep times by category (minutes)
DEFAULT_PREP_TIMES = {
    "beverages": 3,
    "drinks": 3,
    "appetizers": 8,
    "starters": 8,
    "salads": 5,
    "soups": 5,
    "sides": 5,
    "pizza": 18,
    "pasta": 12,
    "entrees": 15,
    "main course": 15,
    "mains": 15,
    "seafood": 18,
    "grill": 20,
    "bbq": 25,
    "desserts": 8,
    "specials": 20,
}

# Time adjustments based on queue depth
QUEUE_MULTIPLIERS = {
    0: 1.0,      # Empty kitchen
    1: 1.0,      # Normal
    2: 1.0,      # Still normal
    3: 1.1,      # Slightly busy
    5: 1.2,      # Busy
    8: 1.3,      # Very busy
    12: 1.5,     # Extremely busy
    20: 1.8,     # Peak hours
}


def get_queue_multiplier(queue_depth: int) -> float:
    """Get the time multiplier based on kitchen queue depth."""
    multiplier = 1.0
    for threshold, mult in sorted(QUEUE_MULTIPLIERS.items()):
        if queue_depth >= threshold:
            multiplier = mult
    return multiplier


def get_item_prep_time(
    item: Dict[str, Any],
    default_prep_time: int = 15
) -> int:
    """
    Get prep time for a menu item.
    Uses item-specific prep_time_minutes if set, otherwise category default.
    """
    # Check for item-specific prep time
    if item.get("prep_time_minutes"):
        return item["prep_time_minutes"]
    
    # Fall back to category default
    category = (item.get("category") or "").lower()
    
    for cat_name, prep_time in DEFAULT_PREP_TIMES.items():
        if cat_name in category:
            return prep_time
    
    # Use restaurant default
    return default_prep_time


async def calculate_dynamic_eta(
    order_items: List[Dict[str, Any]],
    restaurant: Dict[str, Any],
    config: Dict[str, Any],
    menu_items: List[Dict[str, Any]],
    queue_depth: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calculate dynamic ETA for an order based on:
    - Individual item prep times
    - Kitchen queue depth from POS
    - Time of day adjustments
    
    Returns:
        Dict with eta_minutes, breakdown, and factors
    """
    # Build menu lookup
    menu_lookup = {item["id"]: item for item in menu_items}
    menu_lookup.update({item["name"].lower(): item for item in menu_items})
    
    # Get restaurant default prep time
    default_prep = restaurant.get("avg_prep_time_minutes", 20)
    
    # Calculate weighted prep time based on order
    item_times = []
    max_prep_time = 0
    
    for order_item in order_items:
        # Find menu item
        item_id = order_item.get("menu_item_id", "")
        item_name = order_item.get("name", "").lower()
        
        menu_item = menu_lookup.get(item_id) or menu_lookup.get(item_name) or {}
        
        prep_time = get_item_prep_time(menu_item, default_prep)
        quantity = order_item.get("quantity", 1)
        
        # Items can be prepared in parallel, so we use max not sum
        # But multiples of same item add some time
        item_total = prep_time + (quantity - 1) * 2  # +2 min per additional item
        item_times.append({
            "item": order_item.get("name", "Unknown"),
            "base_prep_time": prep_time,
            "quantity": quantity,
            "total_time": item_total,
        })
        
        max_prep_time = max(max_prep_time, item_total)
    
    # Apply queue depth multiplier
    queue_multiplier = 1.0
    if queue_depth is not None:
        queue_multiplier = get_queue_multiplier(queue_depth)
    else:
        # Try to get queue depth from POS
        try:
            from gemini_service import get_kitchen_queue_depth
            queue_depth = await get_kitchen_queue_depth(restaurant, config)
            if queue_depth is not None:
                queue_multiplier = get_queue_multiplier(queue_depth)
        except Exception:
            pass
    
    # Apply time of day adjustment
    import pytz
    tz_str = restaurant.get("timezone", "America/Chicago")
    try:
        tz = pytz.timezone(tz_str)
        local_now = datetime.now(tz)
        hour = local_now.hour
        
        # Peak hours: 12-2 PM lunch, 6-8 PM dinner
        time_multiplier = 1.0
        if 12 <= hour <= 14 or 18 <= hour <= 20:
            time_multiplier = 1.15  # 15% longer during peaks
            
    except Exception:
        time_multiplier = 1.0
    
    # Calculate final ETA
    base_eta = max_prep_time
    adjusted_eta = base_eta * queue_multiplier * time_multiplier
    
    # Round up to nearest 5 minutes
    final_eta = int((adjusted_eta + 4) // 5 * 5)
    
    # Minimum 10 minutes
    final_eta = max(10, final_eta)
    
    return {
        "eta_minutes": final_eta,
        "base_eta": base_eta,
        "queue_depth": queue_depth,
        "queue_multiplier": round(queue_multiplier, 2),
        "time_multiplier": round(time_multiplier, 2),
        "item_breakdown": item_times,
        "factors": {
            "items": len(order_items),
            "max_item_time": max_prep_time,
            "peak_hours": time_multiplier > 1.0,
            "busy_kitchen": queue_multiplier > 1.0,
        }
    }


def format_eta_for_speech(eta_minutes: int) -> str:
    """Format ETA for AI to speak naturally."""
    if eta_minutes <= 10:
        return "about 10 minutes"
    elif eta_minutes <= 15:
        return "about 15 minutes"
    elif eta_minutes <= 20:
        return "about 20 minutes"
    elif eta_minutes <= 25:
        return "about 20 to 25 minutes"
    elif eta_minutes <= 30:
        return "about half an hour"
    elif eta_minutes <= 40:
        return "about 35 to 40 minutes"
    elif eta_minutes <= 50:
        return "about 45 minutes"
    elif eta_minutes <= 60:
        return "about an hour"
    else:
        hours = eta_minutes // 60
        remaining = eta_minutes % 60
        if remaining < 15:
            return f"about {hours} hour{'s' if hours > 1 else ''}"
        else:
            return f"about {hours} hour{'s' if hours > 1 else ''} and {remaining} minutes"
