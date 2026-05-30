"""
Unit tests for backend/security_utils.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 90% (security-critical).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# validate_phone
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phone,expected", [
    ("+15551234567", True),
    ("15551234567", True),
    ("+1 (555) 123-4567", True),
    ("555-123-4567", True),
    ("555.123.4567", True),
    ("+44 20 7946 0958", True),
    # Invalid:
    ("", False),
    ("0", False),
    ("0123", False),  # leading 0 disallowed by E.164
    ("abc", False),
    ("+", False),
])
def test_validate_phone(phone, expected):
    from security_utils import validate_phone
    assert validate_phone(phone) is expected


# ---------------------------------------------------------------------------
# normalize_e164
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "+18156932226",
    "8156932226",
    "(815) 693-2226",
    "815-693-2226",
    "815.693.2226",
    "18156932226",
    "  815 693 2226  ",
])
def test_normalize_e164_accepts_various_us_formats(raw):
    from security_utils import normalize_e164
    assert normalize_e164(raw) == "+18156932226"


def test_normalize_e164_passes_through_other_e164():
    from security_utils import normalize_e164
    # UK number in E.164 form (with spaces) should normalize unchanged.
    assert normalize_e164("+44 20 7946 0958") == "+442079460958"
    assert normalize_e164("+447911123456") == "+447911123456"


@pytest.mark.parametrize("empty", ["", None, "   "])
def test_normalize_e164_returns_empty_for_empty_input(empty):
    from security_utils import normalize_e164
    assert normalize_e164(empty) == ""


@pytest.mark.parametrize("bad", [
    "abc",
    "1234",         # too short to be a US 10-digit
    "+",
    "+0",
])
def test_normalize_e164_rejects_garbage(bad):
    from security_utils import normalize_e164
    with pytest.raises(ValueError):
        normalize_e164(bad)


# ---------------------------------------------------------------------------
# validate_phones_distinct
# ---------------------------------------------------------------------------

def test_validate_phones_distinct_passes_for_distinct():
    from security_utils import validate_phones_distinct
    # Should not raise.
    validate_phones_distinct(
        "+15551112222",
        "+15553334444",
        "+15555556666",
    )


def test_validate_phones_distinct_passes_for_partial_unset():
    from security_utils import validate_phones_distinct
    validate_phones_distinct("+15551112222", None, None)
    validate_phones_distinct("+15551112222", "", None)
    validate_phones_distinct(None, None, "+15553334444")


def test_validate_phones_distinct_rejects_phone_business_dupe():
    from security_utils import validate_phones_distinct
    with pytest.raises(ValueError) as exc_info:
        validate_phones_distinct("+15551112222", "+15551112222", "+15553334444")
    assert "phone_number" in str(exc_info.value)
    assert "business_phone" in str(exc_info.value)


def test_validate_phones_distinct_rejects_phone_escalation_dupe():
    from security_utils import validate_phones_distinct
    with pytest.raises(ValueError) as exc_info:
        validate_phones_distinct("+15551112222", "+15553334444", "+15551112222")
    assert "phone_number" in str(exc_info.value)
    assert "escalation_phone_number" in str(exc_info.value)


def test_validate_phones_distinct_rejects_business_escalation_dupe():
    from security_utils import validate_phones_distinct
    with pytest.raises(ValueError) as exc_info:
        validate_phones_distinct("+15551112222", "+15553334444", "+15553334444")
    assert "business_phone" in str(exc_info.value)
    assert "escalation_phone_number" in str(exc_info.value)


def test_validate_phones_distinct_compares_after_normalization():
    from security_utils import validate_phones_distinct
    # Same number, different formats — should be detected as duplicate.
    with pytest.raises(ValueError):
        validate_phones_distinct("+18156932226", "8156932226", None)
    with pytest.raises(ValueError):
        validate_phones_distinct(None, "(815) 693-2226", "+18156932226")


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("email,expected", [
    ("user@example.com", True),
    ("user.name+tag@sub.domain.io", True),
    ("a@b.co", True),
    ("", False),
    ("not-an-email", False),
    ("@missing-local.com", False),
    ("missing-domain@", False),
    ("user@.com", False),
])
def test_validate_email(email, expected):
    from security_utils import validate_email
    assert validate_email(email) is expected


# ---------------------------------------------------------------------------
# validate_uuid
# ---------------------------------------------------------------------------

def test_validate_uuid_accepts_canonical_form():
    from security_utils import validate_uuid
    assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True


def test_validate_uuid_is_case_insensitive():
    from security_utils import validate_uuid
    assert validate_uuid("550E8400-E29B-41D4-A716-446655440000") is True


@pytest.mark.parametrize("bad", [
    "",
    "not-a-uuid",
    "550e8400-e29b-41d4-a716",  # too short
    "550e8400e29b41d4a716446655440000",  # no hyphens
])
def test_validate_uuid_rejects_invalid(bad):
    from security_utils import validate_uuid
    assert validate_uuid(bad) is False


# ---------------------------------------------------------------------------
# sanitize_string
# ---------------------------------------------------------------------------

def test_sanitize_string_strips_whitespace():
    from security_utils import sanitize_string
    assert sanitize_string("  hello  ") == "hello"


def test_sanitize_string_strips_html_by_default():
    from security_utils import sanitize_string
    assert sanitize_string("Hello <script>alert(1)</script>") == "Hello alert(1)"


def test_sanitize_string_allows_html_when_opted_in():
    from security_utils import sanitize_string
    assert sanitize_string("<b>bold</b>", allow_html=True) == "<b>bold</b>"


def test_sanitize_string_truncates_to_max_length():
    from security_utils import sanitize_string
    assert sanitize_string("x" * 50, max_length=10) == "x" * 10


def test_sanitize_string_passes_empty():
    from security_utils import sanitize_string
    assert sanitize_string("") == ""
    assert sanitize_string(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# sanitize_for_log
# ---------------------------------------------------------------------------

def test_sanitize_for_log_redacts_sensitive_keys():
    from security_utils import sanitize_for_log
    data = {
        "username": "joe",
        "password": "hunter2",
        "api_key": "sk_secret",
        "token": "tok_abc",
    }
    out = sanitize_for_log(data)
    assert out["username"] == "joe"
    assert out["password"] == "***REDACTED***"
    assert out["api_key"] == "***REDACTED***"
    assert out["token"] == "***REDACTED***"


def test_sanitize_for_log_recurses_into_nested_dicts():
    from security_utils import sanitize_for_log
    out = sanitize_for_log({"outer": {"customer_phone": "+15551234567", "name": "Joe"}})
    assert out["outer"]["customer_phone"] == "***REDACTED***"
    assert out["outer"]["name"] == "Joe"


def test_sanitize_for_log_handles_lists():
    from security_utils import sanitize_for_log
    out = sanitize_for_log([{"password": "x"}, {"name": "y"}])
    assert out[0]["password"] == "***REDACTED***"
    assert out[1]["name"] == "y"


def test_sanitize_for_log_truncates_long_strings():
    from security_utils import sanitize_for_log
    long_str = "x" * 250
    result = sanitize_for_log(long_str)
    assert result.endswith("...")
    assert len(result) <= 110


def test_sanitize_for_log_accepts_custom_sensitive_fields():
    from security_utils import sanitize_for_log
    out = sanitize_for_log({"my_secret_value": "x"}, sensitive_fields={"my_secret_value"})
    assert out["my_secret_value"] == "***REDACTED***"


# ---------------------------------------------------------------------------
# create_safe_error / safe_error
# ---------------------------------------------------------------------------

def test_create_safe_error_returns_http_exception_without_leaking_internal():
    from security_utils import create_safe_error

    exc = create_safe_error(500, "Service unavailable", internal_error=RuntimeError("db down"))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 500
    assert exc.detail == "Service unavailable"


def test_safe_error_returns_known_message_for_known_key():
    from security_utils import safe_error
    exc = safe_error("auth_failed", status_code=401)
    assert exc.status_code == 401
    assert exc.detail == "Authentication failed"


def test_safe_error_falls_back_to_server_error_message():
    from security_utils import safe_error
    exc = safe_error("totally-unknown-key")
    assert exc.detail == "An unexpected error occurred"


# ---------------------------------------------------------------------------
# mask_phone / mask_email
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phone,expected", [
    ("", "****"),
    ("123", "****"),
    ("+15551234567", "****4567"),
    ("5551234567", "****4567"),
])
def test_mask_phone(phone, expected):
    from security_utils import mask_phone
    assert mask_phone(phone) == expected


@pytest.mark.parametrize("email,expected", [
    ("", "****@****"),
    ("not-an-email", "****@****"),
    ("a@b.com", "*@b.com"),
    ("ab@b.com", "**@b.com"),
    ("alice@example.com", "a***e@example.com"),
])
def test_mask_email(email, expected):
    from security_utils import mask_email
    assert mask_email(email) == expected


# ---------------------------------------------------------------------------
# validate_business_type / validate_appointment_status
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bt,expected", [
    ("restaurant", True),
    ("clinic", True),
    ("salon", True),
    ("home_services", True),
    ("legal", True),
    ("nothing", False),
    ("", False),
])
def test_validate_business_type(bt, expected):
    from security_utils import validate_business_type
    assert validate_business_type(bt) is expected


@pytest.mark.parametrize("status,expected", [
    ("confirmed", True),
    ("cancelled", True),
    ("completed", True),
    ("no_show", True),
    ("garbage", False),
    ("", False),
])
def test_validate_appointment_status(status, expected):
    from security_utils import validate_appointment_status
    assert validate_appointment_status(status) is expected


# ---------------------------------------------------------------------------
# validate_date_format / validate_time_format
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("date,expected", [
    ("2026-01-01", True),
    ("2026-12-31", True),
    ("2026-02-29", False),  # not a leap year
    ("01-01-2026", False),
    ("2026/01/01", False),
    ("", False),
    ("not-a-date", False),
])
def test_validate_date_format(date, expected):
    from security_utils import validate_date_format
    assert validate_date_format(date) is expected


@pytest.mark.parametrize("time_str,expected", [
    ("2:00 PM", True),
    ("2:00PM", True),
    ("14:00", True),
    ("9:30 AM", True),
    ("25:00", False),
    ("", False),
    ("not-a-time", False),
])
def test_validate_time_format(time_str, expected):
    from security_utils import validate_time_format
    assert validate_time_format(time_str) is expected
