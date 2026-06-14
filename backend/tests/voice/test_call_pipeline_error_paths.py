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


async def test_kitchen_dispatch_failure_transitions_to_dispatch_failed(
    make_call_session, stub_order_extraction, stub_send_sms, monkeypatch
):
    """A configured-POS dispatch failure must NOT be collapsed into a COMPLETED
    DB success (A7-1). The order transitions to DISPATCH_FAILED, records the
    reason, and a fire-and-forget operator alert is raised. ``dispatch_order_if_ready``
    still returns True (the dispatch attempt concluded)."""
    import asyncio
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
            return_value={
                "success": False, "order_id": "DTH-X", "method": "square",
                "attempted_pos": "square", "fallback_saved": True,
                "error": "Square 401: unauthorized",
            }
        ),
    )
    result = await sess.dispatch_order_if_ready()
    assert result is True
    assert sess.order.state == OrderState.DISPATCH_FAILED
    assert sess.order.dispatch_failure_reason == "Square 401: unauthorized"
    # _order_dispatched stays True — the alert, not a retry, is the recovery path.
    assert sess._order_dispatched is True

    # The fire-and-forget operator alert runs as a background task.
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(stub_send_sms) == 1
    assert stub_send_sms[0]["idempotency_key"] == f"dispatch_fail:{sess.call_sid}"
    assert stub_send_sms[0]["to"] == "+15555550199"  # escalation_phone_number


async def test_dispatch_failure_alert_skips_sms_when_no_operator_number(
    make_call_session, stub_send_sms
):
    """SMS resolution skips cleanly (logs, no raise, no send) when none of
    dispatch_alert_phone / escalation_phone_number / owner_phone is configured."""
    from gemini_service import OrderState

    # Config + restaurant with NO operator number anywhere.
    sess = make_call_session(config={"business_type": "restaurant"},
                             restaurant={"id": "r", "name": "X"})
    await sess._notify_dispatch_failure(
        {"attempted_pos": "square", "error": "Square 500"}
    )
    assert len(stub_send_sms) == 0


async def test_dispatch_success_path_unchanged(
    make_call_session, stub_order_extraction, monkeypatch
):
    """Byte-identical success behavior: COMPLETED + kitchen_order_id set."""
    from gemini_service import LiveOrder, OrderItem, OrderState

    sess = make_call_session()
    extracted = LiveOrder(
        restaurant_id="r", call_sid="c", caller_number="+1", state=OrderState.CONFIRMED
    )
    extracted.items.append(
        OrderItem(name="Pizza", menu_item_id="m_pizza", category="P",
                  unit_price=1499, quantity=1)
    )
    stub_order_extraction["return_value"] = extracted
    sess.order.transition(OrderState.CONFIRMED, "test")

    monkeypatch.setattr(
        "call_pipeline.send_order_to_kitchen",
        AsyncMock(return_value={
            "success": True, "order_id": "sq_1", "method": "square",
            "attempted_pos": "square", "fallback_saved": False,
        }),
    )
    result = await sess.dispatch_order_if_ready()
    assert result is True
    assert sess.order.state == OrderState.COMPLETED
    assert sess.order.kitchen_order_id == "sq_1"


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

    # Mock the validator to return a CONCLUSIVE out-of-radius result
    # (allowed=False, verified=True) — accurate customer rejection SMS.
    fake_validation = AsyncMock(
        return_value={
            "allowed": False,
            "verified": True,
            "distance_miles": 12.5,
            "reason": "outside_radius",
        }
    )
    monkeypatch.setattr("delivery_utils.validate_delivery_distance", fake_validation)
    monkeypatch.setattr("call_pipeline.send_order_to_kitchen", AsyncMock())

    result = await sess.dispatch_order_if_ready()
    assert result is False
    # The rejection SMS was sent via telnyx_service.
    assert len(stub_send_sms) == 1
    assert stub_send_sms[0]["to"] == "+15555550199"


async def test_delivery_validation_exception_fails_closed(
    make_call_session, stub_order_extraction, monkeypatch
):
    """B5-26/C21-1: if the validator itself raises, we FAIL CLOSED — hold the
    order for operator review instead of dispatching a delivery we couldn't
    confirm. The kitchen must NOT be called."""
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
    notify = AsyncMock()
    monkeypatch.setattr(sess, "_notify_delivery_unverifiable", notify)
    kitchen = AsyncMock(
        return_value={"success": True, "order_id": "k1", "method": "database"}
    )
    monkeypatch.setattr("call_pipeline.send_order_to_kitchen", kitchen)

    result = await sess.dispatch_order_if_ready()
    assert result is False
    kitchen.assert_not_awaited()
    # K5/C9-1: an unverifiable delivery is held as DISPATCH_FAILED so it surfaces
    # on the OrdersPage failure banner, not silently left CONFIRMED.
    assert sess.order.state == OrderState.DISPATCH_FAILED
    assert sess.order.dispatch_failure_reason
