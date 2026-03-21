"""
Security Utilities for RingAI

Provides:
- Input validation and sanitization
- Sanitized error responses
- Rate limiting helpers
- Data protection utilities

Part 3 - Security Hardening
"""
import re
import logging
from typing import Optional, Any, Dict
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Regex patterns for validation
PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{1,14}$")  # E.164 format
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
UUID_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.I)


def validate_phone(phone: str) -> bool:
    """Validate phone number format."""
    if not phone:
        return False
    # Remove common formatting
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", phone)
    return bool(PHONE_PATTERN.match(cleaned))


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False
    return bool(EMAIL_PATTERN.match(email.strip()))


def validate_uuid(uuid_str: str) -> bool:
    """Validate UUID format."""
    if not uuid_str:
        return False
    return bool(UUID_PATTERN.match(uuid_str))


def sanitize_string(value: str, max_length: int = 1000, allow_html: bool = False) -> str:
    """
    Sanitize user input string.
    
    - Strips leading/trailing whitespace
    - Truncates to max_length
    - Optionally removes HTML tags
    """
    if not value:
        return ""
    
    result = value.strip()
    
    if not allow_html:
        # Remove HTML tags
        result = re.sub(r"<[^>]+>", "", result)
    
    # Truncate
    if len(result) > max_length:
        result = result[:max_length]
    
    return result


def sanitize_for_log(data: Any, sensitive_fields: set = None) -> Any:
    """
    Sanitize data for logging by masking sensitive fields.
    """
    if sensitive_fields is None:
        sensitive_fields = {
            "password", "token", "api_key", "secret", "auth",
            "credit_card", "ssn", "access_token", "refresh_token",
            "customer_phone", "customer_email", "caller_number"
        }
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if any(sf in key.lower() for sf in sensitive_fields):
                result[key] = "***REDACTED***"
            else:
                result[key] = sanitize_for_log(value, sensitive_fields)
        return result
    elif isinstance(data, list):
        return [sanitize_for_log(item, sensitive_fields) for item in data]
    elif isinstance(data, str) and len(data) > 100:
        return data[:100] + "..."
    
    return data


def create_safe_error(
    status_code: int,
    message: str,
    internal_error: Optional[Exception] = None,
    log_details: bool = True
) -> HTTPException:
    """
    Create a safe HTTP exception that doesn't leak internal details.
    
    Args:
        status_code: HTTP status code
        message: User-friendly error message
        internal_error: Original exception (for logging only)
        log_details: Whether to log the internal error
    """
    if internal_error and log_details:
        logger.error(f"Internal error (status={status_code}): {internal_error}")
    
    return HTTPException(status_code=status_code, detail=message)


# Common safe error messages (no internal details)
SAFE_ERRORS = {
    "auth_failed": "Authentication failed",
    "access_denied": "You do not have access to this resource",
    "not_found": "Resource not found",
    "invalid_input": "Invalid input data",
    "server_error": "An unexpected error occurred",
    "rate_limited": "Too many requests, please try again later",
    "config_missing": "Service configuration incomplete",
}


def safe_error(error_key: str, status_code: int = 400) -> HTTPException:
    """Get a pre-defined safe error by key."""
    message = SAFE_ERRORS.get(error_key, SAFE_ERRORS["server_error"])
    return HTTPException(status_code=status_code, detail=message)


def mask_phone(phone: str) -> str:
    """Mask phone number for display (show last 4 digits)."""
    if not phone or len(phone) < 4:
        return "****"
    return "****" + phone[-4:]


def mask_email(email: str) -> str:
    """Mask email for display."""
    if not email or "@" not in email:
        return "****@****"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def validate_business_type(business_type: str) -> bool:
    """Validate business type is in allowed list."""
    allowed = {"restaurant", "clinic", "salon", "home_services", "legal"}
    return business_type in allowed


def validate_appointment_status(status: str) -> bool:
    """Validate appointment status is in allowed list."""
    allowed = {"confirmed", "cancelled", "completed", "no_show"}
    return status in allowed


def validate_date_format(date_str: str) -> bool:
    """Validate date string is in YYYY-MM-DD format."""
    if not date_str:
        return False
    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_time_format(time_str: str) -> bool:
    """Validate time string (accepts multiple formats)."""
    if not time_str:
        return False
    
    # Try various formats
    formats = [
        "%I:%M %p",  # 2:00 PM
        "%I:%M%p",   # 2:00PM
        "%H:%M",     # 14:00
    ]
    
    for fmt in formats:
        try:
            from datetime import datetime
            datetime.strptime(time_str.upper().strip(), fmt)
            return True
        except ValueError:
            continue
    
    return False
