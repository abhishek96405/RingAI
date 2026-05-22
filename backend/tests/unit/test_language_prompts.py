"""
Unit tests for backend/language_prompts.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

def test_supported_languages_present():
    from language_prompts import LANGUAGE_PROMPTS, LANGUAGE_NAMES
    assert set(LANGUAGE_PROMPTS) >= {"en", "te", "hi", "es"}
    assert set(LANGUAGE_NAMES) >= {"en", "te", "hi", "es"}


def test_language_names_have_native_and_latin():
    from language_prompts import LANGUAGE_NAMES
    for code, names in LANGUAGE_NAMES.items():
        assert "native" in names
        assert "latin" in names


# ---------------------------------------------------------------------------
# is_supported
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code,expected", [
    ("en", True),
    ("te", True),
    ("hi", True),
    ("es", True),
    ("fr", False),
    ("", False),
])
def test_is_supported(code, expected):
    from language_prompts import is_supported
    assert is_supported(code) is expected


# ---------------------------------------------------------------------------
# signals_for — short / empty inputs short-circuit to all-False
# ---------------------------------------------------------------------------

def test_signals_for_empty_text_returns_all_false():
    from language_prompts import signals_for
    result = signals_for("en", "")
    assert all(v is False for v in result.values())


def test_signals_for_very_short_text_returns_all_false():
    from language_prompts import signals_for
    result = signals_for("en", "hi")
    assert all(v is False for v in result.values())


# ---------------------------------------------------------------------------
# signals_for — English triggers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,signal", [
    ("Your order is confirmed.", "order_confirmed"),
    ("We got your order in.", "order_confirmed"),
    ("Your appointment is confirmed for 2 PM.", "appointment_confirmed"),
    ("Your reservation is confirmed.", "reservation_confirmed"),
    ("Table is reserved.", "reservation_confirmed"),
    ("I'll text you the menu.", "sending_menu_sms"),
    ("Have a great day!", "call_ending"),
    ("Thanks for calling.", "call_ending"),
])
def test_signals_for_english_triggers(text, signal):
    from language_prompts import signals_for
    result = signals_for("en", text)
    assert result[signal] is True, f"Expected {signal}=True for '{text}', got {result}"


# ---------------------------------------------------------------------------
# signals_for — Telugu, Hindi, Spanish
# ---------------------------------------------------------------------------

def test_signals_for_telugu_order_confirmed():
    from language_prompts import signals_for
    result = signals_for("te", "మీ order confirm చేశాను")
    assert result["order_confirmed"] is True


def test_signals_for_hindi_order_confirmed():
    from language_prompts import signals_for
    result = signals_for("hi", "आपका order confirm हो गया")
    assert result["order_confirmed"] is True


def test_signals_for_spanish_order_confirmed():
    from language_prompts import signals_for
    result = signals_for("es", "Su pedido está confirmado.")
    assert result["order_confirmed"] is True


def test_signals_for_english_fallback_in_telugu_locale():
    """An English confirmation phrase should still trigger when caller is Telugu."""
    from language_prompts import signals_for
    result = signals_for("te", "your order is confirmed.")
    assert result["order_confirmed"] is True


# ---------------------------------------------------------------------------
# signals_for — escalate_to_human is a literal English token
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "te", "hi", "es"])
def test_escalate_to_human_works_in_every_language(lang):
    from language_prompts import signals_for
    # Make text long enough to pass the 3-char guard
    text = "some pretext ESCALATE_TO_HUMAN now"
    result = signals_for(lang, text)
    assert result["escalate_to_human"] is True


@pytest.mark.parametrize("lang", ["en", "te", "hi", "es"])
def test_escalate_is_case_sensitive(lang):
    from language_prompts import signals_for
    # lowercase token must NOT trigger
    text = "some pretext escalate_to_human now"
    result = signals_for(lang, text)
    assert result["escalate_to_human"] is False


# ---------------------------------------------------------------------------
# Unknown language falls back to English
# ---------------------------------------------------------------------------

def test_unknown_language_falls_back_to_english():
    from language_prompts import signals_for
    result = signals_for("zz", "Your order is confirmed.")
    assert result["order_confirmed"] is True


# ---------------------------------------------------------------------------
# Case-insensitivity
# ---------------------------------------------------------------------------

def test_signals_are_case_insensitive():
    from language_prompts import signals_for
    upper = signals_for("en", "YOUR ORDER IS CONFIRMED")
    lower = signals_for("en", "your order is confirmed")
    mixed = signals_for("en", "YouR Order Is Confirmed")
    assert upper["order_confirmed"] is True
    assert lower["order_confirmed"] is True
    assert mixed["order_confirmed"] is True


# ---------------------------------------------------------------------------
# Triggers are exhaustive — return shape is stable
# ---------------------------------------------------------------------------

def test_signals_return_dict_always_has_all_keys():
    from language_prompts import signals_for
    result = signals_for("en", "your order is confirmed")
    expected_keys = {
        "order_confirmed",
        "escalate_to_human",
        "appointment_confirmed",
        "reservation_confirmed",
        "sending_menu_sms",
        "call_ending",
    }
    assert set(result.keys()) == expected_keys
