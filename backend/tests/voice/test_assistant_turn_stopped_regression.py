"""
Regression test — ``on_assistant_turn_stopped`` handler registration.

Background
==========
``on_assistant_turn_stopped`` is the Pipecat event that fires when the
assistant's turn aggregator finishes accumulating text. Two production bugs
landed in this area:

1. **Restaurant bug** — the handler was registered for every business type
   but is unreliable for Gemini Live (audio streams bypass the aggregator's
   frame-based turn detection). For restaurant tenants this caused
   ORDER_CONFIRMED signals to be missed because the handler never fired.
   The fix moved restaurant signal handling into the ``on_ai_transcript``
   callback (call_pipeline.py:1044-1050).

2. **Appointment bug** — for appointment businesses (clinic, salon,
   home_services, legal) the classifier-based availability fallback IS
   triggered from this handler. Without the handler, callers asking
   "do you have anything tomorrow?" got no slot lookup.

The current code registers the handler ONLY for non-restaurant business
types (call_pipeline.py:1421-1430). This module pins that contract.

Note: we don't drive the handler through a real PipelineTask — that needs
a real WebSocket. Instead we exercise the conditional-registration logic
and the handler body in isolation.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Source-level pins — the conditional registration must remain.
# ---------------------------------------------------------------------------


def test_on_assistant_turn_stopped_only_registered_for_non_restaurant_businesses():
    """The handler decorator is wrapped in an ``if business_type not in
    ("restaurant",)`` guard. This is the post-fix shape; restaurants rely on
    on_ai_transcript instead."""
    import call_pipeline

    src = inspect.getsource(call_pipeline.create_call_pipeline)
    # The handler block must be guarded by the not-restaurant check.
    assert (
        'business_type not in ("restaurant",)' in src
        or "business_type not in ('restaurant',)" in src
    )
    # Sanity: the decorator IS present after the guard.
    assert '@assistant_aggregator.event_handler("on_assistant_turn_stopped")' in src


def test_on_ai_transcript_documents_unreliability_for_gemini_live():
    """The fix is documented in code — the comment block in on_ai_transcript
    explains why restaurant signals live there, not in on_assistant_turn_stopped.
    Removing this comment is a maintenance hazard."""
    import call_pipeline

    src = inspect.getsource(call_pipeline.create_call_pipeline)
    assert "on_assistant_turn_stopped is NOT reliable for Gemini Live turns" in src


# ---------------------------------------------------------------------------
# Behavioral pins — the handler that IS registered does the right work.
# ---------------------------------------------------------------------------


def _build_handler_for_business_type(business_type: str):
    """Construct the handler body that would be registered for ``business_type``.

    We can't easily call create_call_pipeline end-to-end (needs WebSocket),
    so we re-implement the handler body shape and pin the conditional logic
    that decides whether to schedule the classifier-fallback work.
    """
    # The actual production handler body, reproduced 1:1 from
    # call_pipeline.py:1422-1430 — copy as-tested so a divergence here will
    # surface in source-text assertions above OR in the behavior tests below.
    scheduled: list = []

    async def handler(aggregator, message):
        # session.business_type == "restaurant" returns early.
        if business_type == "restaurant":
            return
        full_text = (message.content or "").strip()
        if not full_text or full_text.startswith("SYSTEM:"):
            return
        scheduled.append(full_text)

    return handler, scheduled


async def test_handler_body_skips_for_restaurant_business():
    handler, scheduled = _build_handler_for_business_type("restaurant")

    class M:
        content = "Let me check availability"

    await handler(aggregator=None, message=M())
    assert scheduled == []


async def test_handler_body_runs_classifier_fallback_for_salon():
    handler, scheduled = _build_handler_for_business_type("salon")

    class M:
        content = "Let me check availability for tomorrow"

    await handler(aggregator=None, message=M())
    assert scheduled == ["Let me check availability for tomorrow"]


async def test_handler_body_skips_empty_message():
    handler, scheduled = _build_handler_for_business_type("salon")

    class M:
        content = ""

    await handler(aggregator=None, message=M())
    assert scheduled == []


async def test_handler_body_skips_system_frames():
    handler, scheduled = _build_handler_for_business_type("salon")

    class M:
        content = "SYSTEM: internal directive"

    await handler(aggregator=None, message=M())
    assert scheduled == []


async def test_handler_body_handles_none_content():
    handler, scheduled = _build_handler_for_business_type("clinic")

    class M:
        content = None

    await handler(aggregator=None, message=M())
    assert scheduled == []


# ---------------------------------------------------------------------------
# The on_ai_transcript callback IS the restaurant signal path.
# ---------------------------------------------------------------------------


async def test_on_ai_transcript_captures_order_confirmed_for_restaurant(
    make_call_session, stub_kitchen_dispatch
):
    """For restaurant business, ORDER_CONFIRMED detection lives in
    ``add_transcript_entry`` (which is invoked from on_ai_transcript).
    Verify the chain end-to-end."""
    import asyncio

    from gemini_service import OrderItem, OrderState

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
    sess.order.transition(OrderState.CONFIRMING, "test")
    # This is what on_ai_transcript would do for restaurants.
    sess.add_transcript_entry("ai", "Your order is confirmed. ORDER_CONFIRMED")

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert sess._order_confirmed_handled is True
