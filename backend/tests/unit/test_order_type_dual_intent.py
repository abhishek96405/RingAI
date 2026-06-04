"""
Regression tests for the dual-intent order_type relabel in call_pipeline.

When a caller both orders food (pickup/delivery) and books a table in the same
call, the extraction LLM may infer ``order_type == "reservation"``, which would
erase the food fulfillment type. ``dispatch_order_if_ready`` must rewrite the
label to a combined ``"<food>+reservation"`` form so the stored record reflects
both intents — while a plain food order keeps its plain ``"pickup"``/``"delivery"``
label.

The relabel lives in the ``if not self.order.items:`` extraction branch of
``dispatch_order_if_ready``, so each case seeds an empty-items CONFIRMED order and
drives dispatch through that path with extraction + kitchen dispatch stubbed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from gemini_service import LiveOrder, OrderState, OrderItem

import call_pipeline

pytestmark = pytest.mark.unit


def _make_session() -> call_pipeline.CallSession:
    """Build a CallSession with minimal args for the dispatch path."""
    return call_pipeline.CallSession(
        call_sid="test_call_dual",
        restaurant_id="rest_dual",
        caller_number="+15555550123",
        restaurant={},
        config={},
        menu_items=[],
    )


def _extracted_order(order_type: str) -> LiveOrder:
    """A one-item extracted order with the given (LLM-inferred) order_type."""
    order = LiveOrder(
        restaurant_id="rest_dual",
        call_sid="test_call_dual",
        caller_number="+15555550123",
        order_type=order_type,
        delivery_address="",
    )
    order.items.append(
        OrderItem(
            name="Margherita Pizza",
            menu_item_id="m_pizza",
            category="Pizza",
            unit_price=1499,
            quantity=1,
        )
    )
    return order


@pytest.mark.parametrize(
    "detected_order_type, extracted_order_type, expected",
    [
        # Dual-intent: customer ordered food for pickup AND booked a table.
        # Extraction inferred "reservation"; the food fulfillment must survive.
        ("reservation", "reservation", "pickup+reservation"),
        # Plain pickup order — no reservation, label stays plain.
        ("pickup", "pickup", "pickup"),
        # Dual-intent delivery: detected label already combined, extraction says
        # "delivery" — combined label must be preserved.
        ("delivery+reservation", "delivery", "delivery+reservation"),
    ],
)
async def test_dispatch_relabels_dual_intent_order_type(
    monkeypatch, detected_order_type, extracted_order_type, expected
):
    # Fresh session per case — _order_dispatched latches after the first call.
    sess = _make_session()
    sess._detected_order_type = detected_order_type
    sess.order.state = OrderState.CONFIRMED
    # Leave order.items empty so dispatch enters the extraction branch where the
    # relabel lives.
    assert not sess.order.items
    sess.transcript = [{"role": "customer", "text": "pizza for pickup and a table"}]

    monkeypatch.setattr(
        call_pipeline,
        "extract_order_from_transcript",
        AsyncMock(return_value=_extracted_order(extracted_order_type)),
        raising=True,
    )
    monkeypatch.setattr(
        call_pipeline,
        "send_order_to_kitchen",
        AsyncMock(
            return_value={"success": True, "order_id": "TEST", "method": "database"}
        ),
        raising=True,
    )

    result = await sess.dispatch_order_if_ready()

    assert result is True
    assert sess.order.order_type == expected
