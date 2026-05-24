"""
Tests for the cost / metrics block inside ``build_final_call_record``.

These assertions pin the cost computation that ends up in the admin
dashboard. Wrong tags or missing fields here become support escalations
because they directly shape per-call P&L.
"""

from __future__ import annotations

from gemini_service import OrderItem, OrderState

import pytest

pytestmark = pytest.mark.voice


def _seed_completed_order(sess, items=None):
    items = items or [
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    ]
    for it in items:
        sess.order.items.append(it)
    sess.order.transition(OrderState.COMPLETED, "test seed")


def test_cost_fields_are_present_with_zero_duration(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    record = sess.build_final_call_record()
    for key in (
        "cost_voice_cents",
        "cost_sms_cents",
        "cost_gemini_live_cents",
        "cost_gemini_extract_cents",
        "cost_total_cents",
        "gemini_extract_tokens",
        "sms_count",
        "duration_seconds_actual",
    ):
        assert key in record, f"{key} must be reported in final call record"


def test_explicit_duration_seconds_propagates(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    sess._actual_duration_seconds = 90  # 1.5 min → ceil(1.5)=2 → 2 * $0.0085 = $0.017
    record = sess.build_final_call_record()
    assert record["duration_seconds_actual"] == 90
    # $0.017 = 1.7 cents — assert the rounded representation.
    assert record["cost_voice_cents"] == pytest.approx(1.7, rel=0.01)


def test_sms_count_drives_sms_cost(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    sess._sms_count = 4
    record = sess.build_final_call_record()
    assert record["sms_count"] == 4
    # 4 SMS * $0.0083 = $0.0332 = 3.32 cents
    assert record["cost_sms_cents"] == pytest.approx(3.32, rel=0.01)


def test_cost_total_is_sum_of_components(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    sess._actual_duration_seconds = 60
    sess._sms_count = 2
    record = sess.build_final_call_record()
    component_sum = (
        record["cost_voice_cents"]
        + record["cost_sms_cents"]
        + record["cost_gemini_live_cents"]
        + record["cost_gemini_extract_cents"]
    )
    assert record["cost_total_cents"] == pytest.approx(component_sum, rel=0.0001)


def test_gemini_live_is_currently_free_preview(make_call_session):
    """Pin: Gemini Live audio is reported as $0 during the free-preview window.
    A regression that bills for it would show up here."""
    sess = make_call_session()
    _seed_completed_order(sess)
    sess._actual_duration_seconds = 600
    record = sess.build_final_call_record()
    assert record["cost_gemini_live_cents"] == 0


def test_business_type_appears_in_record(make_call_session):
    sess = make_call_session(business_type="salon")
    sess._appointment_total = 5000
    record = sess.build_final_call_record()
    assert record["business_type"] == "salon"


def test_kitchen_order_id_propagates(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    sess.order.kitchen_order_id = "POS-12345"
    record = sess.build_final_call_record()
    assert record["kitchen_order_id"] == "POS-12345"


def test_caller_name_set_from_order(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    sess.order.customer_name = "Jane Doe"
    record = sess.build_final_call_record()
    assert record["caller_name"] == "Jane Doe"


def test_caller_name_none_when_order_missing_name(make_call_session):
    sess = make_call_session()
    _seed_completed_order(sess)
    record = sess.build_final_call_record()
    assert record["caller_name"] is None
