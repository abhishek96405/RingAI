"""
Appointment Reminder Service for RingAI

Sends SMS reminders 24 hours before scheduled appointments.
Can be run as a background task or scheduled job.

Part 2 Enhancement - Appointment Reminders
"""
import os
import base64
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)


async def get_appointments_due_for_reminder(db, hours_ahead: int = 24) -> List[Dict[str, Any]]:
    """
    Find appointments scheduled within the next `hours_ahead` hours
    that haven't received a reminder yet.
    """
    now = datetime.now(timezone.utc)
    target_date = (now + timedelta(hours=hours_ahead)).strftime("%Y-%m-%d")
    
    # Find confirmed appointments for tomorrow that haven't been reminded
    appointments = await db.appointments.find({
        "status": "confirmed",
        "scheduled_date": target_date,
        "reminder_sent": {"$ne": True},
    }, {"_id": 0}).to_list(100)
    
    return appointments


async def send_reminder_sms(
    customer_phone: str,
    customer_name: str,
    service_name: str,
    scheduled_date: str,
    scheduled_time: str,
    business_name: str,
    duration_minutes: int = 60,
) -> bool:
    """
    Send appointment reminder SMS.
    
    Format:
        Reminder: Your {service} appointment at {business} is tomorrow at {time}.
        Duration: {duration}. See you then!
    """

    # Format date nicely
    try:
        date_obj = datetime.strptime(scheduled_date, "%Y-%m-%d")
        date_formatted = date_obj.strftime("%A, %B %d")
    except:
        date_formatted = scheduled_date
    
    name_part = f"Hi {customer_name}! " if customer_name else ""
    
    body = (
        f"{name_part}Reminder: Your appointment at {business_name} is tomorrow!\n\n"
        f"{service_name}\n"
        f"{date_formatted} at {scheduled_time}\n"
        f"Duration: {duration_minutes} min\n\n"
        f"Please arrive 5-10 minutes early. See you soon!"
    )
    
    from telnyx_service import send_sms
    result = await send_sms(
        to=customer_phone,
        body=body,
        idempotency_key=f"reminder:{scheduled_date}:{scheduled_time}:{customer_phone}",
        metadata={
            "purpose": "appointment_reminder",
            "service_name": service_name,
            "business_name": business_name,
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
        },
    )
    return result.success


async def process_appointment_reminders(db) -> Dict[str, Any]:
    """
    Process all due appointment reminders.
    Called by the background job scheduler.
    
    Returns summary of processed reminders.
    """
    result = {
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "appointments": [],
    }
    
    try:
        appointments = await get_appointments_due_for_reminder(db, hours_ahead=24)
        result["processed"] = len(appointments)
        
        for apt in appointments:
            # Get business name
            restaurant = await db.restaurants.find_one(
                {"id": apt.get("restaurant_id")},
                {"_id": 0, "name": 1}
            )
            business_name = restaurant.get("name", "Business") if restaurant else "Business"
            
            # Send reminder
            success = await send_reminder_sms(
                customer_phone=apt.get("customer_phone", ""),
                customer_name=apt.get("customer_name", ""),
                service_name=apt.get("service_name", "Appointment"),
                scheduled_date=apt.get("scheduled_date", ""),
                scheduled_time=apt.get("scheduled_time", ""),
                business_name=business_name,
                duration_minutes=apt.get("duration_minutes", 60),
            )
            
            if success:
                result["sent"] += 1
                # Mark as reminded
                await db.appointments.update_one(
                    {"id": apt.get("id")},
                    {"$set": {
                        "reminder_sent": True,
                        "reminder_sent_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
            else:
                result["failed"] += 1
            
            result["appointments"].append({
                "id": apt.get("id"),
                "customer_name": apt.get("customer_name"),
                "success": success,
            })
        
        logger.info(f"Reminder job complete: {result['sent']}/{result['processed']} sent")
        
    except Exception as e:
        logger.error(f"Reminder job error: {e}")
        result["error"] = str(e)
    
    return result


async def send_single_reminder(db, appointment_id: str) -> bool:
    """
    Send reminder for a single appointment (manual trigger).
    """
    apt = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not apt:
        return False
    
    if apt.get("status") != "confirmed":
        return False
    
    restaurant = await db.restaurants.find_one(
        {"id": apt.get("restaurant_id")},
        {"_id": 0, "name": 1}
    )
    business_name = restaurant.get("name", "Business") if restaurant else "Business"
    
    success = await send_reminder_sms(
        customer_phone=apt.get("customer_phone", ""),
        customer_name=apt.get("customer_name", ""),
        service_name=apt.get("service_name", "Appointment"),
        scheduled_date=apt.get("scheduled_date", ""),
        scheduled_time=apt.get("scheduled_time", ""),
        business_name=business_name,
        duration_minutes=apt.get("duration_minutes", 60),
    )
    
    if success:
        await db.appointments.update_one(
            {"id": appointment_id},
            {"$set": {
                "reminder_sent": True,
                "reminder_sent_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
    
    return success
