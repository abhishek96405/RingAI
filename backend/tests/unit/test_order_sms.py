"""
A7-6 display: the order-confirmation SMS lists each line at its modifier-inclusive
subtotal (not the base unit_price) and surfaces the chosen modifier names, so the
SMS lines sum to order.total and match the Clover ticket / dashboard.
"""


async def test_order_sms_body_includes_modifiers_and_sums_to_total(monkeypatch):
    import telnyx_service
    from telnyx_service import SMSResult
    from gemini_service import LiveOrder, OrderItem, send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return SMSResult(success=True, message_id="m1")

    monkeypatch.setattr(telnyx_service, "send_sms", fake_send_sms)

    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+15551234567")
    # 1x Chicken Biryani $15.99 base + $4.99 modifier → $20.98 effective line
    order.items.append(OrderItem(
        name="Chicken Biryani", menu_item_id="1", category="Mains",
        unit_price=1599, quantity=1,
        modifiers=["Medium", "Extra Chicken Meat"], modifier_total=499,
    ))
    # 1x Mango Lassi $5.99, no modifiers
    order.items.append(OrderItem(
        name="Mango Lassi", menu_item_id="2", category="Drinks",
        unit_price=599, quantity=1,
    ))

    ok = await send_order_sms(
        caller_number="+15551234567", order=order,
        restaurant_name="Bawarchi", restaurant=None,
    )
    assert ok is True
    body = captured["body"]
    assert "Extra Chicken Meat" in body          # modifier name surfaces
    assert "Medium" in body
    assert "$20.98" in body                       # 1599 + 499, modifier-inclusive line
    assert "Total: $26.97" in body                # 2098 + 599 = 2697
    assert "$15.99" not in body                   # base price must NOT leak onto the line


async def test_order_sms_no_modifiers_unchanged(monkeypatch):
    import telnyx_service
    from telnyx_service import SMSResult
    from gemini_service import LiveOrder, OrderItem, send_order_sms

    captured = {}

    async def fake_send_sms(to, body, **kwargs):
        captured["body"] = body
        return SMSResult(success=True, message_id="m1")

    monkeypatch.setattr(telnyx_service, "send_sms", fake_send_sms)

    order = LiveOrder(restaurant_id="r", call_sid="c", caller_number="+15551234567")
    order.items.append(OrderItem(
        name="Samosa", menu_item_id="1", category="Starters",
        unit_price=500, quantity=2,
    ))

    ok = await send_order_sms(
        caller_number="+15551234567", order=order,
        restaurant_name="Bawarchi", restaurant=None,
    )
    assert ok is True
    body = captured["body"]
    assert "2x Samosa" in body
    assert "$10.00" in body                        # 500 * 2, no modifier drift
    assert "Total: $10.00" in body
