"""
Unit tests for backend/gemini_service.py operating-hours normalization:
  - normalize_day_hours / get_effective_periods (the shared helper)
  - calculate_is_open, exercised for split hours + the kitchen last-call offset.

Covers backward compatibility (old {open,close} shape), split hours (multiple
service periods per day), the per-day last-call offset applied to every period,
collapsed-period dropping, and preservation of the existing overnight behavior.

No network I/O, no Mongo. 2026-06-15 is a Monday; all freezes below are Monday
in UTC so the frozen weekday matches the "monday" key under test.
"""
from __future__ import annotations

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

ALL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _every_day(day_config: dict) -> dict:
    """Same config for every weekday (so the frozen 'today' always matches)."""
    return {d: dict(day_config) for d in ALL_DAYS}


# ---------------------------------------------------------------------------
# normalize_day_hours — canonical shape + backward compatibility
# ---------------------------------------------------------------------------

def test_normalize_old_shape_becomes_single_period():
    from gemini_service import normalize_day_hours
    norm = normalize_day_hours({"closed": False, "open": "09:00", "close": "21:00"})
    assert norm["closed"] is False
    assert norm["last_call_offset_minutes"] == 0
    assert norm["periods"] == [{"open": "09:00", "close": "21:00"}]


def test_normalize_new_shape_passthrough_with_offset():
    from gemini_service import normalize_day_hours
    norm = normalize_day_hours({
        "closed": False,
        "last_call_offset_minutes": 30,
        "periods": [{"open": "10:00", "close": "15:00"}, {"open": "18:00", "close": "22:00"}],
    })
    assert norm["last_call_offset_minutes"] == 30
    assert norm["periods"] == [{"open": "10:00", "close": "15:00"}, {"open": "18:00", "close": "22:00"}]


def test_normalize_missing_offset_defaults_zero():
    from gemini_service import normalize_day_hours
    norm = normalize_day_hours({"closed": False, "periods": [{"open": "09:00", "close": "17:00"}]})
    assert norm["last_call_offset_minutes"] == 0


def test_normalize_closed_day_has_no_periods():
    from gemini_service import normalize_day_hours
    norm = normalize_day_hours({"closed": True, "open": "09:00", "close": "21:00"})
    assert norm["closed"] is True
    assert norm["periods"] == []


def test_normalize_negative_and_garbage_offset_clamped_to_zero():
    from gemini_service import normalize_day_hours
    assert normalize_day_hours({"open": "9:00", "close": "17:00", "last_call_offset_minutes": -5})["last_call_offset_minutes"] == 0
    assert normalize_day_hours({"open": "9:00", "close": "17:00", "last_call_offset_minutes": "oops"})["last_call_offset_minutes"] == 0


# ---------------------------------------------------------------------------
# get_effective_periods — last-call offset + collapse dropping
# ---------------------------------------------------------------------------

def test_effective_periods_no_offset_returns_posted_close():
    from gemini_service import get_effective_periods
    day = {"open": "09:00", "close": "21:00"}
    assert get_effective_periods(day, apply_last_call=True) == [{"open": "09:00", "close": "21:00"}]


def test_effective_periods_apply_last_call_pulls_close_earlier():
    from gemini_service import get_effective_periods
    day = {"last_call_offset_minutes": 30, "periods": [{"open": "09:00", "close": "21:00"}]}
    assert get_effective_periods(day, apply_last_call=True) == [{"open": "09:00", "close": "20:30"}]
    # Reservation/appointment path ignores the offset entirely.
    assert get_effective_periods(day, apply_last_call=False) == [{"open": "09:00", "close": "21:00"}]


def test_effective_periods_offset_applied_to_each_period():
    from gemini_service import get_effective_periods
    day = {
        "last_call_offset_minutes": 30,
        "periods": [{"open": "10:00", "close": "15:00"}, {"open": "18:00", "close": "22:00"}],
    }
    assert get_effective_periods(day, apply_last_call=True) == [
        {"open": "10:00", "close": "14:30"},
        {"open": "18:00", "close": "21:30"},
    ]


def test_effective_periods_collapsed_period_is_dropped_not_overnight():
    from gemini_service import get_effective_periods
    # A 20-minute window with a 30-minute offset collapses. It must be DROPPED,
    # never reinterpreted as an overnight (close <= open) window.
    day = {"last_call_offset_minutes": 30, "periods": [{"open": "12:00", "close": "12:20"}]}
    assert get_effective_periods(day, apply_last_call=True) == []
    # Without the offset the same period is perfectly valid.
    assert get_effective_periods(day, apply_last_call=False) == [{"open": "12:00", "close": "12:20"}]


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 1: old shape, no regression
# ---------------------------------------------------------------------------

@freeze_time("2026-06-15T12:00:00+00:00")  # Monday 12:00 UTC
def test_old_shape_open_inside_window():
    from gemini_service import calculate_is_open
    hours = _every_day({"closed": False, "open": "09:00", "close": "21:00"})
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is True


