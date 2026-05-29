"""
State-machine tests for :class:`call_pipeline.CallSession`.

Covers signal detection, transcript handling, hangup scheduling guards,
and the order-confirmed / appointment-confirmed dispatch flows. Downstream
side effects (kitchen dispatch, SMS, Telnyx transfer) are stubbed via the
fixtures in voice/conftest.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from gemini_service import LiveOrder, OrderState, OrderItem

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# add_transcript_entry — basic shape
# ---------------------------------------------------------------------------


def test_add_transcript_entry_appends_role_text_timestamp(make_call_session):
    sess = make_call_session()
    sess.add_transcript_entry("customer", "Hi")
    assert len(sess.transcript) == 1
    entry = sess.transcript[0]
    assert entry["role"] == "customer"
    assert entry["text"] == "Hi"
    assert "timestamp" in entry


def test_add_transcript_entry_customer_does_not_run_signal_detection(make_call_session):
    """Signal detection is gated on role == 'ai'; customer turns are stored verbatim."""
    sess = make_call_session()
    sess.add_transcript_entry(
        "customer", "Your order is confirmed"
    )  # signal phrase, wrong role
    assert sess.order.state == OrderState.GREETING  # unchanged


# ---------------------------------------------------------------------------
# ORDER_CONFIRMED signal flow
# ---------------------------------------------------------------------------


async def test_order_confirmed_signal_transitions_and_dispatches(
    make_call_session, stub_kitchen_dispatch
):
    sess = make_call_session()
    # Seed an order so dispatch has something to send.
    sess.order.items.append(
        OrderItem(
            name="Margherita Pizza",
            menu_item_id="m_pizza",
            category="Pizza",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMING, "ready for readback")

    sess.add_transcript_entry("ai", "ORDER_CONFIRMED")
    # Let the spawned async task run.
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert sess.order.state in (OrderState.CONFIRMED, OrderState.COMPLETED)
    assert sess._order_confirmed_handled is True


async def test_order_confirmed_with_no_items_attempts_extraction(
    make_call_session, stub_order_extraction
):
    """When the in-memory order has no items, dispatch retries extraction."""
    sess = make_call_session()

    # Make extraction return a valid order so dispatch succeeds.
    extracted = LiveOrder(
        restaurant_id="rest_voice_test",
        call_sid="test_call_001",
        caller_number="+15555550199",
        state=OrderState.CONFIRMED,
    )
    extracted.items.append(
        OrderItem(
            name="Chicken Biryani",
            menu_item_id="m_biryani",
            category="Mains",
            unit_price=1699,
            quantity=2,
        )
    )
    stub_order_extraction["return_value"] = extracted

    sess.order.transition(OrderState.CONFIRMED, "test setup")
    with patch(
        "call_pipeline.send_order_to_kitchen",
        AsyncMock(
            return_value={"success": True, "order_id": "k1", "method": "database"}
        ),
    ):
        result = await sess.dispatch_order_if_ready()
    assert result is True
    assert sess.order.items[0].name == "Chicken Biryani"
    assert sess.order.kitchen_order_id == "k1"


async def test_dispatch_skipped_when_already_dispatched(
    make_call_session, stub_kitchen_dispatch
):
    sess = make_call_session()
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMED, "test")
    sess._order_dispatched = True
    result = await sess.dispatch_order_if_ready()
    assert result is False
    assert stub_kitchen_dispatch["sends"] == []  # nothing dispatched


async def test_dispatch_rejected_when_state_not_confirmed(
    make_call_session, stub_kitchen_dispatch
):
    sess = make_call_session()
    # State is GREETING — dispatch_order_if_ready returns False.
    assert sess.order.state == OrderState.GREETING
    result = await sess.dispatch_order_if_ready()
    assert result is False


async def test_repeated_order_confirmed_only_handled_once(
    make_call_session, stub_kitchen_dispatch
):
    """Re-entry guard: ``_order_confirmed_handled`` blocks the second call."""
    sess = make_call_session()
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMED, "test")
    await sess._handle_order_confirmed()
    first_count = len(stub_kitchen_dispatch["sends"])
    assert sess._order_confirmed_handled is True

    await sess._handle_order_confirmed()
    # No additional dispatch.
    assert len(stub_kitchen_dispatch["sends"]) == first_count


async def test_order_confirmed_blocked_when_restaurant_closed(
    make_call_session, stub_kitchen_dispatch
):
    """If is_open is False the handler must short-circuit and not dispatch."""
    sess = make_call_session()
    sess.is_open = False
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMED, "test")
    await sess._handle_order_confirmed()
    assert stub_kitchen_dispatch["sends"] == []


# ---------------------------------------------------------------------------
# Hangup scheduling — guards and idempotency
# ---------------------------------------------------------------------------


async def test_schedule_hangup_guard_blocks_second_call(make_call_session, monkeypatch):
    sess = make_call_session()
    # Replace HANGUP_DELAY_SECS with 0 so the test runs instantly.
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    await sess._schedule_hangup(reason="first")
    first_cancel = sess._pipeline_task.cancel.await_count

    # Second call WITHOUT _skip_guard must not re-cancel.
    await sess._schedule_hangup(reason="second")
    assert sess._pipeline_task.cancel.await_count == first_cancel
    assert sess._hangup_scheduled is True


async def test_schedule_hangup_with_skip_guard_runs_even_when_already_scheduled(
    make_call_session, monkeypatch
):
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._hangup_scheduled = True  # already set, _skip_guard required

    await sess._schedule_hangup(reason="forced", _skip_guard=True)
    assert sess._pipeline_task.cancel.await_count == 1


async def test_schedule_hangup_escalation_attempts_transfer(
    make_call_session, monkeypatch
):
    """On successful escalation transfer, the pipeline MUST NOT be cancelled
    and the Telnyx leg MUST NOT be hung up — both would abort the in-progress
    outbound dial before Telnyx can ring the destination. Instead the session
    enters _transfer_in_progress state, calls Telnyx streaming_stop, and
    starts a fallback watchdog task. Pipeline release happens later via the
    call.bridged webhook handler (see _handle_transfer_bridged)."""
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    transfer_mock = AsyncMock(return_value=True)
    sess._transfer_call = transfer_mock
    stop_streaming = AsyncMock(return_value=True)
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.stop_streaming", stop_streaming)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._schedule_hangup(reason="escalation")

    transfer_mock.assert_awaited_once_with("+15555550199")
    # Pipeline stays alive — bridge needs the A-leg as its anchor.
    assert sess._pipeline_task.cancel.await_count == 0
    # Telnyx leg stays alive too.
    hang_up.assert_not_awaited()
    # Streaming is stopped so Gemini Live goes idle (no input audio = no billing).
    stop_streaming.assert_awaited_once_with(sess.call_sid)
    # Transfer-in-progress flag and fallback watchdog are set.
    assert sess._transfer_in_progress is True
    assert sess._transfer_fallback_task is not None
    # Cleanup: cancel the fallback task to avoid lingering background work.
    sess._transfer_fallback_task.cancel()


async def test_schedule_hangup_escalation_falls_through_when_transfer_fails(
    make_call_session, monkeypatch
):
    """When _transfer_call returns False (no phone or Telnyx errored), the
    escalation branch falls through to terminate the call — explicit
    hang_up_call BEFORE pipeline cancel, since auto_hang_up=False on the
    serializer no longer hangs up implicitly."""
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=False)
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._schedule_hangup(reason="escalation")

    # Explicit Telnyx hangup BEFORE pipeline cancel.
    hang_up.assert_awaited_once_with(sess.call_sid)
    assert sess._pipeline_task.cancel.await_count == 1


# ---------------------------------------------------------------------------
# Appointment-confirmed flow (non-restaurant)
# ---------------------------------------------------------------------------


async def test_appointment_confirmed_dispatches_booking(
    make_call_session, stub_appointment_dispatch, monkeypatch
):
    sess = make_call_session(
        business_type="salon",
        services=[{"name": "Standard Haircut", "price_cents": 4500}],
    )
    stub_appointment_dispatch["extracted"] = {
        "customer_name": "Jane",
        "service_name": "Standard Haircut",
        "date": "2026-05-30",
        "time": "15:00",
    }
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)

    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete

    await sess._handle_appointment_confirmed()

    assert sess._booking_dispatched is True
    assert sess._appointment_total == 4500
    on_complete.assert_awaited_once()


async def test_appointment_confirmed_no_booking_extracted(
    make_call_session, stub_appointment_dispatch, monkeypatch
):
    sess = make_call_session(business_type="salon", services=[{"name": "Haircut"}])
    stub_appointment_dispatch["extracted"] = None
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    await sess._handle_appointment_confirmed()
    # When no booking is extracted, _booking_dispatched stays False so a later
    # extraction attempt can still succeed. The hangup IS scheduled regardless
    # (the AI already said the confirmation phrase).
    assert sess._booking_dispatched is False
    assert sess._hangup_scheduled is True
    assert stub_appointment_dispatch["dispatch_calls"] == []


# ---------------------------------------------------------------------------
# build_final_call_record
# ---------------------------------------------------------------------------


def test_build_final_call_record_returns_canonical_shape(make_call_session):
    sess = make_call_session()
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=2,
        )
    )
    sess.order.transition(OrderState.COMPLETED, "test")
    record = sess.build_final_call_record()
    assert record["call_sid"] == "test_call_001"
    assert record["restaurant_id"] == "rest_voice_test"
    assert record["status"] == "COMPLETED"
    assert record["contained_by_ai"] is True
    assert record["escalated_to_human"] is False
    assert record["order"]["total"] == 1499 * 2
    assert record["order_total"] == 1499 * 2
    assert "cost_voice_cents" in record
    assert "cost_total_cents" in record
    assert record["sms_count"] == 0


def test_build_final_call_record_marks_escalated(make_call_session):
    sess = make_call_session()
    sess._escalated = True
    record = sess.build_final_call_record()
    assert record["status"] == "ESCALATED"
    assert record["contained_by_ai"] is False
    assert record["escalated_to_human"] is True


def test_build_final_call_record_appointment_total_for_salon(make_call_session):
    """For salon business, order_total comes from _appointment_total, not order.total."""
    sess = make_call_session(business_type="salon")
    sess._appointment_total = 9000
    sess._booking_dispatched = True
    record = sess.build_final_call_record()
    assert record["order_total"] == 9000
    assert record["business_type"] == "salon"
    assert record["booking_dispatched"] is True


# ---------------------------------------------------------------------------
# Order signal dedup — repeat AI message with same text is ignored
# ---------------------------------------------------------------------------


async def test_repeated_ai_text_does_not_double_fire_signals(
    make_call_session, stub_kitchen_dispatch
):
    sess = make_call_session()
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMING, "ready")

    # First fire should trigger dispatch (eventually).
    sess.add_transcript_entry("ai", "Your order is confirmed.")
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    first_dispatch_count = len(stub_kitchen_dispatch["sends"])
    # Repeat same text — guard via _last_signal_text should skip processing.
    sess.add_transcript_entry("ai", "Your order is confirmed.")
    await asyncio.sleep(0)
    assert len(stub_kitchen_dispatch["sends"]) == first_dispatch_count


# ---------------------------------------------------------------------------
# Escalation signal path through add_transcript_entry.
# ---------------------------------------------------------------------------


async def test_escalate_to_human_signal_marks_session_and_schedules_hangup(
    make_call_session, monkeypatch
):
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=False)

    sess.add_transcript_entry("ai", "ESCALATE_TO_HUMAN")
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert sess._escalated is True
    assert sess.order.state == OrderState.ESCALATED


async def test_order_confirmed_with_deferred_escalation_then_transfers(
    make_call_session, stub_kitchen_dispatch, monkeypatch
):
    """When _escalation_deferred is set (customer asked for human mid-order),
    ORDER_CONFIRMED dispatches the order AND then escalates to a human via
    the inner _order_then_escalate coroutine."""
    import asyncio

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=True)

    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMING, "ready")
    sess._escalation_deferred = True

    # Need to make asyncio.sleep(3.0) inside _order_then_escalate run instantly.
    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr("call_pipeline.asyncio.sleep", fast_sleep)

    sess.add_transcript_entry("ai", "Your order is confirmed.")
    # Let both tasks (handle_order_confirmed and the deferred escalation) run.
    for _ in range(10):
        await asyncio.sleep(0)
    assert sess._escalated is True


# ---------------------------------------------------------------------------
# _handle_order_confirmed exception path — on_call_complete raises.
# ---------------------------------------------------------------------------


async def test_handle_order_confirmed_swallows_on_call_complete_exception(
    make_call_session, stub_kitchen_dispatch, monkeypatch
):
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMED, "test")

    sess._on_call_complete = AsyncMock(
        side_effect=RuntimeError("simulated post-call crash")
    )
    # Must not raise — exception is logged.
    await sess._handle_order_confirmed()
    sess._on_call_complete.assert_awaited_once()


async def test_handle_order_confirmed_cancels_call_timer_task(
    make_call_session, stub_kitchen_dispatch, monkeypatch
):
    import asyncio

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMED, "test")

    async def never():
        await asyncio.sleep(60)

    sess._call_timer_task = asyncio.create_task(never())

    await sess._handle_order_confirmed()
    # Cancellation cleared the reference.
    assert sess._call_timer_task is None


# ---------------------------------------------------------------------------
# Reservation_confirmed handler (currently uncovered).
# ---------------------------------------------------------------------------


async def test_handle_reservation_confirmed_extracts_and_dispatches(
    make_call_session, monkeypatch
):
    import asyncio
    import sys
    import types

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)

    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr("call_pipeline.asyncio.sleep", fast_sleep)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    # Stub the reservation_service helpers via a fake module insertion.
    extract_calls: list = []
    dispatch_calls: list = []

    async def fake_extract(transcript, menu_index=None):
        extract_calls.append({"transcript": transcript})
        return {
            "customer_name": "Jane",
            "party_size": 4,
            "date": "2026-05-30",
            "time": "19:00",
        }

    async def fake_dispatch(reservation_data, restaurant, config, db=None):
        dispatch_calls.append(reservation_data)
        return {"success": True, "reservation_id": "rsv_123"}

    fake_module = types.ModuleType("reservation_service")
    fake_module.extract_reservation_from_transcript = fake_extract
    fake_module.dispatch_reservation = fake_dispatch
    monkeypatch.setitem(sys.modules, "reservation_service", fake_module)

    on_complete = AsyncMock()
    sess._on_call_complete = on_complete

    await sess._handle_reservation_confirmed()
    assert len(extract_calls) == 1
    assert len(dispatch_calls) == 1
    assert dispatch_calls[0]["customer_phone"] == "+15555550199"
    assert dispatch_calls[0]["call_id"] == "test_call_001"
    on_complete.assert_awaited_once()


async def test_handle_reservation_confirmed_no_extraction_skips_dispatch(
    make_call_session, monkeypatch
):
    import asyncio
    import sys
    import types

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)

    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr("call_pipeline.asyncio.sleep", fast_sleep)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    async def fake_extract(transcript, menu_index=None):
        return None

    dispatch_calls: list = []

    async def fake_dispatch(**kw):
        dispatch_calls.append(kw)
        return {"success": True}

    fake_module = types.ModuleType("reservation_service")
    fake_module.extract_reservation_from_transcript = fake_extract
    fake_module.dispatch_reservation = fake_dispatch
    monkeypatch.setitem(sys.modules, "reservation_service", fake_module)

    await sess._handle_reservation_confirmed()
    assert dispatch_calls == []


async def test_handle_reservation_confirmed_swallows_exceptions(
    make_call_session, monkeypatch
):
    """The whole reservation handler is wrapped in try/except — a crash in
    extraction must not block the on_call_complete + hangup chain."""
    import asyncio
    import sys
    import types

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)

    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr("call_pipeline.asyncio.sleep", fast_sleep)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    async def boom(transcript, menu_index=None):
        raise RuntimeError("simulated extraction crash")

    fake_module = types.ModuleType("reservation_service")
    fake_module.extract_reservation_from_transcript = boom
    fake_module.dispatch_reservation = AsyncMock()
    monkeypatch.setitem(sys.modules, "reservation_service", fake_module)

    on_complete = AsyncMock()
    sess._on_call_complete = on_complete

    # Must not raise — exception is logged.
    await sess._handle_reservation_confirmed()
    on_complete.assert_awaited_once()


# ---------------------------------------------------------------------------
# Appointment dispatch fuzzy-match revenue calculation.
# ---------------------------------------------------------------------------


async def test_dispatch_booking_fuzzy_matches_service_name(
    make_call_session, stub_appointment_dispatch, monkeypatch
):
    """If the booking says "haircut" and the service is "Standard Haircut",
    the fuzzy-match branch (substring with length>4) picks the right price."""
    sess = make_call_session(
        business_type="salon",
        services=[
            {"name": "Standard Haircut", "price_cents": 4500},
            {"name": "Color Treatment", "price_cents": 12000},
        ],
    )
    stub_appointment_dispatch["extracted"] = {
        "service_name": "haircut",
        "customer_name": "Jane",
    }
    await sess.dispatch_booking()
    assert sess._appointment_total == 4500


async def test_dispatch_booking_multiple_services_comma_separated(
    make_call_session, stub_appointment_dispatch
):
    """When ``service_name`` is comma-separated (multiple services booked),
    revenue sums across all of them."""
    sess = make_call_session(
        business_type="salon",
        services=[
            {"name": "Standard Haircut", "price_cents": 4500},
            {"name": "Color", "price_cents": 12000},
        ],
    )
    stub_appointment_dispatch["extracted"] = {
        "service_name": "Standard Haircut, Color",
        "customer_name": "Jane",
    }
    await sess.dispatch_booking()
    assert sess._appointment_total == 4500 + 12000


async def test_dispatch_booking_already_dispatched_returns_true(make_call_session):
    sess = make_call_session(business_type="salon", services=[])
    sess._booking_dispatched = True
    assert await sess.dispatch_booking() is True


async def test_dispatch_booking_returns_false_when_appointment_service_unavailable(
    make_call_session, monkeypatch
):
    sess = make_call_session(business_type="salon", services=[])
    monkeypatch.setattr("call_pipeline._APPOINTMENT_SERVICE_AVAILABLE", False)
    assert await sess.dispatch_booking() is False
