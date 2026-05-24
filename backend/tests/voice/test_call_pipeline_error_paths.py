"""
Tests for error and resilience paths in :func:`call_pipeline.create_call_pipeline`
and ``CallSession`` dispatch.

Pin behavior for:
- Missing API keys (early return None)
- Pipecat unavailable (early return None)
- Missing TelnyxFrameSerializer (early return None with error log)
- Kitchen webhook failure → DB fallback
- Extraction returning None after retries → no dispatch
- Delivery validation failure → SMS rejection + abort
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Early-exit guards in create_call_pipeline.
# ---------------------------------------------------------------------------


async def test_no_google_api_key_returns_none(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    monkeypatch.setenv("TELNYX_API_KEY", "tnx_test")

    import call_pipeline

    result = await call_pipeline.create_call_pipeline(
        websocket=None,
        system_prompt="hi",
        restaurant_id="r1",
        call_sid="c1",
    )
    assert result is None


async def test_no_telnyx_api_key_returns_none(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.delenv("TELNYX_API_KEY", raising=False)

    import call_pipeline

    result = await call_pipeline.create_call_pipeline(
        websocket=None,
        system_prompt="hi",
        restaurant_id="r1",
        call_sid="c1",
    )
    assert result is None


async def test_pipecat_unavailable_short_circuits(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.setenv("TELNYX_API_KEY", "tnx_test")
    import call_pipeline

    monkeypatch.setattr(call_pipeline, "_PIPECAT_AVAILABLE", False)
    result = await call_pipeline.create_call_pipeline(
        websocket=None,
        system_prompt="hi",
        restaurant_id="r1",
        call_sid="c1",
    )
    assert result is None


async def test_telnyx_serializer_missing_short_circuits(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.setenv("TELNYX_API_KEY", "tnx_test")
    import call_pipeline

    monkeypatch.setattr(call_pipeline, "_TELNYX_SERIALIZER_AVAILABLE", False)
    result = await call_pipeline.create_call_pipeline(
        websocket=None,
        system_prompt="hi",
        restaurant_id="r1",
        call_sid="c1",
    )
    assert result is None


# ---------------------------------------------------------------------------
# Order extraction failure modes.
# ---------------------------------------------------------------------------


async def test_dispatch_with_no_items_and_extraction_returns_none_captures_bug(
    make_call_session, stub_order_extraction, monkeypatch
):
    """Captures bug: after retries fail, the ``for/else`` branch returns False
    WITHOUT resetting ``_order_dispatched`` to False (call_pipeline.py:569-573).
    This permanently blocks any future retry attempt within the same call, even
    if a later transcript update would have allowed extraction to succeed. See
    FINDINGS.md 2026-05-23.
    """
    from gemini_service import OrderState

    sess = make_call_session()
    sess.order.transition(OrderState.CONFIRMED, "test")
    stub_order_extraction["return_value"] = None
    # Replace asyncio.sleep so retries don't actually wait.
    monkeypatch.setattr("call_pipeline.asyncio.sleep", AsyncMock())

    result = await sess.dispatch_order_if_ready(max_retries=2)
    assert result is False
    # Current (buggy) behavior: flag stays True, blocking future retries.
    assert sess._order_dispatched is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        "When extraction fails after max_retries, _order_dispatched should be "
        "reset to False so a later attempt can succeed. See FINDINGS.md 2026-05-23."
    ),
)
async def test_dispatch_failure_should_allow_future_retry_expected(
    make_call_session, stub_order_extraction, monkeypatch
):
    from gemini_service import OrderState

    sess = make_call_session()
    sess.order.transition(OrderState.CONFIRMED, "test")
    stub_order_extraction["return_value"] = None
    monkeypatch.setattr("call_pipeline.asyncio.sleep", AsyncMock())

    await sess.dispatch_order_if_ready(max_retries=2)
    assert sess._order_dispatched is False


async def test_dispatch_retries_on_extraction_failure(
    make_call_session, stub_order_extraction, monkeypatch
):
    """Extraction is retried up to ``max_retries`` times before giving up."""
    from gemini_service import OrderState

    sess = make_call_session()
    sess.order.transition(OrderState.CONFIRMED, "test")
    stub_order_extraction["return_value"] = None
    # Replace asyncio.sleep so retries don't actually wait.
    monkeypatch.setattr("call_pipeline.asyncio.sleep", AsyncMock())

    result = await sess.dispatch_order_if_ready(max_retries=3)
    assert result is False
    # Called once per attempt.
    assert len(stub_order_extraction["calls"]) == 3


async def test_kitchen_dispatch_failure_still_transitions_state(
    make_call_session, stub_order_extraction, monkeypatch
):
    """If send_order_to_kitchen returns success=False, the order still transitions
    to COMPLETED (with a 'dispatch failed' reason) so the call doesn't hang."""
    from gemini_service import LiveOrder, OrderItem, OrderState

    sess = make_call_session()
    extracted = LiveOrder(
        restaurant_id="r", call_sid="c", caller_number="+1", state=OrderState.CONFIRMED
    )
    extracted.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    stub_order_extraction["return_value"] = extracted
    sess.order.transition(OrderState.CONFIRMED, "test")

    monkeypatch.setattr(
        "call_pipeline.send_order_to_kitchen",
        AsyncMock(
            return_value={"success": False, "order_id": "", "method": "kitchen_webhook"}
        ),
    )
    result = await sess.dispatch_order_if_ready()
    assert result is True
    assert sess.order.state == OrderState.COMPLETED


