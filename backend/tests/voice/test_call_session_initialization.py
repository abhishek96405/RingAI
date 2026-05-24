"""
Tests for :class:`call_pipeline.CallSession` constructor and default state.

The Duuutah AI call session is the per-call state machine. Init bugs surface
as wrong defaults that cascade into hangup loops, duplicated dispatches, or
silent failures. We pin every default explicitly so a refactor that drops
a flag will fail loudly here.
"""

from __future__ import annotations

import pytest
from gemini_service import LiveOrder, MenuIndex, OrderState

pytestmark = pytest.mark.voice


def test_constructor_records_identifying_fields(make_call_session):
    sess = make_call_session(
        call_sid="abc123",
        restaurant_id="rest_xyz",
        caller_number="+15555550199",
    )
    assert sess.call_sid == "abc123"
    assert sess.restaurant_id == "rest_xyz"
    assert sess.caller_number == "+15555550199"


def test_menu_index_constructed_from_menu_items(make_call_session, minimal_menu):
    sess = make_call_session()
    assert isinstance(sess.menu_index, MenuIndex)
    # Find should resolve the seeded menu names.
    assert sess.menu_index.find("Margherita Pizza")["id"] == "m_pizza"
    assert sess.menu_index.find("Chicken Biryani")["id"] == "m_biryani"


def test_transcript_starts_empty(make_call_session):
    sess = make_call_session()
    assert sess.transcript == []


def test_order_initialised_with_call_identifiers(make_call_session):
    sess = make_call_session(
        call_sid="cs_test", restaurant_id="r_test", caller_number="+1"
    )
    assert isinstance(sess.order, LiveOrder)
    assert sess.order.call_sid == "cs_test"
    assert sess.order.restaurant_id == "r_test"
    assert sess.order.caller_number == "+1"
    assert sess.order.state == OrderState.GREETING


@pytest.mark.parametrize(
    "flag_attr",
    [
        "_order_dispatched",
        "_order_confirmed_handled",
        "_escalated",
        "_escalation_deferred",
        "_hangup_scheduled",
        "_booking_dispatched",
        "_reservation_dispatched",
    ],
)
def test_lifecycle_flags_default_false(make_call_session, flag_attr):
    sess = make_call_session()
    assert getattr(sess, flag_attr) is False, f"{flag_attr} must default to False"


def test_counters_and_optional_fields_default(make_call_session):
    sess = make_call_session()
    assert sess._appointment_total == 0
    assert sess._sms_count == 0
    assert sess._detected_order_type is None
    assert sess._call_timer_task is None
    assert sess._actual_duration_seconds is None
    assert sess._pipeline_task is None
    assert sess._on_call_complete is None


def test_started_at_is_isoformat(make_call_session):
    from datetime import datetime

    sess = make_call_session()
    # Must round-trip as ISO 8601 with timezone.
    parsed = datetime.fromisoformat(sess.started_at)
    assert parsed.tzinfo is not None


def test_business_type_defaults_to_restaurant_when_config_missing_field(
    make_call_session,
):
    sess = make_call_session(config={"escalation_phone_number": "+1"})
    assert sess.business_type == "restaurant"


def test_business_type_honors_config_value(make_call_session):
    sess = make_call_session(business_type="salon")
    assert sess.business_type == "salon"


def test_business_type_defaults_to_restaurant_when_config_is_none():
    """The CallSession ``config or {}.get(...)`` pattern handles None config."""
    import call_pipeline

    sess = call_pipeline.CallSession(
        call_sid="cs",
        restaurant_id="r",
        caller_number="+1",
        restaurant={"name": "Test"},
        config=None,
        menu_items=[],
    )
    assert sess.business_type == "restaurant"
    assert sess.config is None


def test_services_list_defaults_to_empty(make_call_session):
    sess = make_call_session()
    assert sess.services == []


def test_services_list_used_when_provided(make_call_session):
    svc = [{"name": "Haircut", "price_cents": 4500}]
    sess = make_call_session(business_type="salon", services=svc)
    assert sess.services == svc


def test_lang_default_english(make_call_session):
    sess = make_call_session()
    assert sess.lang == "en"


def test_lang_honors_override(make_call_session):
    sess = make_call_session(lang="te")
    assert sess.lang == "te"


def test_is_open_starts_true(make_call_session):
    """is_open is set True at init; create_call_pipeline rewrites based on hours."""
    sess = make_call_session()
    assert sess.is_open is True


def test_db_starts_none(make_call_session):
    sess = make_call_session()
    assert sess.db is None
