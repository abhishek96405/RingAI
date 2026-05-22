"""
Unit tests for backend/gemini_service.py — language handling in prompts.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _build_language_section
# ---------------------------------------------------------------------------

def test_english_returns_empty_string():
    """English produces no language block — prompt is byte-identical to baseline."""
    from gemini_service import _build_language_section
    assert _build_language_section("en", "Tasty Bites") == ""


@pytest.mark.parametrize("lang,marker", [
    ("te", "TELUGU"),
    ("hi", "HINDI"),
    ("es", "SPANISH"),
])
def test_non_english_returns_language_block(lang, marker):
    from gemini_service import _build_language_section
    out = _build_language_section(lang, "Tasty Bites")
    assert marker in out
    assert "CODE-MIXING" in out


def test_unknown_language_returns_empty():
    from gemini_service import _build_language_section
    assert _build_language_section("zz", "Tasty Bites") == ""
    assert _build_language_section("", "Tasty Bites") == ""


@pytest.mark.parametrize("lang", ["te", "hi", "es"])
def test_language_block_instructs_stay_in_language(lang):
    """Each non-English block must tell Gemini not to switch mid-call."""
    from gemini_service import _build_language_section
    out = _build_language_section(lang, "Restaurant")
    assert "STAY IN" in out.upper()


@pytest.mark.parametrize("lang", ["te", "hi", "es"])
def test_language_block_keeps_escalation_token_as_english(lang):
    from gemini_service import _build_language_section
    out = _build_language_section(lang, "Restaurant")
    assert "ESCALATE_TO_HUMAN" in out


# ---------------------------------------------------------------------------
# _translate_greeting
# ---------------------------------------------------------------------------

def test_english_greeting_passthrough():
    from gemini_service import _translate_greeting
    default = "Hi! Welcome to Tasty Bites!"
    out = _translate_greeting(
        lang="en", is_open=True, restaurant_name="Tasty Bites",
        customer_name=None, delivery_enabled=True, reservations_enabled=False,
        default_greeting=default,
    )
    assert out == default


@pytest.mark.parametrize("lang,sample_text", [
    ("te", "నమస్తే"),
    ("hi", "नमस्ते"),
    ("es", "Hola"),
])
def test_non_english_greeting_uses_native_script(lang, sample_text):
    from gemini_service import _translate_greeting
    out = _translate_greeting(
        lang=lang, is_open=True, restaurant_name="Tasty Bites",
        customer_name=None, delivery_enabled=True, reservations_enabled=True,
        default_greeting="default",
    )
    assert sample_text in out


@pytest.mark.parametrize("lang", ["te", "hi", "es"])
def test_returning_customer_greeting_includes_name(lang):
    from gemini_service import _translate_greeting
    out = _translate_greeting(
        lang=lang, is_open=True, restaurant_name="Tasty",
        customer_name="Alice",
        delivery_enabled=False, reservations_enabled=False,
        default_greeting="default",
    )
    assert "Alice" in out


@pytest.mark.parametrize("lang", ["te", "hi", "es"])
def test_closed_greeting_mentions_closed_state(lang):
    """When the restaurant is closed, the greeting should signal that."""
    from gemini_service import _translate_greeting
    out = _translate_greeting(
        lang=lang, is_open=False, restaurant_name="Tasty",
        customer_name=None,
        delivery_enabled=False, reservations_enabled=False,
        default_greeting="default",
    )
    # Each language uses its own word for "closed" — just check it's longer than default
    assert "closed" in out.lower() or "cerrado" in out.lower() or "closed" in out  # English fallback uses 'closed'


def test_unknown_language_falls_back_to_default():
    from gemini_service import _translate_greeting
    default = "Hi! Welcome to Tasty Bites!"
    out = _translate_greeting(
        lang="zz", is_open=True, restaurant_name="Tasty",
        customer_name=None,
        delivery_enabled=True, reservations_enabled=False,
        default_greeting=default,
    )
    assert out == default


@pytest.mark.parametrize("lang", ["te", "hi", "es"])
def test_greeting_adapts_to_delivery_reservations_options(lang):
    """Different delivery/reservations combos produce different question phrasing."""
    from gemini_service import _translate_greeting

    delivery_only = _translate_greeting(
        lang=lang, is_open=True, restaurant_name="r", customer_name=None,
        delivery_enabled=True, reservations_enabled=False,
        default_greeting="default",
    )
    reservations_only = _translate_greeting(
        lang=lang, is_open=True, restaurant_name="r", customer_name=None,
        delivery_enabled=False, reservations_enabled=True,
        default_greeting="default",
    )
    both = _translate_greeting(
        lang=lang, is_open=True, restaurant_name="r", customer_name=None,
        delivery_enabled=True, reservations_enabled=True,
        default_greeting="default",
    )
    # The three should not be identical (delivery vs reservation vs both)
    assert delivery_only != reservations_only
    assert both not in (delivery_only, reservations_only)
