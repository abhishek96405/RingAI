"""
Unit tests for backend/gemini_service.py — system prompt assembly.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module slice: contributes to >= 75% overall.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


MINIMAL_MENU = [
    {
        "id": "m1",
        "name": "Cheese Pizza",
        "category": "Pizza",
        "price": 1299,
        "available": True,
        "allergens": ["dairy", "gluten"],
    },
    {
        "id": "m2",
        "name": "Garden Salad",
        "category": "Salad",
        "price": 799,
        "available": True,
        "allergens": [],
    },
]


# ---------------------------------------------------------------------------
# calculate_is_open
# ---------------------------------------------------------------------------

def test_is_open_returns_true_when_no_hours():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=None) is True


def test_is_open_returns_false_when_closed_day():
    """A closed day should return False regardless of time."""
    from gemini_service import calculate_is_open
    # We can't easily mock datetime.now without patching tz; instead, give every
    # day a closed flag — at least one will be hit.
    hours = {d: {"closed": True} for d in
             ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is False


def test_is_open_returns_true_when_hours_unparseable():
    """If hours contain bad time strings, default is True."""
    from gemini_service import calculate_is_open
    hours = {d: {"open": "not-a-time", "close": "also-bad"} for d in
             ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is True


def test_is_open_uses_24h_open_window():
    """A 00:00 → 23:59 window means always open."""
    from gemini_service import calculate_is_open
    hours = {d: {"open": "00:00", "close": "23:59"} for d in
             ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is True


def test_is_open_handles_invalid_timezone_gracefully():
    """A bogus timezone should not crash."""
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=None, restaurant_timezone="Not/A/TZ") is True


# ---------------------------------------------------------------------------
# build_system_prompt — smoke checks on prompt content
# ---------------------------------------------------------------------------

def _build(**overrides):
    from gemini_service import build_system_prompt
    defaults = dict(
        restaurant_name="Tasty Bites",
        cuisine_type="italian",
        persona="friendly",
        business_rules=["No cash"],
        escalation_rules=["Manager request"],
        menu_items=MINIMAL_MENU,
        disclosure_text="Hi, I'm an AI assistant for Tasty Bites.",
        upsell_enabled=True,
        offers_delivery=True,
        offers_reservations=False,
        delivery_enabled=True,
        delivery_minimum=1500,
        avg_prep_time_minutes=20,
        operating_hours={d: {"open": "11:00", "close": "22:00"} for d in
                         ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
        restaurant_timezone="UTC",
        plan="STARTER",
        lang="en",
    )
    defaults.update(overrides)
    return build_system_prompt(**defaults)


def test_prompt_includes_restaurant_name():
    out = _build()
    assert "Tasty Bites" in out


def test_prompt_includes_menu_items():
    out = _build()
    assert "Cheese Pizza" in out
    assert "Garden Salad" in out


def test_prompt_includes_business_rules():
    out = _build()
    assert "No cash" in out


def test_prompt_handles_disclosure_text_param_without_crashing():
    """disclosure_text is plumbed into build_system_prompt; the function must accept and not crash."""
    out = _build(disclosure_text="anything goes here")
    assert isinstance(out, str) and len(out) > 100


def test_prompt_starter_plan_disables_delivery_with_escalation_block():
    out = _build(plan="STARTER", offers_delivery=True)
    # On STARTER, delivery is escalated
    assert "ESCALATE_TO_HUMAN" in out


def test_prompt_premium_plan_keeps_delivery_enabled():
    """A PRO/PRO plan should keep the delivery flow active.

    Plans may not all be present in PLAN_CONFIG; if KeyError, the code
    falls back to defaults that keep delivery on.
    """
    out = _build(plan="PRO", offers_delivery=True)
    # The prompt should mention delivery somewhere
    assert "delivery" in out.lower()


@pytest.mark.parametrize("lang", ["en", "te", "hi", "es"])
def test_prompt_lang_param_passes_through(lang):
    out = _build(lang=lang)
    assert isinstance(out, str) and len(out) > 100


def test_prompt_telugu_includes_telugu_section():
    out = _build(lang="te")
    # Telugu section in _build_language_section uses "TELUGU"
    assert "TELUGU" in out or "తెలుగు" in out


def test_prompt_hindi_includes_hindi_section():
    out = _build(lang="hi")
    assert "HINDI" in out or "हिंदी" in out


def test_prompt_spanish_includes_spanish_section():
    out = _build(lang="es")
    assert "SPANISH" in out or "Español" in out


def test_prompt_with_customer_profile_on_premium_plan_includes_returning_greeting():
    """STARTER plan disables customer recognition; on a plan with it enabled, the name appears."""
    out = _build(
        plan="PRO",
        customer_profile={
            "last_name": "Alice",
            "visit_count": 5,
            "last_order": {"items": [{"name": "Cheese Pizza"}]},
        },
    )
    # Premium plan keeps customer_profile, so Alice's name should make it into the prompt
    assert "Alice" in out


def test_prompt_starter_plan_ignores_customer_profile():
    """STARTER plan disables customer_recognition; profile should not bleed through."""
    out = _build(
        plan="STARTER",
        customer_profile={
            "last_name": "ALICE-SHOULD-NOT-APPEAR",
            "visit_count": 1,
            "last_order": {"items": []},
        },
    )
    assert "ALICE-SHOULD-NOT-APPEAR" not in out


def test_prompt_premium_with_or_without_upsell_differs():
    """On PRO (upsell available), the upsell flag actually changes the prompt."""
    with_upsell = _build(plan="PRO", upsell_enabled=True)
    without_upsell = _build(plan="PRO", upsell_enabled=False)
    assert with_upsell != without_upsell
