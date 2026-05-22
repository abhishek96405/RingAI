"""
Unit tests for backend/payment_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 90% (money-critical).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _sms_success():
    return SimpleNamespace(success=True, message_id="msg_1", error_code=None, error_message=None)


def _sms_failure():
    return SimpleNamespace(success=False, message_id=None, error_code="X", error_message="boom")


# ---------------------------------------------------------------------------
# create_payment_link — happy path & failure modes
# ---------------------------------------------------------------------------

async def test_create_payment_link_returns_url_when_stripe_configured(monkeypatch):
    from payment_service import create_payment_link
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    fake_session = MagicMock(url="https://checkout.stripe.com/c/abc")
    create_mock = MagicMock(return_value=fake_session)

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", create_mock)

    url = await create_payment_link(
        order_total=2500,
        order_id="order_1",
        restaurant_name="Tasty Bites",
        customer_name="Joe",
        items_description="Pizza",
        restaurant_id="rest_a",
        convenience_fee_pct=1.0,
    )

    assert url == "https://checkout.stripe.com/c/abc"
    create_mock.assert_called_once()
    kwargs = create_mock.call_args.kwargs

    # Mode and currency
    assert kwargs["mode"] == "payment"
    line_items = kwargs["line_items"]
    assert len(line_items) == 2

    # First item: the order itself
    assert line_items[0]["price_data"]["unit_amount"] == 2500
    assert line_items[0]["price_data"]["currency"] == "usd"
    assert "Tasty Bites" in line_items[0]["price_data"]["product_data"]["name"]

    # Second item: convenience fee = 1% of 2500 = 25 cents
    assert line_items[1]["price_data"]["unit_amount"] == 25
    assert line_items[1]["price_data"]["product_data"]["name"] == "Convenience Fee"

    # Metadata
    assert kwargs["metadata"]["order_id"] == "order_1"
    assert kwargs["metadata"]["restaurant_id"] == "rest_a"


async def test_create_payment_link_minimum_convenience_fee_is_one_cent(monkeypatch):
    """Even tiny orders must get at least a 1¢ convenience fee."""
    from payment_service import create_payment_link
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    fake_session = MagicMock(url="https://x")
    create_mock = MagicMock(return_value=fake_session)
    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", create_mock)

    await create_payment_link(
        order_total=5,  # 5 cents — 1% would round to 0
        order_id="o", restaurant_name="r",
        convenience_fee_pct=1.0,
    )
    fee = create_mock.call_args.kwargs["line_items"][1]["price_data"]["unit_amount"]
    assert fee >= 1


async def test_create_payment_link_returns_none_when_stripe_unconfigured(monkeypatch):
    from payment_service import create_payment_link
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    url = await create_payment_link(
        order_total=2500,
        order_id="o",
        restaurant_name="r",
    )
    assert url is None


async def test_create_payment_link_returns_none_on_stripe_exception(monkeypatch):
    from payment_service import create_payment_link
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create",
                        MagicMock(side_effect=Exception("stripe error")))

    url = await create_payment_link(
        order_total=2500, order_id="o", restaurant_name="r",
    )
    assert url is None


async def test_create_payment_link_truncates_long_descriptions(monkeypatch):
    from payment_service import create_payment_link
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    fake_session = MagicMock(url="https://x")
    create_mock = MagicMock(return_value=fake_session)
    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", create_mock)

    await create_payment_link(
        order_total=1000,
        order_id="o",
        restaurant_name="r",
        items_description="x" * 1000,
    )
    desc = create_mock.call_args.kwargs["line_items"][0]["price_data"]["product_data"]["description"]
    assert len(desc) <= 500


# ---------------------------------------------------------------------------
# send_payment_sms
# ---------------------------------------------------------------------------

async def test_send_payment_sms_with_payment_link(monkeypatch):
    from payment_service import send_payment_sms

    monkeypatch.setattr("payment_service.create_payment_link",
                        AsyncMock(return_value="https://checkout.stripe.com/c/abc"))
    monkeypatch.setattr("telnyx_service.send_sms",
                        AsyncMock(return_value=_sms_success()))

    result = await send_payment_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order_total=2500,
        order_id="order_abcdef12",
        items_summary="1x Pizza",
        eta_minutes=20,
    )

    assert result["success"] is True
    assert result["sms_sent"] is True
    assert result["payment_link_sent"] is True
    assert result["payment_link"] == "https://checkout.stripe.com/c/abc"


async def test_send_payment_sms_without_payment_link_still_sends(monkeypatch):
    """If Stripe is unavailable, SMS should still go out without a link."""
    from payment_service import send_payment_sms

    monkeypatch.setattr("payment_service.create_payment_link", AsyncMock(return_value=None))
    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    result = await send_payment_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order_total=2500,
        order_id="order_abcdef12",
    )
    assert result["success"] is True
    assert result["sms_sent"] is True
    assert result["payment_link_sent"] is False
    assert "Pay when you pick up." in captured["body"]


async def test_send_payment_sms_returns_failure_when_telnyx_fails(monkeypatch):
    from payment_service import send_payment_sms

    monkeypatch.setattr("payment_service.create_payment_link", AsyncMock(return_value=None))
    monkeypatch.setattr("telnyx_service.send_sms", AsyncMock(return_value=_sms_failure()))

    result = await send_payment_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order_total=2500,
        order_id="order_abc",
    )
    assert result["success"] is False
    assert result["sms_sent"] is False


async def test_send_payment_sms_formats_total_with_two_decimals(monkeypatch):
    from payment_service import send_payment_sms

    monkeypatch.setattr("payment_service.create_payment_link", AsyncMock(return_value=None))
    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_payment_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order_total=1499,  # $14.99
        order_id="o",
    )
    assert "$14.99" in captured["body"]


# ---------------------------------------------------------------------------
# send_order_confirmation_sms — routes based on prepayment_enabled
# ---------------------------------------------------------------------------

class _FakeOrder:
    def __init__(self, items, total, call_sid="call_1"):
        self.items = items
        self.total = total
        self.call_sid = call_sid


def _item(name="Pizza", quantity=1):
    return SimpleNamespace(name=name, quantity=quantity)


async def test_order_confirmation_routes_to_payment_when_prepayment_enabled(monkeypatch):
    from payment_service import send_order_confirmation_sms

    payment_mock = AsyncMock(return_value={"success": True, "sms_sent": True})
    monkeypatch.setattr("payment_service.send_payment_sms", payment_mock)

    await send_order_confirmation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order=_FakeOrder(items=[_item()], total=2500),
        restaurant={"prepayment_enabled": True},
        config={"sms_enabled": True},
    )
    payment_mock.assert_awaited_once()


async def test_order_confirmation_routes_to_regular_when_prepayment_disabled(monkeypatch):
    from payment_service import send_order_confirmation_sms

    regular_mock = AsyncMock(return_value={"success": True, "sms_sent": True})
    monkeypatch.setattr("payment_service.send_regular_confirmation_sms", regular_mock)

    await send_order_confirmation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order=_FakeOrder(items=[_item()], total=1000),
        restaurant={"prepayment_enabled": False},
        config={"sms_enabled": True},
    )
    regular_mock.assert_awaited_once()


async def test_order_confirmation_short_circuits_when_sms_disabled(monkeypatch):
    from payment_service import send_order_confirmation_sms

    payment_mock = AsyncMock()
    regular_mock = AsyncMock()
    monkeypatch.setattr("payment_service.send_payment_sms", payment_mock)
    monkeypatch.setattr("payment_service.send_regular_confirmation_sms", regular_mock)

    result = await send_order_confirmation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order=_FakeOrder(items=[_item()], total=1000),
        restaurant={"prepayment_enabled": False},
        config={"sms_enabled": False},
    )

    assert result["success"] is False
    payment_mock.assert_not_awaited()
    regular_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# send_regular_confirmation_sms
# ---------------------------------------------------------------------------

async def test_send_regular_confirmation_sms_constructs_message(monkeypatch):
    from payment_service import send_regular_confirmation_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        captured["metadata"] = metadata
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    result = await send_regular_confirmation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order_id="order_abcdef12",
        items_summary="1x Pizza",
        eta_minutes=15,
    )
    assert result["success"] is True
    assert "Hi Joe" in captured["body"]
    assert "Tasty" in captured["body"]
    assert "Pizza" in captured["body"]
    assert "15 minutes" in captured["body"]
    assert captured["metadata"]["purpose"] == "order_confirmation_simple"


async def test_send_regular_confirmation_sms_returns_failure_on_telnyx_failure(monkeypatch):
    from payment_service import send_regular_confirmation_sms

    monkeypatch.setattr("telnyx_service.send_sms",
                        AsyncMock(return_value=_sms_failure()))

    result = await send_regular_confirmation_sms(
        customer_phone="+15551234567",
        customer_name="Joe",
        restaurant_name="Tasty",
        order_id="o",
    )
    assert result["success"] is False
