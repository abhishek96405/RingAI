"""Google Calendar token encryption at rest (B3-7 / A3-1 token half).

google_calendar_tokens is a dict; encrypt_calendar_tokens / decrypt_calendar_tokens
encrypt only the access_token + refresh_token values in place, leaving non-secret keys
(expires_at, ...) untouched. The 'enc:' prefix makes them idempotent and lets legacy
plaintext tokens pass through decrypt unchanged.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from encryption_utils import (
    encrypt_calendar_tokens,
    decrypt_calendar_tokens,
    encrypt_value,
)

pytestmark = [pytest.mark.unit]


def test_roundtrip_preserves_values_and_encrypts_secrets():
    plain = {
        "access_token": "ya29.plain-access",
        "refresh_token": "1//plain-refresh",
        "expires_at": 1234567890.0,
        "token_type": "Bearer",
    }
    enc = encrypt_calendar_tokens(plain)
    assert enc["access_token"].startswith("enc:")
    assert enc["refresh_token"].startswith("enc:")
    assert enc["expires_at"] == 1234567890.0
    assert enc["token_type"] == "Bearer"
    dec = decrypt_calendar_tokens(enc)
    assert dec["access_token"] == "ya29.plain-access"
    assert dec["refresh_token"] == "1//plain-refresh"
    assert dec["expires_at"] == 1234567890.0


def test_decrypt_passes_through_legacy_plaintext():
    legacy = {"access_token": "ya29.legacy", "refresh_token": "1//legacy"}
    dec = decrypt_calendar_tokens(legacy)
    assert dec["access_token"] == "ya29.legacy"
    assert dec["refresh_token"] == "1//legacy"


def test_encrypt_is_idempotent():
    plain = {"access_token": "a", "refresh_token": "r"}
    once = encrypt_calendar_tokens(plain)
    twice = encrypt_calendar_tokens(once)
    assert once == twice


def test_none_and_empty_are_safe():
    assert encrypt_calendar_tokens(None) is None
    assert decrypt_calendar_tokens(None) is None
    assert encrypt_calendar_tokens({}) == {}


async def test_get_valid_access_token_returns_decrypted():
    """The sole token consumer must hand back a PLAINTEXT access token."""
    import calendar_service

    tokens = {
        "access_token": encrypt_value("ya29.real-access"),
        "refresh_token": encrypt_value("1//real-refresh"),
        "expires_at": 9999999999.0,  # far future -> no refresh, db untouched
    }
    result = await calendar_service.get_valid_access_token(tokens, MagicMock(), "rid-x")
    assert result == "ya29.real-access"
