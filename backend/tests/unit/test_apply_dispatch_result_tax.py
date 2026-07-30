"""_apply_dispatch_result copies POS tax/grand-total figures (tax_cents,
total_with_tax_cents) from a send_order_to_kitchen() result onto the session,
so build_final_call_record() and the confirmation SMS can read them later.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from call_pipeline import CallSession, OrderState

pytestmark = pytest.mark.unit

_MENU = [
    {"id": "i1", "name": "Samosa", "price": 500, "category": "Appetizers", "available": True},
]


def _session():
    return CallSession(
        call_sid="test-call",
        restaurant_id="rest-1",
        caller_number="+15555550123",
        restaurant={},
        config={},
        menu_items=_MENU,
    )


def test_apply_dispatch_result_copies_tax_fields_on_success():
    session = _session()
    assert session._order_tax_cents is None
    assert session._order_total_with_tax_cents is None

    session._apply_dispatch_result({
        "success": True,
        "order_id": "clv_1",
        "method": "clover",
        "tax_cents": 88,
        "total_with_tax_cents": 1088,
    })

    assert session._order_tax_cents == 88
    assert session._order_total_with_tax_cents == 1088
    assert session.order.state == OrderState.COMPLETED


def test_apply_dispatch_result_leaves_tax_fields_none_when_pos_omits_them():
    """Non-Clover/Square paths (e.g. database-only, kitchen webhook) don't
    return tax_cents/total_with_tax_cents — the session must stay None, not
    fabricate a value."""
    session = _session()

    session._apply_dispatch_result({
        "success": True,
        "order_id": "DTH-123",
        "method": "database",
    })

    assert session._order_tax_cents is None
    assert session._order_total_with_tax_cents is None
    assert session.order.state == OrderState.COMPLETED


async def test_apply_dispatch_result_leaves_tax_fields_none_on_failure(monkeypatch):
    """Failure path also fires a fire-and-forget operator alert
    (_notify_dispatch_failure) via _spawn_tracked — stub it out so the test
    doesn't need real Telnyx/WS collaborators, then let the loop settle."""
    import telnyx_service
    import websocket_notifications

    monkeypatch.setattr(telnyx_service, "send_sms",
                         lambda **kw: asyncio.sleep(0, result=SimpleNamespace(success=True)))
    monkeypatch.setattr(websocket_notifications, "notify_order_dispatch_failed",
                         lambda **kw: asyncio.sleep(0))

    session = _session()

    session._apply_dispatch_result({
        "success": False,
        "error": "Clover 500",
        "attempted_pos": "clover",
    })

    assert session._order_tax_cents is None
    assert session._order_total_with_tax_cents is None
    assert session.order.state == OrderState.DISPATCH_FAILED

    await asyncio.sleep(0)  # let the spawned notify task run to completion