@freeze_time("2026-06-15T22:00:00+00:00")  # Monday 22:00 UTC
def test_old_shape_closed_outside_window():
    from gemini_service import calculate_is_open
    hours = _every_day({"closed": False, "open": "09:00", "close": "21:00"})
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is False


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 2: split hours (open, midday gap, open)
# ---------------------------------------------------------------------------

SPLIT_DAY = {"closed": False, "periods": [{"open": "10:00", "close": "15:00"},
                                          {"open": "18:00", "close": "22:00"}]}


@freeze_time("2026-06-15T12:00:00+00:00")  # inside lunch
def test_split_hours_open_during_first_period():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_DAY), restaurant_timezone="UTC") is True


@freeze_time("2026-06-15T16:00:00+00:00")  # midday gap
def test_split_hours_closed_in_midday_gap():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_DAY), restaurant_timezone="UTC") is False


@freeze_time("2026-06-15T19:00:00+00:00")  # inside dinner
def test_split_hours_open_during_second_period():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_DAY), restaurant_timezone="UTC") is True


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 3: last-call offset boundary
# close 21:00, offset 30 → kitchen cut-off 20:30 (closed AT the cut-off onward)
# ---------------------------------------------------------------------------

OFFSET_DAY = {"closed": False, "last_call_offset_minutes": 30,
              "periods": [{"open": "09:00", "close": "21:00"}]}


@freeze_time("2026-06-15T20:29:00+00:00")  # cut-off − 1 min
def test_last_call_still_open_one_minute_before_cutoff():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(OFFSET_DAY), restaurant_timezone="UTC") is True


@freeze_time("2026-06-15T20:30:00+00:00")  # exactly the cut-off
def test_last_call_closed_at_cutoff():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(OFFSET_DAY), restaurant_timezone="UTC") is False


@freeze_time("2026-06-15T20:45:00+00:00")  # between cut-off and posted close
def test_last_call_closed_between_cutoff_and_posted_close():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(OFFSET_DAY), restaurant_timezone="UTC") is False


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 4: offset applied to EACH period independently
# lunch 10-15 (cut-off 14:30), dinner 18-22 (cut-off 21:30), offset 30
# ---------------------------------------------------------------------------

SPLIT_OFFSET_DAY = {"closed": False, "last_call_offset_minutes": 30,
                    "periods": [{"open": "10:00", "close": "15:00"},
                                {"open": "18:00", "close": "22:00"}]}


@freeze_time("2026-06-15T14:29:00+00:00")  # 1 min before lunch cut-off
def test_split_offset_lunch_open_before_cutoff():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_OFFSET_DAY), restaurant_timezone="UTC") is True


@freeze_time("2026-06-15T14:30:00+00:00")  # lunch cut-off → closed (in gap)
def test_split_offset_lunch_closed_at_cutoff():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_OFFSET_DAY), restaurant_timezone="UTC") is False


@freeze_time("2026-06-15T21:29:00+00:00")  # 1 min before dinner cut-off
def test_split_offset_dinner_open_before_cutoff():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_OFFSET_DAY), restaurant_timezone="UTC") is True


@freeze_time("2026-06-15T21:30:00+00:00")  # dinner cut-off → closed
def test_split_offset_dinner_closed_at_cutoff():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(SPLIT_OFFSET_DAY), restaurant_timezone="UTC") is False


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 5: closed day is always closed
# ---------------------------------------------------------------------------

@freeze_time("2026-06-15T12:00:00+00:00")
def test_closed_day_always_closed_even_with_periods():
    from gemini_service import calculate_is_open
    hours = _every_day({"closed": True, "last_call_offset_minutes": 30,
                        "periods": [{"open": "10:00", "close": "22:00"}]})
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is False


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 6: collapsed period → closed (not overnight)
# ---------------------------------------------------------------------------

@freeze_time("2026-06-15T12:10:00+00:00")  # inside the posted 12:00–12:20 window
def test_collapsed_period_reads_closed_not_open_all_day():
    from gemini_service import calculate_is_open
    # 20-min window, 30-min offset → collapses and is dropped. If it were wrongly
    # treated as overnight (11:50 <= open) the restaurant would read OPEN here.
    hours = _every_day({"closed": False, "last_call_offset_minutes": 30,
                        "periods": [{"open": "12:00", "close": "12:20"}]})
    assert calculate_is_open(operating_hours=hours, restaurant_timezone="UTC") is False


# ---------------------------------------------------------------------------
# calculate_is_open — scenario 7: existing overnight behavior preserved
# 18:00 → 02:00 wraps past midnight.
# ---------------------------------------------------------------------------

OVERNIGHT_DAY = {"closed": False, "open": "18:00", "close": "02:00"}


@freeze_time("2026-06-15T01:00:00+00:00")  # Monday 01:00 — within the wrap
def test_overnight_open_after_midnight():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(OVERNIGHT_DAY), restaurant_timezone="UTC") is True


@freeze_time("2026-06-15T03:00:00+00:00")  # Monday 03:00 — after the wrap close
def test_overnight_closed_after_wrap_close():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(OVERNIGHT_DAY), restaurant_timezone="UTC") is False


