"""
Encryption Utilities for RingAI - Production-Grade Security

Provides:
- Fernet symmetric encryption for sensitive credentials at rest
- Secure key derivation from environment
- Field-level encryption/decryption helpers

All sensitive data (POS credentials, API tokens) should be encrypted
before storage and decrypted only when needed.
"""
import os
import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Derive encryption key from environment secret
# In production, use a proper key management service (AWS KMS, HashiCorp Vault)
_ENCRYPTION_KEY: Optional[bytes] = None


def _get_encryption_key() -> bytes:
    """
    Derive a Fernet-compatible key from environment secret.
    Uses SHA-256 to ensure consistent 32-byte key from any secret length.
    """
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY
    
    # Use dedicated encryption key or fall back to other secrets
    secret = (
        os.environ.get("ENCRYPTION_SECRET_KEY") or
        os.environ.get("CLERK_SECRET_KEY") or
        "duuutah-ai-default-encryption-key-change-in-production"
    )
    
    # SHA-256 produces 32 bytes, which we base64 encode to get Fernet key
    key_bytes = hashlib.sha256(secret.encode()).digest()
    _ENCRYPTION_KEY = base64.urlsafe_b64encode(key_bytes)
    return _ENCRYPTION_KEY


def get_fernet() -> Fernet:
    """Get Fernet instance for encryption/decryption."""
    return Fernet(_get_encryption_key())


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value for storage.
    Returns base64-encoded ciphertext prefixed with 'enc:' marker.
    """
    if not plaintext:
        return plaintext
    
    # Don't double-encrypt
    if plaintext.startswith("enc:"):
        return plaintext
    
    try:
        fernet = get_fernet()
        encrypted = fernet.encrypt(plaintext.encode())
        return f"enc:{encrypted.decode()}"
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        # Return original if encryption fails - log for investigation
        return plaintext


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt an encrypted string value.
    Returns original plaintext. If value is not encrypted, returns as-is.
    """
    if not ciphertext:
        return ciphertext
    
    # Check for encryption marker
    if not ciphertext.startswith("enc:"):
        return ciphertext
    
    try:
        fernet = get_fernet()
        encrypted_bytes = ciphertext[4:].encode()  # Remove 'enc:' prefix
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except InvalidToken:
        logger.error("Decryption failed - invalid token or wrong key")
        return ""
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return ""


def encrypt_sensitive_fields(doc: dict, fields: set) -> dict:
    """
    Encrypt specified fields in a document before storage.
    """
    if not doc:
        return doc
    
    result = dict(doc)
    for field in fields:
        if field in result and result[field]:
            result[field] = encrypt_value(str(result[field]))
    return result


def decrypt_sensitive_fields(doc: dict, fields: set) -> dict:
    """
    Decrypt specified fields in a document after retrieval.
    """
    if not doc:
        return doc
    
    result = dict(doc)
    for field in fields:
        if field in result and result[field]:
            result[field] = decrypt_value(str(result[field]))
    return result


# Google Calendar tokens are stored as a dict (access_token, refresh_token, expires_at,
# ...), so they can't go through the flat-string field helpers above. Encrypt only the two
# secret string values in place; the 'enc:' prefix makes both functions idempotent and lets
# legacy plaintext values pass through unchanged.
CALENDAR_TOKEN_SECRET_KEYS = ("access_token", "refresh_token")


def encrypt_calendar_tokens(tokens):
    """Encrypt the secret values inside a Google Calendar tokens dict."""
    if not tokens:
        return tokens
    result = dict(tokens)
    for key in CALENDAR_TOKEN_SECRET_KEYS:
        if result.get(key):
            result[key] = encrypt_value(str(result[key]))
    return result


def decrypt_calendar_tokens(tokens):
    """Inverse of encrypt_calendar_tokens. Prefix-aware: plaintext (legacy) values pass
    through unchanged, so this is safe on un-migrated data."""
    if not tokens:
        return tokens
    result = dict(tokens)
    for key in CALENDAR_TOKEN_SECRET_KEYS:
        if result.get(key):
            result[key] = decrypt_value(str(result[key]))
    return result


# Fields that should be encrypted at rest
ENCRYPTED_CREDENTIAL_FIELDS = {
    "clover_api_token",
    "clover_merchant_id",
    "clover_refresh_token",
    "square_access_token",
    "square_location_id",
    "toast_client_id",
    "toast_client_secret",
    "toast_restaurant_guid",
    "google_calendar_tokens",
    "stripe_customer_id",
    "stripe_subscription_id",
}


def mask_for_display(value: str, show_chars: int = 4) -> str:
    """
    Mask a sensitive value for display, showing only last N characters.
    """
    if not value or len(value) <= show_chars:
        return "****"
    return "*" * (len(value) - show_chars) + value[-show_chars:]
