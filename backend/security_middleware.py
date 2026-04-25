"""
Security Middleware for RingAI - Production-Grade Hardening

Provides:
- Twilio webhook signature validation
- Request size limits
- Security headers
- MongoDB injection prevention
- CORS configuration helper

Part of Prompt 6 - Security Hardening
"""
import os
import re
import logging
import hashlib
import hmac
from typing import Optional, Any, Dict, Callable
from urllib.parse import urlencode
from fastapi import Request, HTTPException
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Maximum request body size (5MB)
MAX_REQUEST_SIZE = 5 * 1024 * 1024

# Allowed CORS origins - tightened from wildcard
ALLOWED_ORIGINS = [
    "https://www.duuutah.com",
    "https://duuutah.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
]


def get_secure_cors_origins() -> list:
    """
    Get CORS origins with environment override support.
    Production should use explicit origins, never wildcards.
    """
    env_origins = os.environ.get("CORS_ORIGINS", "")
    if env_origins and env_origins != "*":
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    
    # Add frontend URL if configured
    frontend_url = os.environ.get("FRONTEND_URL", "")
    if frontend_url:
        origins = list(ALLOWED_ORIGINS)
        if frontend_url not in origins:
            origins.append(frontend_url.rstrip("/"))
        return origins
    
    return ALLOWED_ORIGINS


# ============================================================
# TWILIO WEBHOOK SIGNATURE VALIDATION
# ============================================================

def validate_twilio_signature(
    request_url: str,
    params: Dict[str, str],
    signature: str,
    auth_token: Optional[str] = None
) -> bool:
    """
    Validate Twilio webhook signature using HMAC-SHA1.
    
    Args:
        request_url: Full URL of the webhook endpoint
        params: POST parameters from the request
        signature: X-Twilio-Signature header value
        auth_token: Twilio auth token (from env if not provided)
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        return False
    
    token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not token:
        logger.warning("TWILIO_AUTH_TOKEN not configured - skipping validation in dev")
        # In development without token, allow requests
        return os.environ.get("ENVIRONMENT", "development") == "development"
    
    # Sort params and build string
    sorted_params = sorted(params.items())
    param_string = "".join(f"{k}{v}" for k, v in sorted_params)
    
    # Create signature
    data = request_url + param_string
    computed_sig = hmac.new(
        token.encode(),
        data.encode(),
        hashlib.sha1
    ).digest()
    
    import base64
    computed_b64 = base64.b64encode(computed_sig).decode()
    
    return hmac.compare_digest(computed_b64, signature)


async def verify_twilio_request(request: Request) -> bool:
    """
    Verify incoming Twilio webhook request.
    Call this at the start of Twilio endpoints.
    """
    # Skip validation in test/development mode
    if os.environ.get("SKIP_TWILIO_VALIDATION", "").lower() == "true":
        return True
    
    signature = request.headers.get("X-Twilio-Signature", "")
    
    # Get the full URL
    url = str(request.url)
    # Twilio uses the public URL, not internal
    public_url = os.environ.get("BACKEND_PUBLIC_URL", "")
    if public_url:
        url = public_url.rstrip("/") + request.url.path
    
    # Get form data
    try:
        form_data = await request.form()
        params = {k: v for k, v in form_data.items()}
    except Exception:
        params = {}
    
    return validate_twilio_signature(url, params, signature)


# ============================================================
# MONGODB INJECTION PREVENTION
# ============================================================

def sanitize_mongo_query(data: Any) -> Any:
    """
    Recursively sanitize user input to prevent MongoDB injection.
    Removes/escapes $ operators from keys.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Remove keys starting with $ (MongoDB operators)
            if isinstance(key, str) and key.startswith("$"):
                logger.warning(f"Blocked potential MongoDB injection: key={key}")
                continue
            # Recursively sanitize nested structures
            sanitized[key] = sanitize_mongo_query(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_mongo_query(item) for item in data]
    elif isinstance(data, str):
        # Remove embedded $ operators in string values
        if "$" in data and any(op in data for op in ["$where", "$gt", "$lt", "$ne", "$regex", "$or", "$and"]):
            logger.warning(f"Blocked potential MongoDB injection in string: {data[:50]}...")
            return re.sub(r'\$\w+', '', data)
    return data


def sanitize_string_input(value: str, max_length: int = 1000, allow_html: bool = False) -> str:
    """
    Sanitize user string input.
    - Strips whitespace
    - Removes HTML tags (unless allowed)
    - Truncates to max length
    - Removes null bytes
    """
    if not value:
        return ""
    
    # Remove null bytes
    result = value.replace("\x00", "")
    
    # Strip whitespace
    result = result.strip()
    
    # Remove HTML tags
    if not allow_html:
        result = re.sub(r"<[^>]+>", "", result)
    
    # Truncate
    if len(result) > max_length:
        result = result[:max_length]
    
    return result


# ============================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # HSTS - only in production with HTTPS
        if os.environ.get("ENVIRONMENT") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Remove server header
        if "server" in response.headers:
            del response.headers["server"]
        
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Reject requests with body larger than MAX_REQUEST_SIZE.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_SIZE:
                    logger.warning(f"Request too large: {content_length} bytes from {request.client.host}")
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large. Maximum size is 5MB."}
                    )
            except ValueError:
                pass
        
        return await call_next(request)


# ============================================================
# SECURE LOGGING UTILITIES
# ============================================================

# Fields that should NEVER appear in logs
REDACTED_FIELDS = {
    "password", "token", "api_key", "secret", "auth_token",
    "access_token", "refresh_token", "credit_card", "ssn",
    "clover_api_token", "square_access_token", "toast_client_secret",
    "customer_phone", "caller_number", "phone_number",
    "customer_email", "email", "billing_email",
    "delivery_address", "address",
}


def redact_for_logging(data: Any, depth: int = 0) -> Any:
    """
    Recursively redact sensitive fields from data before logging.
    Prevents PII and credentials from appearing in logs.
    """
    if depth > 10:  # Prevent infinite recursion
        return "[MAX_DEPTH]"
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(rf in key_lower for rf in REDACTED_FIELDS):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_for_logging(value, depth + 1)
        return result
    elif isinstance(data, list):
        return [redact_for_logging(item, depth + 1) for item in data[:10]]  # Limit list size
    elif isinstance(data, str):
        if len(data) > 200:
            return data[:200] + "...[TRUNCATED]"
        return data
    return data


def safe_log_request(request_data: dict, message: str = "Request"):
    """Log request data with sensitive fields redacted."""
    redacted = redact_for_logging(request_data)
    logger.info(f"{message}: {redacted}")


def safe_log_error(error: Exception, context: dict = None):
    """Log error with context, redacting sensitive data."""
    error_msg = str(error)
    # Redact any values that look like tokens/secrets
    error_msg = re.sub(r'(token|key|secret|password)[\s=:]+[^\s,}\]]+', r'\1=[REDACTED]', error_msg, flags=re.I)
    
    redacted_context = redact_for_logging(context) if context else {}
    logger.error(f"Error: {error_msg} | Context: {redacted_context}")
