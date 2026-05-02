"""
SMS Payment Link Service for RingAI

Provides:
- Stripe payment link generation for orders
- SMS delivery of payment links
- Payment status tracking

Optional feature - enabled via prepayment_enabled setting
"""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def create_payment_link(
    order_total: int,  # cents — food total only
    order_id: str,
    restaurant_name: str,
    customer_name: str = "Customer",
    items_description: str = "",
    restaurant_id: str = "",
    convenience_fee_pct: float = 1.0,
) -> Optional[str]:
    """
    Create a Stripe Checkout Session for order prepayment.
    Uses inline price_data — does NOT create persistent Price objects.
    Adds convenience fee as a separate visible line item.
    
    Returns:
        Checkout Session URL, or None if creation fails
    """
    import stripe
    
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        logger.warning("STRIPE_SECRET_KEY not configured - payment links disabled")
        return None
    
    stripe.api_key = stripe_key
    
    try:
        fee_cents = max(1, round(order_total * convenience_fee_pct / 100))
        
        checkout_session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": order_total,
                        "product_data": {
                            "name": f"Order — {restaurant_name}",
                            "description": items_description[:500] if items_description else None,
                        },
                    },
                    "quantity": 1,
                },
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": fee_cents,
                        "product_data": {"name": "Convenience Fee"},
                    },
                    "quantity": 1,
                },
            ],
            metadata={
                "type": "order_payment",
                "order_id": order_id,
                "restaurant_id": restaurant_id,
                "restaurant_name": restaurant_name,
                "customer_name": customer_name,
            },
            after_completion={
                "type": "redirect",
                "redirect": {
                    "url": os.environ.get("PAYMENT_SUCCESS_URL", "https://duuutah.com/payment-success")
                }
            },
        )
        
        logger.info(f"Payment checkout created for order {order_id}: {checkout_session.url}")
        return checkout_session.url
        
    except Exception as e:
        logger.error(f"Stripe payment checkout error: {e}")
        return None


async def send_payment_sms(
    customer_phone: str,
    customer_name: str,
    restaurant_name: str,
    order_total: int,  # cents
    order_id: str,
    items_summary: str = "",
    eta_minutes: int = 20,
) -> Dict[str, Any]:
    """
    Send order confirmation with payment link via SMS.
    
    Returns:
        Dict with success status, sms_sent, payment_link_sent
    """
    result = {
        "success": False,
        "sms_sent": False,
        "payment_link_sent": False,
        "payment_link": None,
    }
    
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_PHONE_NUMBER")
    
    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio not configured - skipping SMS")
        return result
    
    # Create payment link
    payment_link = await create_payment_link(
        order_total=order_total,
        order_id=order_id,
        restaurant_name=restaurant_name,
        customer_name=customer_name,
        items_description=items_summary,
    )
    
    # Format total
    total_str = f"${order_total / 100:.2f}"
    
    # Build message
    message = (
        f"Hi {customer_name}! Your order from {restaurant_name} is confirmed.\n\n"
        f"Order #{order_id[-8:].upper()}\n"
        f"Total: {total_str}\n"
        f"Ready in: ~{eta_minutes} minutes\n"
    )
    
    if items_summary:
        message += f"\n{items_summary}\n"
    
    if payment_link:
        message += f"\nPay now to skip the line:\n{payment_link}"
        result["payment_link"] = payment_link
    else:
        message += "\nPay when you pick up."
    
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        
        client.messages.create(
            body=message,
            from_=from_number,
            to=customer_phone
        )
        
        result["success"] = True
        result["sms_sent"] = True
        result["payment_link_sent"] = bool(payment_link)
        
        logger.info(f"Payment SMS sent to {customer_phone[-4:]} (link: {bool(payment_link)})")
        
    except Exception as e:
        logger.error(f"Payment SMS error: {e}")
    
    return result


async def send_order_confirmation_sms(
    customer_phone: str,
    customer_name: str,
    restaurant_name: str,
    order,  # LiveOrder object
    restaurant: Dict[str, Any],
    config: Dict[str, Any],
    eta_minutes: int = 20,
) -> Dict[str, Any]:
    """
    Send order confirmation SMS, with optional payment link if enabled.
    
    This is the main entry point called after order confirmation.
    """
    prepayment_enabled = restaurant.get("prepayment_enabled", False)
    sms_enabled = config.get("sms_enabled", True)
    
    if not sms_enabled:
        return {"success": False, "reason": "SMS disabled"}
    
    # Build items summary
    items_list = ", ".join(
        f"{item.quantity}x {item.name}" for item in order.items
    )
    
    if prepayment_enabled:
        # Send SMS with payment link
        return await send_payment_sms(
            customer_phone=customer_phone,
            customer_name=customer_name,
            restaurant_name=restaurant_name,
            order_total=order.total,
            order_id=order.call_sid,
            items_summary=items_list,
            eta_minutes=eta_minutes,
        )
    else:
        # Send regular confirmation SMS without payment link
        return await send_regular_confirmation_sms(
            customer_phone=customer_phone,
            customer_name=customer_name,
            restaurant_name=restaurant_name,
            order_id=order.call_sid,
            items_summary=items_list,
            eta_minutes=eta_minutes,
        )


async def send_regular_confirmation_sms(
    customer_phone: str,
    customer_name: str,
    restaurant_name: str,
    order_id: str,
    items_summary: str = "",
    eta_minutes: int = 20,
) -> Dict[str, Any]:
    """Send order confirmation SMS without payment link."""
    result = {
        "success": False,
        "sms_sent": False,
        "payment_link_sent": False,
    }
    
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_PHONE_NUMBER")
    
    if not all([account_sid, auth_token, from_number]):
        return result
    
    message = (
        f"Hi {customer_name}! Your order from {restaurant_name} is confirmed.\n\n"
        f"Order #{order_id[-8:].upper()}\n"
        f"Ready in: ~{eta_minutes} minutes\n"
    )
    
    if items_summary:
        message += f"\n{items_summary}\n"
    
    message += "\nSee you soon!"
    
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        
        client.messages.create(
            body=message,
            from_=from_number,
            to=customer_phone
        )
        
        result["success"] = True
        result["sms_sent"] = True
        
    except Exception as e:
        logger.error(f"Confirmation SMS error: {e}")
    
    return result
