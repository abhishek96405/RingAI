"""
Unit tests for backend/websocket_notifications.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# build_notification
# ---------------------------------------------------------------------------

def test_build_notification_returns_complete_envelope():
    from websocket_notifications import build_notification
    out = build_notification(
        event_type="order",
        title="New Order",
        message="$25 — pickup",
        data={"order_id": "abc"},
        priority="high",
    )
    assert out["type"] == "notification"
    assert out["event"] == "order"
    assert out["title"] == "New Order"
    assert out["message"] == "$25 — pickup"
    assert out["data"] == {"order_id": "abc"}
    assert out["priority"] == "high"
    assert "timestamp" in out


def test_build_notification_defaults():
    from websocket_notifications import build_notification
    out = build_notification(event_type="x", title="t", message="m")
    assert out["data"] == {}
    assert out["priority"] == "normal"


# ---------------------------------------------------------------------------
# ConnectionManager: connect / disconnect / scoping
# ---------------------------------------------------------------------------

def _make_ws():
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


async def test_connect_assigns_to_restaurant_bucket():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    ws = _make_ws()

    await mgr.connect(ws, restaurant_id="rest_a")
    ws.accept.assert_awaited_once()

    assert "rest_a" in mgr.active_connections
    assert ws in mgr.active_connections["rest_a"]
    assert mgr.connection_restaurants[ws] == "rest_a"


async def test_connect_without_restaurant_is_global():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    ws = _make_ws()

    await mgr.connect(ws, restaurant_id=None)
    assert ws in mgr.global_connections


async def test_disconnect_removes_from_restaurant_bucket():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    ws = _make_ws()

    await mgr.connect(ws, restaurant_id="rest_a")
    await mgr.disconnect(ws)

    assert "rest_a" not in mgr.active_connections
    assert ws not in mgr.connection_restaurants


async def test_disconnect_removes_from_global():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    ws = _make_ws()

    await mgr.connect(ws, restaurant_id=None)
    await mgr.disconnect(ws)

    assert ws not in mgr.global_connections


async def test_disconnect_unknown_websocket_is_noop():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    await mgr.disconnect(_make_ws())  # must not raise


# ---------------------------------------------------------------------------
# Tenant isolation: send_to_restaurant only reaches that tenant
# ---------------------------------------------------------------------------

async def test_send_to_restaurant_isolates_tenants():
    """Tenant A's subscriber must not receive Tenant B's events."""
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    ws_a = _make_ws()
    ws_b = _make_ws()

    await mgr.connect(ws_a, restaurant_id="rest_a")
    await mgr.connect(ws_b, restaurant_id="rest_b")

    await mgr.send_to_restaurant("rest_a", {"event": "for_a", "x": 1})

    ws_a.send_text.assert_awaited_once()
    ws_b.send_text.assert_not_awaited()

    sent_payload = json.loads(ws_a.send_text.await_args.args[0])
    assert sent_payload["event"] == "for_a"


async def test_send_to_restaurant_with_no_subscribers_is_silent():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    await mgr.send_to_restaurant("nobody_subscribed", {"event": "x"})  # must not raise


async def test_send_to_restaurant_removes_dead_connections():
    """A connection raising on send_text is treated as dead and removed."""
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()

    ws = _make_ws()
    ws.send_text = AsyncMock(side_effect=RuntimeError("connection lost"))

    await mgr.connect(ws, restaurant_id="rest_a")
    await mgr.send_to_restaurant("rest_a", {"event": "x"})

    assert "rest_a" not in mgr.active_connections


async def test_send_global_only_reaches_global_subscribers():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()

    global_ws = _make_ws()
    tenant_ws = _make_ws()

    await mgr.connect(global_ws, restaurant_id=None)
    await mgr.connect(tenant_ws, restaurant_id="rest_a")

    await mgr.send_global({"event": "system"})

    global_ws.send_text.assert_awaited_once()
    tenant_ws.send_text.assert_not_awaited()


async def test_broadcast_reaches_all():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()

    global_ws = _make_ws()
    a_ws = _make_ws()
    b_ws = _make_ws()
    await mgr.connect(global_ws, restaurant_id=None)
    await mgr.connect(a_ws, restaurant_id="rest_a")
    await mgr.connect(b_ws, restaurant_id="rest_b")

    await mgr.broadcast({"event": "all"})

    global_ws.send_text.assert_awaited()
    a_ws.send_text.assert_awaited()
    b_ws.send_text.assert_awaited()


# ---------------------------------------------------------------------------
# get_connection_count
# ---------------------------------------------------------------------------

async def test_get_connection_count_per_restaurant():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    for _ in range(3):
        await mgr.connect(_make_ws(), restaurant_id="rest_a")
    await mgr.connect(_make_ws(), restaurant_id="rest_b")

    assert mgr.get_connection_count("rest_a") == 3
    assert mgr.get_connection_count("rest_b") == 1
    assert mgr.get_connection_count("rest_c") == 0


async def test_get_connection_count_global_total():
    from websocket_notifications import ConnectionManager
    mgr = ConnectionManager()
    await mgr.connect(_make_ws(), restaurant_id="rest_a")
    await mgr.connect(_make_ws(), restaurant_id=None)
    assert mgr.get_connection_count() == 2


# ---------------------------------------------------------------------------
# notify_* helpers — assert they dispatch via the manager singleton
# ---------------------------------------------------------------------------

async def test_notify_new_call_started(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)

    await wn.notify_new_call(
        restaurant_id="rest_a",
        call_sid="call_1",
        caller_number="+15551234567",
        status="started",
    )
    mock_send.assert_awaited_once()
    args, _ = mock_send.await_args
    assert args[0] == "rest_a"
    assert args[1]["title"] == "New Call"


async def test_notify_new_call_escalated_is_high_priority(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)

    await wn.notify_new_call(
        restaurant_id="rest_a",
        call_sid="call_1",
        caller_number="+15551234567",
        status="ESCALATED",
    )
    payload = mock_send.await_args.args[1]
    assert payload["priority"] == "high"
    assert "transferred" in payload["message"].lower()


async def test_notify_new_call_completed_includes_total(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)

    await wn.notify_new_call(
        restaurant_id="rest_a",
        call_sid="c1",
        caller_number="+15551234567",
        status="COMPLETED",
        order_total=2500,
    )
    payload = mock_send.await_args.args[1]
    assert "$25.00" in payload["message"]


async def test_notify_new_order(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)

    await wn.notify_new_order(
        restaurant_id="rest_a",
        order_id="order_12345678",
        total=3499,
        order_type="delivery",
        items_count=3,
    )
    payload = mock_send.await_args.args[1]
    assert payload["event"] == "order"
    assert "$34.99" in payload["message"]
    assert "delivery" in payload["message"]


async def test_notify_new_appointment(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)

    await wn.notify_new_appointment(
        restaurant_id="rest_a",
        appointment_id="appt_1",
        customer_name="Joe",
        service_name="Haircut",
        scheduled_date="2026-05-22",
        scheduled_time="2:00 PM",
    )
    payload = mock_send.await_args.args[1]
    assert payload["event"] == "appointment"
    assert "Joe" in payload["message"]
    assert "Haircut" in payload["message"]


async def test_notify_appointment_reminder_priority_is_low(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)

    await wn.notify_appointment_reminder(
        restaurant_id="rest_a",
        appointment_id="appt_1",
        customer_name="Joe",
        service_name="Haircut",
    )
    payload = mock_send.await_args.args[1]
    assert payload["priority"] == "low"


async def test_notify_system_with_restaurant_uses_send_to_restaurant(monkeypatch):
    import websocket_notifications as wn
    mock_send = AsyncMock()
    mock_broadcast = AsyncMock()
    monkeypatch.setattr(wn.manager, "send_to_restaurant", mock_send)
    monkeypatch.setattr(wn.manager, "broadcast", mock_broadcast)

    await wn.notify_system(restaurant_id="rest_a", title="t", message="m")
    mock_send.assert_awaited_once()
    mock_broadcast.assert_not_awaited()


async def test_notify_system_without_restaurant_broadcasts(monkeypatch):
    import websocket_notifications as wn
    mock_broadcast = AsyncMock()
    monkeypatch.setattr(wn.manager, "broadcast", mock_broadcast)

    await wn.notify_system(restaurant_id=None, title="t", message="m")
    mock_broadcast.assert_awaited_once()