@freeze_time("2026-06-15T20:00:00+00:00")  # Monday 20:00 — evening open side
def test_overnight_open_in_evening():
    from gemini_service import calculate_is_open
    assert calculate_is_open(operating_hours=_every_day(OVERNIGHT_DAY), restaurant_timezone="UTC") is True


# ---------------------------------------------------------------------------
# build_system_prompt — the restaurant prompt builder must reflect split hours
# and the kitchen last-call offset in BOTH its CURRENT STATUS line (which used
# to be a duplicate, old-shape-only is-open check) and its OPERATING HOURS list
# (which used to render "?" for a new-shape day).
# ---------------------------------------------------------------------------

def _build_prompt(**overrides) -> str:
    from gemini_service import build_system_prompt
    defaults = dict(
        restaurant_name="Tasty Bites",
        cuisine_type="italian",
        persona="friendly",
        business_rules=["No cash"],
        escalation_rules=["Manager request"],
        menu_items=[{"id": "m1", "name": "Cheese Pizza", "category": "Pizza",
                     "price": 1299, "available": True, "allergens": []}],
        disclosure_text="Hi, I'm an AI assistant for Tasty Bites.",
        upsell_enabled=True,
        offers_delivery=True,
        offers_reservations=False,
        delivery_enabled=True,
        delivery_minimum=1500,
        avg_prep_time_minutes=20,
        restaurant_timezone="UTC",
        plan="STARTER",
        lang="en",
    )
    defaults.update(overrides)
    return build_system_prompt(**defaults)


# Split hours: lunch 10:00–15:00, dinner 18:00–22:00, 30-min kitchen last-call
# (lunch cut-off 14:30, dinner cut-off 21:30).
PROMPT_SPLIT_DAY = {"closed": False, "last_call_offset_minutes": 30,
                    "periods": [{"open": "10:00", "close": "15:00"},
                                {"open": "18:00", "close": "22:00"}]}


@freeze_time("2026-06-15T12:00:00+00:00")  # inside lunch
def test_prompt_status_open_during_first_period():
    out = _build_prompt(operating_hours=_every_day(PROMPT_SPLIT_DAY))
    assert "CURRENT STATUS: The restaurant is currently OPEN." in out


@freeze_time("2026-06-15T16:00:00+00:00")  # midday gap
def test_prompt_status_closed_in_midday_gap():
    out = _build_prompt(operating_hours=_every_day(PROMPT_SPLIT_DAY))
    assert "CURRENT STATUS: The restaurant is currently CLOSED." in out


@freeze_time("2026-06-15T19:00:00+00:00")  # inside dinner
def test_prompt_status_open_during_second_period():
    out = _build_prompt(operating_hours=_every_day(PROMPT_SPLIT_DAY))
    assert "CURRENT STATUS: The restaurant is currently OPEN." in out


@freeze_time("2026-06-15T21:45:00+00:00")  # past dinner last-call (21:30)
def test_prompt_status_closed_after_last_call():
    out = _build_prompt(operating_hours=_every_day(PROMPT_SPLIT_DAY))
    assert "CURRENT STATUS: The restaurant is currently CLOSED." in out


@freeze_time("2026-06-15T12:00:00+00:00")  # Monday noon
def test_prompt_status_old_shape_open_no_regression():
    hours = _every_day({"closed": False, "open": "11:00", "close": "22:00"})
    out = _build_prompt(operating_hours=hours)
    assert "CURRENT STATUS: The restaurant is currently OPEN." in out


@freeze_time("2026-06-15T23:00:00+00:00")  # Monday 23:00, past 22:00 close
def test_prompt_status_old_shape_closed_no_regression():
    hours = _every_day({"closed": False, "open": "11:00", "close": "22:00"})
    out = _build_prompt(operating_hours=hours)
    assert "CURRENT STATUS: The restaurant is currently CLOSED." in out


@freeze_time("2026-06-15T12:00:00+00:00")
def test_prompt_hours_display_split_day_shows_both_ranges():
    out = _build_prompt(operating_hours=_every_day(PROMPT_SPLIT_DAY))
    # Posted hours (NOT the last-call cut-off): both ranges, no "?" placeholder.
    assert "  Monday: 10:00 – 15:00, 18:00 – 22:00" in out


@freeze_time("2026-06-15T12:00:00+00:00")
def test_prompt_hours_display_old_shape_byte_identical():
    hours = _every_day({"closed": False, "open": "11:00", "close": "22:00"})
    out = _build_prompt(operating_hours=hours)
    # Exactly the pre-change rendering: two-space indent, en-dash separator, 24h.
    assert "  Monday: 11:00 – 22:00" in out


@freeze_time("2026-06-15T12:00:00+00:00")
def test_prompt_hours_display_closed_day_unchanged():
    hours = _every_day({"closed": False, "open": "11:00", "close": "22:00"})
    hours["monday"] = {"closed": True}
    out = _build_prompt(operating_hours=hours)
    assert "  Monday: Closed" in out
