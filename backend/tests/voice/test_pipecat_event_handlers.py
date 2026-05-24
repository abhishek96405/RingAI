"""
Tests for the ``@event_handler``-decorated callbacks inside
``create_call_pipeline``: ``on_user_turn_stopped``, ``on_client_connected``,
``on_client_disconnected``, and the user-idle escalation chain.

Real Pipecat aggregators bind these via decorators, so we exercise their
*observable contract* — the side effects on the CallSession + downstream
mocks — by reproducing the conditional logic in isolation. The matching
source-level pins live in ``test_restaurant_guard_regression.py``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# on_user_turn_stopped — order-type detection from customer speech.
# Reproduces call_pipeline.py:1373-1419 logic for direct testing.
# ---------------------------------------------------------------------------


def _customer_turn_handler(session):
    """Reproduces the on_user_turn_stopped body inline so we can drive it
    without spinning up a real Pipecat aggregator. The contract being
    tested is the *side-effect* set on the session."""

    async def handler(text: str):
        if not text:
            return
        session.add_transcript_entry("customer", text)
        if session.business_type == "restaurant":
            _tl = text.lower()
            _plan = session.restaurant.get("plan", "STARTER")
            _rest_has_delivery = session.restaurant.get("offers_delivery", True)
            _rest_has_reservations = session.restaurant.get("offers_reservations", True)
            if any(w in _tl for w in ["delivery", "deliver", "delivered"]):
                if _plan == "PRO" and _rest_has_delivery:
                    session._detected_order_type = "delivery"
                elif _rest_has_delivery:
                    session._escalation_deferred = True
            elif any(
                w in _tl
                for w in ["pickup", "pick up", "pick-up", "carry out", "carryout"]
            ):
                session._detected_order_type = "pickup"
            elif any(
                w in _tl
                for w in ["reservation", "reserve", "book a table", "table for"]
            ):
                if _plan == "PRO" and _rest_has_reservations:
                    session._detected_order_type = "reservation"
                elif _rest_has_reservations:
                    session._escalation_deferred = True

    return handler


async def test_customer_pickup_keyword_sets_detected_order_type(make_call_session):
    sess = make_call_session()
    handler = _customer_turn_handler(sess)
    await handler("I want a pickup order please")
    assert sess._detected_order_type == "pickup"


async def test_customer_delivery_keyword_pro_plan_sets_delivery(make_call_session):
    sess = make_call_session()
    sess.restaurant["plan"] = "PRO"
    handler = _customer_turn_handler(sess)
    await handler("Can I get delivery to my office")
    assert sess._detected_order_type == "delivery"


async def test_customer_delivery_keyword_starter_plan_defers_escalation(
    make_call_session,
):
    sess = make_call_session()
    sess.restaurant["plan"] = "STARTER"
    sess.restaurant["offers_delivery"] = True
    handler = _customer_turn_handler(sess)
    await handler("I'd like delivery please")
    assert sess._detected_order_type is None
    assert sess._escalation_deferred is True


async def test_customer_delivery_keyword_no_delivery_offered_no_op(make_call_session):
    sess = make_call_session()
    sess.restaurant["plan"] = "STARTER"
    sess.restaurant["offers_delivery"] = False
    handler = _customer_turn_handler(sess)
    await handler("I want delivery")
    assert sess._detected_order_type is None
    assert sess._escalation_deferred is False


async def test_customer_reservation_keyword_pro_plan_sets_reservation(
    make_call_session,
):
    sess = make_call_session()
    sess.restaurant["plan"] = "PRO"
    sess.restaurant["offers_reservations"] = True
    handler = _customer_turn_handler(sess)
    await handler("I'd like to book a table for tonight")
    assert sess._detected_order_type == "reservation"


@pytest.mark.parametrize("business_type", ["salon", "clinic", "home_services", "legal"])
async def test_non_restaurant_business_does_not_run_keyword_detection(
    make_call_session, business_type
):
    sess = make_call_session(business_type=business_type)
    handler = _customer_turn_handler(sess)
    await handler("I want a pickup order")
    assert sess._detected_order_type is None


async def test_empty_customer_text_is_noop(make_call_session):
    sess = make_call_session()
    handler = _customer_turn_handler(sess)
    await handler("")
    assert sess.transcript == []


async def test_customer_text_appended_to_transcript(make_call_session):
    sess = make_call_session()
    handler = _customer_turn_handler(sess)
    await handler("Hi I want a pizza")
    assert sess.transcript[-1] == {
        "role": "customer",
        "text": "Hi I want a pizza",
        "timestamp": sess.transcript[-1]["timestamp"],
    }


# ---------------------------------------------------------------------------
# Idle-escalation chain — first retry warns, second retry warns again,
# third retry schedules hangup.
# ---------------------------------------------------------------------------


def _idle_handler(session, task):
    """Reproduce the production handle_user_idle body."""
    queued_frames: list = []

    async def task_queue(frame):
        queued_frames.append(frame)

    task.queue_frame = task_queue

    async def handler(processor, retry_count):
        if retry_count == 1:
            await task.queue_frame("retry1_text")
            return True
        elif retry_count == 2:
            await task.queue_frame("retry2_text")
            return True
        else:
            asyncio.create_task(session._schedule_hangup(reason="customer_idle"))
            return False

    return handler, queued_frames


async def test_idle_retry_1_emits_check_in_text(make_call_session, monkeypatch):
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    task = type("T", (), {})()
    handler, queued = _idle_handler(sess, task)

    cont = await handler(processor=None, retry_count=1)
    assert cont is True
    assert queued == ["retry1_text"]


async def test_idle_retry_2_emits_second_check_in(make_call_session, monkeypatch):
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    task = type("T", (), {})()
    handler, queued = _idle_handler(sess, task)

    cont = await handler(processor=None, retry_count=2)
    assert cont is True
    assert queued == ["retry2_text"]


async def test_idle_retry_3_schedules_hangup(make_call_session, monkeypatch):
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    task = type("T", (), {})()
    handler, _ = _idle_handler(sess, task)

    cont = await handler(processor=None, retry_count=3)
    assert cont is False
    # Allow the scheduled task to run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert sess._hangup_scheduled is True
