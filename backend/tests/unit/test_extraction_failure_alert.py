"""_notify_extraction_failure pings the operator when a confirmed order can't be
auto-recovered (extraction failed AND cart-rebuild couldn't produce a dispatchable
order, e.g. a delivery order with no address in the cart)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from call_pipeline import CallSession

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


async def test_extraction_failure_alert_sends_operator_sms(monkeypatch):
    import telnyx_service
    import websocket_notifications

    sent = {}

    async def _fake_send_sms(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(success=True)

    async def _fake_ws(**kwargs):
        return None

    monkeypatch.setattr(telnyx_service, "send_sms", _fake_send_sms)
    monkeypatch.setattr(websocket_notifications, "notify_order_dispatch_failed", _fake_ws)

    session = _session()
    session.config = {"escalation_phone_number": "+15555559999"}

    await session._notify_extraction_failure()

    assert sent.get("to") == "+15555559999"
    assert sent.get("idempotency_key") == "extract_fail:test-call"
    assert sent.get("metadata", {}).get("purpose") == "extraction_failure_alert"


async def test_extraction_failure_alert_skips_when_no_operator_phone(monkeypatch):
    import telnyx_service
    import websocket_notifications

    called = {"sms": False}

    async def _fake_send_sms(**kwargs):
        called["sms"] = True
        return SimpleNamespace(success=True)

    async def _fake_ws(**kwargs):
        return None

    monkeypatch.setattr(telnyx_service, "send_sms", _fake_send_sms)
    monkeypatch.setattr(websocket_notifications, "notify_order_dispatch_failed", _fake_ws)

    session = _session()
    session.config = {}
    session.restaurant = {}

    # No alert phone configured anywhere → SMS skipped, must not raise.
    await session._notify_extraction_failure()
    assert called["sms"] is False
