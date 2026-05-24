"""
Tests for ``call_pipeline.classify_booking_intent`` — Duuutah AI's structured
booking-intent classifier used by the appointment-flow fallback path.

Pure function, no I/O, no LLM calls. We test every date-format branch:

- explicit ISO dates  ``2026-04-15``
- month + numeric day ``april 15th``
- month + word ordinal ``april fifth``
- relative ``today``, ``tomorrow``, ``day after tomorrow``
- named weekdays with ``this``/``next`` modifiers

…plus the early-exit guards (already confirmed, insufficient context,
no date found), the service-name resolution paths (exact / partial / single-
service fallback), and the timezone-sensitive ``today``/``tomorrow``
resolution against the restaurant's local time, not UTC.
"""

from __future__ import annotations

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _t(
    customer_text: str, ai_text: str = "When would you like to come in?"
) -> list[dict]:
    """Build a minimal transcript that satisfies the ≥2-turn guard."""
    return [
        {"role": "ai", "text": ai_text},
        {"role": "customer", "text": customer_text},
    ]


_SERVICES = [
    {"name": "Standard Haircut", "price_cents": 4500},
    {"name": "Color", "price_cents": 12000},
    {"name": "Blowout", "price_cents": 5500},
]


# ---------------------------------------------------------------------------
# Early-exit guards
# ---------------------------------------------------------------------------


def test_already_confirmed_short_circuits_to_zero_confidence():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("tomorrow at 3pm"),
        services=_SERVICES,
        order_state_confirmed=True,
    )
    assert intent.confidence == 0.0
    assert intent.trigger == "already_confirmed"


def test_insufficient_context_returns_zero_confidence():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=[{"role": "customer", "text": "tomorrow"}],
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.confidence == 0.0
    assert intent.trigger == "insufficient_context"