# ---------------------------------------------------------------------------
# Delivery validation failure path.
# ---------------------------------------------------------------------------


async def test_delivery_outside_radius_sends_rejection_sms(
    make_call_session, stub_order_extraction, stub_send_sms, monkeypatch
):
    from gemini_service import LiveOrder, OrderItem, OrderState

    sess = make_call_session()
    extracted = LiveOrder(
        restaurant_id="r",
        call_sid="c",
        caller_number="+15555550199",
        state=OrderState.CONFIRMED,
        order_type="delivery",
        delivery_address="9999 Far Away St",
    )
    extracted.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    stub_order_extraction["return_value"] = extracted
    sess.order.transition(OrderState.CONFIRMED, "test")

    # Mock the distance validator to return OUT-OF-RADIUS.
    fake_validation = AsyncMock(
        return_value={"within_radius": False, "distance_miles": 12.5}
    )
    monkeypatch.setattr("delivery_utils.validate_delivery_distance", fake_validation)
    monkeypatch.setattr("call_pipeline.send_order_to_kitchen", AsyncMock())

    result = await sess.dispatch_order_if_ready()
    assert result is False
    # The rejection SMS was sent via telnyx_service.
    assert len(stub_send_sms) == 1
    assert stub_send_sms[0]["to"] == "+15555550199"


async def test_delivery_validation_exception_proceeds_with_dispatch(
    make_call_session, stub_order_extraction, monkeypatch
):
    """If the distance validator raises, we log and dispatch anyway — don't
    block legitimate orders on a validator outage."""
    from gemini_service import LiveOrder, OrderItem, OrderState

    sess = make_call_session()
    extracted = LiveOrder(
        restaurant_id="r",
        call_sid="c",
        caller_number="+15555550199",
        state=OrderState.CONFIRMED,
        order_type="delivery",
        delivery_address="123 Some St",
    )
    extracted.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    stub_order_extraction["return_value"] = extracted
    sess.order.transition(OrderState.CONFIRMED, "test")

    monkeypatch.setattr(
        "delivery_utils.validate_delivery_distance",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    kitchen = AsyncMock(
        return_value={"success": True, "order_id": "k1", "method": "database"}
    )
    monkeypatch.setattr("call_pipeline.send_order_to_kitchen", kitchen)

    result = await sess.dispatch_order_if_ready()
    assert result is True
    kitchen.assert_awaited_once()
