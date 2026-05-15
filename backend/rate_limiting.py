"""
Rate Limiting for RingAI - Production-Grade API Protection

Uses slowapi with custom key functions to rate limit by:
- Clerk user ID for authenticated requests
- IP address for unauthenticated requests

Rate limit tiers:
- Bootstrap/auth: 30/minute
- Restaurant reads: 60/minute
- Restaurant writes: 20/minute
- Menu operations: 30/minute reads, 10/minute bulk
- Analytics: 20/minute
- POS credentials: 5/minute

Part of Prompt 5 - Rate Limiting
"""
import os
import logging
from typing import Optional, Callable
from functools import wraps

from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """
    Custom key function for rate limiting.
    Uses Clerk user ID if authenticated, otherwise IP address.
    """
    # Try to get user ID from auth header (Clerk JWT)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import jwt
            token = auth_header.split(" ", 1)[1]
            # Decode without verification just to get the subject
            # (verification happens in the endpoint)
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
    
    # Fallback to IP address
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # Get first IP in chain (client IP)
        return f"ip:{forwarded.split(',')[0].strip()}"
    
    return f"ip:{get_remote_address(request)}"


def get_restaurant_rate_key(request: Request) -> str:
    """
    Rate limit by restaurant ID when available.
    Falls back to user/IP if no restaurant context.
    """
    # Try path parameter first
    restaurant_id = request.path_params.get("restaurant_id")
    if not restaurant_id:
        # Try query parameter
        restaurant_id = request.query_params.get("restaurant_id")
    
    if restaurant_id:
        return f"restaurant:{restaurant_id}"
    
    return get_rate_limit_key(request)


# Initialize limiter with default key function
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["100/minute"],
    storage_uri=os.environ.get("REDIS_URL"),  # Use Redis if available
    strategy="fixed-window",
)


# ============================================================
# RATE LIMIT DECORATORS
# ============================================================

# Auth/Bootstrap endpoints - 30/minute
LIMIT_AUTH = "30/minute"

# Restaurant reads - 60/minute
LIMIT_RESTAURANT_READ = "60/minute"

# Restaurant writes - 20/minute
LIMIT_RESTAURANT_WRITE = "20/minute"

# Menu reads - 30/minute
LIMIT_MENU_READ = "30/minute"

# Menu bulk operations - 10/minute
LIMIT_MENU_BULK = "10/minute"

# Analytics - 20/minute
LIMIT_ANALYTICS = "20/minute"

# POS credentials - 5/minute (sensitive)
LIMIT_POS_CREDENTIALS = "5/minute"

# General API - 100/minute
LIMIT_GENERAL = "100/minute"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors."""
    logger.warning(
        f"Rate limit exceeded: {get_rate_limit_key(request)} "
        f"on {request.url.path} - limit: {exc.detail}"
    )
    raise HTTPException(
        status_code=429,
        detail="Too many requests. Please try again later.",
        headers={"Retry-After": "60"}
    )


# ============================================================
# WEBSOCKET CONNECTION LIMITS
# ============================================================

# Track WebSocket connections per restaurant
_ws_connections: dict = {}  # restaurant_id -> count
MAX_WS_PER_RESTAURANT = 5


def check_ws_connection_limit(restaurant_id: str) -> bool:
    """
    Check if a new WebSocket connection is allowed for this restaurant.
    Returns True if under limit, False if at capacity.
    """
    current = _ws_connections.get(restaurant_id, 0)
    if current >= MAX_WS_PER_RESTAURANT:
        logger.warning(f"WebSocket limit reached for restaurant {restaurant_id}: {current}/{MAX_WS_PER_RESTAURANT}")
        return False
    return True


def register_ws_connection(restaurant_id: str):
    """Register a new WebSocket connection."""
    _ws_connections[restaurant_id] = _ws_connections.get(restaurant_id, 0) + 1
    logger.debug(f"WS connection registered: {restaurant_id} ({_ws_connections[restaurant_id]})")


def unregister_ws_connection(restaurant_id: str):
    """Unregister a WebSocket connection."""
    if restaurant_id in _ws_connections:
        _ws_connections[restaurant_id] = max(0, _ws_connections[restaurant_id] - 1)
        if _ws_connections[restaurant_id] == 0:
            del _ws_connections[restaurant_id]
        logger.debug(f"WS connection unregistered: {restaurant_id}")


def get_ws_connection_count(restaurant_id: Optional[str] = None) -> int:
    """Get current WebSocket connection count."""
    if restaurant_id:
        return _ws_connections.get(restaurant_id, 0)
    return sum(_ws_connections.values())


# ============================================================
# RATE LIMIT HELPER FOR MANUAL CHECKING
# ============================================================

class RateLimitChecker:
    """
    Manual rate limit checking for use outside of decorators.
    Useful for WebSocket connections or custom flows.
    """
    
    def __init__(self):
        self._counters: dict = {}  # key -> (count, window_start)
        self._window_seconds = 60
    
    def check(self, key: str, limit: int) -> bool:
        """
        Check if action is within rate limit.
        Returns True if allowed, False if rate limited.
        """
        import time
        now = time.time()
        
        if key not in self._counters:
            self._counters[key] = (1, now)
            return True
        
        count, window_start = self._counters[key]
        
        # Reset window if expired
        if now - window_start >= self._window_seconds:
            self._counters[key] = (1, now)
            return True
        
        # Check limit
        if count >= limit:
            return False
        
        # Increment counter
        self._counters[key] = (count + 1, window_start)
        return True
    
    def reset(self, key: str):
        """Reset rate limit counter for a key."""
        if key in self._counters:
            del self._counters[key]


# Global rate limit checker instance
rate_checker = RateLimitChecker()