def test_no_date_found_returns_zero_confidence():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("I want to book something"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.confidence == 0.0
    assert intent.trigger == "no_date_found"


# ---------------------------------------------------------------------------
# ISO date branch (highest confidence)
# ---------------------------------------------------------------------------


def test_explicit_iso_date_yields_high_confidence():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("Can I book for 2026-04-15"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str == "2026-04-15"
    assert intent.trigger.startswith("iso_date")
    assert intent.confidence >= 0.5


# ---------------------------------------------------------------------------
# Month + numeric/word-ordinal day branch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,expected_month_day",
    [
        ("April 15th", ("04", "15")),
        ("march 29", ("03", "29")),
        ("July 4th", ("07", "04")),
        ("december 1st", ("12", "01")),
    ],
)
@freeze_time("2026-03-01T12:00:00+00:00")
def test_month_plus_numeric_day_resolves(phrase, expected_month_day):
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t(phrase),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str is not None
    month, day = intent.date_str.split("-")[1:]
    assert (month, day) == expected_month_day
    assert intent.trigger.startswith("month_day")


@pytest.mark.parametrize(
    "phrase,expected_month_day",
    [
        ("April fifth", ("04", "05")),
        ("march twenty-ninth", ("03", "29")),
        ("july fourth", ("07", "04")),
    ],
)
@freeze_time("2026-03-01T12:00:00+00:00")
def test_month_plus_word_ordinal_resolves(phrase, expected_month_day):
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t(phrase),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str is not None
    month, day = intent.date_str.split("-")[1:]
    assert (month, day) == expected_month_day
    assert intent.trigger.startswith("month_word_ordinal")


@freeze_time("2026-06-15T12:00:00+00:00")
def test_month_in_past_rolls_to_next_year():
    """An explicit February date with current month=June must roll to 2027."""
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("February 14th"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str == "2027-02-14"


# ---------------------------------------------------------------------------
# Relative date branch
# ---------------------------------------------------------------------------


@freeze_time("2026-04-10T12:00:00+00:00")
def test_relative_today():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("can I come in today"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str == "2026-04-10"
    assert intent.trigger.startswith("relative_today")


@freeze_time("2026-04-10T12:00:00+00:00")
def test_relative_tomorrow():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("tomorrow at 3pm please"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str == "2026-04-11"
    assert intent.trigger.startswith("relative_tomorrow")


@freeze_time("2026-04-10T12:00:00+00:00")
def test_day_after_tomorrow_phrase_currently_matches_tomorrow_first_captures_bug():
    """Captures bug: ``"tomorrow" in "day after tomorrow"`` is True (substring),
    so the ``tomorrow`` branch fires before ``day after tomorrow`` is checked.
    See FINDINGS.md 2026-05-23 — classify_booking_intent ordering bug.
    """
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("day after tomorrow"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    # Current (buggy) behavior: returns tomorrow's date, not two days out.
    assert intent.date_str == "2026-04-11"
    assert intent.trigger.startswith("relative_tomorrow")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "classify_booking_intent orders 'tomorrow' before 'day after tomorrow', "
        "so 'day after tomorrow' is shadowed. See FINDINGS.md 2026-05-23."
    ),
)
@freeze_time("2026-04-10T12:00:00+00:00")
def test_day_after_tomorrow_should_resolve_two_days_out_expected():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("day after tomorrow"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str == "2026-04-12"
    assert intent.trigger.startswith("relative_day_after")


# ---------------------------------------------------------------------------
# Named weekday branch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,expected_iso",
    [
        # frozen Friday 2026-04-10. "this monday" → next Monday = 2026-04-13.
        ("this monday", "2026-04-13"),
        ("next monday", "2026-04-20"),
        # "this friday" on Friday is interpreted as today (days_ahead=0).
        ("this friday", "2026-04-10"),
        ("next friday", "2026-04-17"),
        ("this sunday", "2026-04-12"),
    ],
)
@freeze_time("2026-04-10T12:00:00+00:00")
def test_named_weekday_resolves(phrase, expected_iso):
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t(phrase),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.date_str == expected_iso, f"phrase={phrase!r}"
    assert intent.trigger.startswith("weekday_")


# ---------------------------------------------------------------------------
# Timezone resolution: production bug was "today" computed in UTC instead of
# the restaurant's local timezone, which caused late-evening callers to get
# tomorrow's date.
# ---------------------------------------------------------------------------


@freeze_time("2026-04-10T03:30:00+00:00")  # 22:30 the previous day in America/Chicago
def test_today_resolves_against_local_timezone_not_utc():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("today please"),
        services=_SERVICES,
        order_state_confirmed=False,
        timezone_str="America/Chicago",
    )
    # In Chicago it is still April 9 — "today" must resolve to 2026-04-09,
    # not 2026-04-10 (UTC).
    assert intent.date_str == "2026-04-09"


# ---------------------------------------------------------------------------
# Service-name resolution
# ---------------------------------------------------------------------------


@freeze_time("2026-04-10T12:00:00+00:00")
def test_exact_service_name_match_wins():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("standard haircut tomorrow"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert intent.service_name == "Standard Haircut"
    assert "service=matched" in intent.trigger


@freeze_time("2026-04-10T12:00:00+00:00")
def test_partial_service_word_match():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("can I get a haircut tomorrow"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    # "haircut" is in "Standard Haircut" so the partial-word branch fires.
    assert intent.service_name == "Standard Haircut"


@freeze_time("2026-04-10T12:00:00+00:00")
def test_single_service_business_fallback():
    """One-service businesses always resolve to that one service when date is present."""
    from call_pipeline import classify_booking_intent

    services = [{"name": "Consultation"}]
    intent = classify_booking_intent(
        transcript=_t("tomorrow morning"),
        services=services,
        order_state_confirmed=False,
    )
    assert intent.service_name == "Consultation"
    assert "service=matched" in intent.trigger or "service=fallback" in intent.trigger


@freeze_time("2026-04-10T12:00:00+00:00")
def test_no_service_match_with_multiple_services_keeps_none():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("can I come tomorrow"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    # No service keyword found — service_name is None but date intent stands.
    assert intent.service_name is None
    assert intent.date_str == "2026-04-11"
    assert "service=fallback" in intent.trigger


# ---------------------------------------------------------------------------
# Confidence shape
# ---------------------------------------------------------------------------


@freeze_time("2026-04-10T12:00:00+00:00")
def test_iso_with_matched_service_is_most_confident():
    """ISO + exact service should outscore weekday + fallback service."""
    from call_pipeline import classify_booking_intent

    high = classify_booking_intent(
        transcript=_t("2026-04-15 standard haircut"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    low = classify_booking_intent(
        transcript=_t("this friday"),
        services=_SERVICES,
        order_state_confirmed=False,
    )
    assert high.confidence > low.confidence
    assert 0.0 <= high.confidence <= 1.0
    assert 0.0 <= low.confidence <= 1.0


@freeze_time("2026-04-10T12:00:00+00:00")
def test_empty_services_list_still_returns_intent_when_date_found():
    from call_pipeline import classify_booking_intent

    intent = classify_booking_intent(
        transcript=_t("tomorrow"),
        services=[],
        order_state_confirmed=False,
    )
    assert intent.date_str == "2026-04-11"
    assert intent.service_name is None
