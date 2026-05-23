"""
Unit tests for backend/gemini_service.py — SMS senders and prompt router.

Covers send_order_sms, send_menu_sms, get_system_prompt, parse_menu_text.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def _sms_success():
    return SimpleNamespace(success=True, message_id="msg_1", error_code=None, error_message=None)


def _sms_failure():
    return SimpleNamespace(success=False, message_id=None, error_code="X", error_message="boom")


def _make_order(items=None, **kw):
    from gemini_service import LiveOrder, OrderItem

    order = LiveOrder(
        restaurant_id=kw.get("restaurant_id", "rest_a"),
        call_sid=kw.get("call_sid", "call_abcd1234"),
        caller_number=kw.get("caller_number", "+15551234567"),
        customer_name=kw.get("customer_name", "Joe"),
        order_type=kw.get("order_type", "pickup"),
    )
    if items is None:
        items = [OrderItem(name="Pizza", menu_item_id="p1", category="Pizza",
                           unit_price=1299, quantity=1)]
    order.items.extend(items)
    return order


# ---------------------------------------------------------------------------
# send_order_sms
# ---------------------------------------------------------------------------

async def test_send_order_sms_returns_false_for_empty_order():
    from gemini_service import LiveOrder, send_order_sms

    empty = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+1")
    out = await send_order_sms(
        caller_number="+15551234567",
        order=empty,
        restaurant_name="Tasty",
    )
    assert out is False


async def test_send_order_sms_constructs_body_with_items(monkeypatch):
    from gemini_service import send_order_sms

    captured = {}

    async def fake_send_sms(to, body, idempotency_key, metadata):
        captured["body"] = body
        captured["metadata"] = metadata
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    out = await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(),
        restaurant_name="Tasty",
        prep_time_minutes=20,
    )
    assert out is True
    assert "Hi Joe" in captured["body"]
    assert "Pizza" in captured["body"]
    assert "$12.99" in captured["body"]
    assert captured["metadata"]["purpose"] == "order_confirmation"


async def test_send_order_sms_with_delivery_type(monkeypatch):
    from gemini_service import send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(order_type="delivery"),
        restaurant_name="Tasty",
    )
    assert "delivery" in captured["body"].lower() or "Delivery" in captured["body"]


async def test_send_order_sms_with_explicit_payment_link(monkeypatch):
    from gemini_service import send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        captured["metadata"] = kwargs.get("metadata")
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(),
        restaurant_name="Tasty",
        payment_link="https://checkout.stripe.com/c/abc",
    )
    assert "https://checkout.stripe.com/c/abc" in captured["body"]
    assert captured["metadata"]["has_payment_link"] is True


async def test_send_order_sms_generates_payment_link_when_prepayment_enabled(monkeypatch):
    from gemini_service import send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)
    monkeypatch.setattr(
        "payment_service.create_payment_link",
        AsyncMock(return_value="https://stripe.test/checkout/xyz"),
    )

    await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(),
        restaurant_name="Tasty",
        restaurant={"prepayment_enabled": True, "timezone": "UTC"},
    )
    assert "stripe.test/checkout/xyz" in captured["body"]


async def test_send_order_sms_uses_dynamic_eta(monkeypatch):
    """When a restaurant is supplied, calculate_dynamic_eta is consulted."""
    from gemini_service import send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    eta_mock = AsyncMock(return_value={"eta_minutes": 35, "factors": {}})
    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)
    monkeypatch.setattr("eta_service.calculate_dynamic_eta", eta_mock)

    await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(),
        restaurant_name="Tasty",
        restaurant={"timezone": "UTC", "prepayment_enabled": False},
    )
    eta_mock.assert_awaited_once()
    assert "35 min" in captured["body"]


async def test_send_order_sms_falls_back_when_eta_calculation_fails(monkeypatch):
    from gemini_service import send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return _sms_success()

    async def boom(*a, **k):
        raise RuntimeError("eta down")

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)
    monkeypatch.setattr("eta_service.calculate_dynamic_eta", boom)

    out = await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(),
        restaurant_name="Tasty",
        restaurant={"timezone": "UTC"},
        prep_time_minutes=25,
    )
    assert out is True
    # The fallback prep_time should appear
    assert "25 min" in captured["body"]


async def test_send_order_sms_returns_false_when_telnyx_fails(monkeypatch):
    from gemini_service import send_order_sms

    monkeypatch.setattr("telnyx_service.send_sms",
                        AsyncMock(return_value=_sms_failure()))

    out = await send_order_sms(
        caller_number="+15551234567",
        order=_make_order(),
        restaurant_name="Tasty",
    )
    assert out is False


# ---------------------------------------------------------------------------
# send_menu_sms
# ---------------------------------------------------------------------------

async def test_send_menu_sms_constructs_url(monkeypatch):
    from gemini_service import send_menu_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        captured["metadata"] = kwargs.get("metadata")
        return _sms_success()

    monkeypatch.setattr("telnyx_service.send_sms", fake_send_sms)

    out = await send_menu_sms(
        caller_number="+15551234567",
        restaurant_name="Tasty Bites",
        restaurant_id="rest_a",
        base_url="https://api.test",
    )
    assert out is True
    assert "Tasty Bites" in captured["body"]
    assert "https://api.test/menu/rest_a" in captured["body"]
    assert captured["metadata"]["purpose"] == "menu_share"


# ---------------------------------------------------------------------------
# get_system_prompt — router behavior
# ---------------------------------------------------------------------------

def test_get_system_prompt_routes_restaurant_to_build_system_prompt():
    from gemini_service import get_system_prompt

    out = get_system_prompt(
        business_type="restaurant",
        restaurant_name="Tasty",
        cuisine_type="italian",
        persona="friendly",
        business_rules=[],
        escalation_rules=[],
        menu_items=[],
        disclosure_text="hi",
    )
    assert "Tasty" in out


def test_get_system_prompt_routes_salon_to_appointment_builder():
    from gemini_service import get_system_prompt

    out = get_system_prompt(
        business_type="salon",
        restaurant_name="Snip Salon",
        services=[{"name": "Haircut", "duration_minutes": 30}],
        business_rules=[],
        escalation_phone=None,
        operating_hours=None,
        restaurant_timezone="UTC",
        disclosure_text="hi from Snip!",
    )
    assert "Snip Salon" in out


def test_get_system_prompt_unknown_business_type_falls_back_to_restaurant():
    """An unrecognised business_type should not crash."""
    from gemini_service import get_system_prompt

    out = get_system_prompt(
        business_type="zoo",
        restaurant_name="Zoo Cafe",
        cuisine_type="snack",
        persona="friendly",
        business_rules=[],
        escalation_rules=[],
        menu_items=[],
        disclosure_text="hi",
    )
    assert "Zoo Cafe" in out


# ---------------------------------------------------------------------------
# parse_menu_text — happy and fallback paths
# ---------------------------------------------------------------------------

async def test_parse_menu_text_uses_mock_when_no_client(monkeypatch):
    from gemini_service import parse_menu_text
    monkeypatch.setattr("gemini_service._get_client", lambda: None)

    out = await parse_menu_text("Pizza - $10\nSalad - $7")
    assert "items" in out
    assert "categories" in out


async def test_parse_menu_text_with_client(monkeypatch):
    from gemini_service import parse_menu_text

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(
                            content='{"items": [{"name": "Pizza", "category": "Main", "price": 1500, "description": "", "allergens": []}], "categories": ["Main"], "warnings": []}'
                        ))],
                        usage=None,
                    )

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    out = await parse_menu_text("Pizza - $15")
    assert len(out["items"]) == 1
    assert out["items"][0]["name"] == "Pizza"
    assert out["items"][0]["price"] == 1500


async def test_parse_menu_text_strips_code_fence(monkeypatch):
    from gemini_service import parse_menu_text

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(
                            content='```json\n{"items": [], "categories": [], "warnings": []}\n```'
                        ))],
                        usage=None,
                    )

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    out = await parse_menu_text("nothing")
    assert out["items"] == []


async def test_parse_menu_text_falls_back_to_mock_on_invalid_json(monkeypatch):
    from gemini_service import parse_menu_text

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(
                            content="not json at all"
                        ))],
                        usage=None,
                    )

    monkeypatch.setattr("gemini_service._get_client", lambda: _FakeClient)

    out = await parse_menu_text("Pizza - $10")
    assert "items" in out  # mock fallback always returns this shape


# ---------------------------------------------------------------------------
# _mock_parse_menu — best-effort regex parser
# ---------------------------------------------------------------------------

def test_mock_parse_menu_extracts_basic_items():
    from gemini_service import _mock_parse_menu

    text = """
    Pizza - $12.99
    Salad - $7.50
    Coke - $2.00
    """
    out = _mock_parse_menu(text)
    assert len(out["items"]) >= 1
    # Prices should be in cents
    for item in out["items"]:
        assert isinstance(item["price"], int)


def test_mock_parse_menu_returns_default_shape_on_empty():
    from gemini_service import _mock_parse_menu
    out = _mock_parse_menu("")
    assert "items" in out
    assert "categories" in out
    assert "warnings" in out


# ---------------------------------------------------------------------------
# is_gemini_available / _get_client
# ---------------------------------------------------------------------------

def test_is_gemini_available_returns_false_without_keys(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    import gemini_service
    monkeypatch.setattr(gemini_service, "_client", None)
    assert gemini_service.is_gemini_available() is False


def test_is_gemini_available_initialises_client_with_keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    import gemini_service
    monkeypatch.setattr(gemini_service, "_client", None)
    # We don't actually want to make API calls; check the client got created.
    assert gemini_service.is_gemini_available() is True
    assert gemini_service._client is not None


# ---------------------------------------------------------------------------
# generate_menu_examples
# ---------------------------------------------------------------------------

def test_generate_menu_examples_returns_empty_for_small_menu():
    from gemini_service import MenuIndex, generate_menu_examples

    idx = MenuIndex([{"id": "1", "name": "Only Item", "category": "x",
                     "price": 100, "available": True}])
    assert generate_menu_examples(idx) == ""


def test_generate_menu_examples_includes_real_names():
    from gemini_service import MenuIndex, generate_menu_examples

    idx = MenuIndex([
        {"id": "1", "name": "Chicken Biryani", "category": "Mains",
         "price": 1299, "available": True},
        {"id": "2", "name": "Mango Lassi", "category": "Drinks",
         "price": 399, "available": True},
    ])
    out = generate_menu_examples(idx)
    assert "Chicken Biryani" in out


def test_generate_menu_examples_includes_partial_match_when_3_word_item_exists():
    from gemini_service import MenuIndex, generate_menu_examples

    idx = MenuIndex([
        {"id": "1", "name": "Veg Cooker Pulav", "category": "Mains",
         "price": 1099, "available": True},
        {"id": "2", "name": "Mango Lassi", "category": "Drinks",
         "price": 399, "available": True},
    ])
    out = generate_menu_examples(idx)
    # Partial-match block triggers
    assert "Veg" in out
