"""
Unit tests for backend/encryption_utils.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 90% (security-critical).
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_module_key(monkeypatch):
    """Encryption module caches the derived key in a global. Reset between tests."""
    import encryption_utils

    monkeypatch.setattr(encryption_utils, "_ENCRYPTION_KEY", None, raising=False)
    yield
    monkeypatch.setattr(encryption_utils, "_ENCRYPTION_KEY", None, raising=False)


# ---------------------------------------------------------------------------
# _get_encryption_key
# ---------------------------------------------------------------------------

def test_get_encryption_key_caches_first_derivation():
    import encryption_utils

    k1 = encryption_utils._get_encryption_key()
    k2 = encryption_utils._get_encryption_key()
    assert k1 is k2  # same bytes object — cached


def test_get_encryption_key_uses_dedicated_env_var(monkeypatch):
    import encryption_utils

    monkeypatch.setenv("ENCRYPTION_SECRET_KEY", "primary-secret-key")
    monkeypatch.setenv("CLERK_SECRET_KEY", "this-should-not-be-used")
    encryption_utils._ENCRYPTION_KEY = None

    k = encryption_utils._get_encryption_key()
    assert isinstance(k, bytes) and len(k) > 0


def test_get_encryption_key_falls_back_to_clerk(monkeypatch):
    import encryption_utils

    monkeypatch.delenv("ENCRYPTION_SECRET_KEY", raising=False)
    monkeypatch.setenv("CLERK_SECRET_KEY", "clerk-fallback")
    encryption_utils._ENCRYPTION_KEY = None

    k = encryption_utils._get_encryption_key()
    assert isinstance(k, bytes) and len(k) > 0


# ---------------------------------------------------------------------------
# encrypt_value / decrypt_value round-trip
# ---------------------------------------------------------------------------

def test_encrypt_then_decrypt_round_trip():
    from encryption_utils import encrypt_value, decrypt_value

    plaintext = "very-secret-api-token-12345"
    cipher = encrypt_value(plaintext)
    assert cipher.startswith("enc:")
    assert decrypt_value(cipher) == plaintext


def test_encrypt_value_passes_empty_through():
    from encryption_utils import encrypt_value
    assert encrypt_value("") == ""
    assert encrypt_value(None) is None  # type: ignore[arg-type]


def test_decrypt_value_passes_empty_through():
    from encryption_utils import decrypt_value
    assert decrypt_value("") == ""
    assert decrypt_value(None) is None  # type: ignore[arg-type]


def test_encrypt_value_does_not_double_encrypt():
    from encryption_utils import encrypt_value

    once = encrypt_value("sensitive")
    twice = encrypt_value(once)
    assert once == twice  # marker prevents double-encryption


def test_decrypt_passes_through_unmarked_value():
    """A plaintext that was never encrypted should be returned untouched."""
    from encryption_utils import decrypt_value
    assert decrypt_value("plain-text-not-encrypted") == "plain-text-not-encrypted"


def test_decrypt_with_invalid_token_returns_empty():
    from encryption_utils import decrypt_value
    assert decrypt_value("enc:garbage-not-a-real-fernet-token") == ""


def test_decrypt_with_tampered_ciphertext_returns_empty():
    """Tampering with the ciphertext must surface as a decryption failure (empty string)."""
    from encryption_utils import encrypt_value, decrypt_value

    cipher = encrypt_value("secret")
    # Flip a single character in the body to corrupt the MAC.
    tampered = cipher[:-2] + ("A" if cipher[-2] != "A" else "B") + cipher[-1]
    assert decrypt_value(tampered) == ""


# ---------------------------------------------------------------------------
# encrypt_sensitive_fields / decrypt_sensitive_fields
# ---------------------------------------------------------------------------

def test_encrypt_sensitive_fields_only_targets_named_keys():
    from encryption_utils import encrypt_sensitive_fields

    doc = {"name": "Joe", "api_token": "tok_123", "merchant_id": "m_42"}
    encrypted = encrypt_sensitive_fields(doc, {"api_token", "merchant_id"})

    assert encrypted["name"] == "Joe"
    assert encrypted["api_token"].startswith("enc:")
    assert encrypted["merchant_id"].startswith("enc:")
    # Should not mutate the original
    assert doc["api_token"] == "tok_123"


def test_encrypt_sensitive_fields_skips_missing_and_empty():
    from encryption_utils import encrypt_sensitive_fields

    doc = {"api_token": "", "other": "x"}
    encrypted = encrypt_sensitive_fields(doc, {"api_token", "absent_field"})
    assert encrypted["api_token"] == ""
    assert "absent_field" not in encrypted


def test_encrypt_sensitive_fields_passes_empty_doc():
    from encryption_utils import encrypt_sensitive_fields
    assert encrypt_sensitive_fields({}, {"x"}) == {}
    assert encrypt_sensitive_fields(None, {"x"}) is None  # type: ignore[arg-type]


def test_round_trip_through_encrypt_decrypt_sensitive_fields():
    from encryption_utils import encrypt_sensitive_fields, decrypt_sensitive_fields

    fields = {"api_token", "merchant_id"}
    doc = {"name": "Joe", "api_token": "tok_xyz", "merchant_id": "m_42"}

    encrypted = encrypt_sensitive_fields(doc, fields)
    decrypted = decrypt_sensitive_fields(encrypted, fields)

    assert decrypted["api_token"] == "tok_xyz"
    assert decrypted["merchant_id"] == "m_42"
    assert decrypted["name"] == "Joe"


# ---------------------------------------------------------------------------
# ENCRYPTED_CREDENTIAL_FIELDS — make sure the set lists the expected creds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected_field", [
    "clover_api_token",
    "square_access_token",
    "toast_client_secret",
    "google_calendar_tokens",
    "stripe_customer_id",
])
def test_encrypted_credential_fields_includes_expected(expected_field):
    from encryption_utils import ENCRYPTED_CREDENTIAL_FIELDS
    assert expected_field in ENCRYPTED_CREDENTIAL_FIELDS


# ---------------------------------------------------------------------------
# mask_for_display
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,show,expected", [
    ("", 4, "****"),
    ("abc", 4, "****"),
    ("abcd", 4, "****"),
    ("secret-token-12345", 4, "**************2345"),
    ("api_key_abcdef", 4, "**********cdef"),
])
def test_mask_for_display_shows_only_trailing_chars(value, show, expected):
    from encryption_utils import mask_for_display
    assert mask_for_display(value, show_chars=show) == expected


# ---------------------------------------------------------------------------
# Hypothesis fuzz — round-trip on arbitrary text payloads
# ---------------------------------------------------------------------------

@given(text=st.text(min_size=1, max_size=500).filter(lambda s: not s.startswith("enc:")))
@settings(max_examples=50, deadline=None)
def test_encrypt_decrypt_round_trip_property(text):
    from encryption_utils import encrypt_value, decrypt_value
    assert decrypt_value(encrypt_value(text)) == text


@given(payload=st.binary(min_size=1, max_size=512).map(lambda b: b.hex()))
@settings(max_examples=30, deadline=None)
def test_encrypt_decrypt_round_trip_on_hex_blobs(payload):
    from encryption_utils import encrypt_value, decrypt_value
    assert decrypt_value(encrypt_value(payload)) == payload
