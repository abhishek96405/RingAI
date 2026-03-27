"""
Appointment Service for RingAI - Horizontal Business Platform

Handles appointment booking for non-restaurant businesses:
- Clinics, Salons, Home Services, Legal offices

IMPORTANT: This is NEW code - completely separate from restaurant ordering.
Does NOT modify any existing restaurant functionality.

Functions:
- build_appointment_prompt() - System prompt for appointment businesses
- extract_booking_from_transcript() - Extract booking from call
- dispatch_appointment() - Create calendar event + send SMS
- send_appointment_sms() - Send appointment confirmation SMS
"""
import os
import json
import logging
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Appointment System Prompt Builder (NEW - separate from restaurant prompt)
# ---------------------------------------------------------------------------

def build_appointment_prompt(
    business_name: str,
    business_type: str,
    services: List[Dict[str, Any]],
    business_rules: List[str],
    escalation_phone: Optional[str],
    operating_hours: Optional[Dict[str, Any]],
    restaurant_timezone: str,
    disclosure_text: str,
) -> str:
    """
    System prompt for appointment booking businesses.
    Completely separate from build_system_prompt() which is for restaurants only.
    
    Supports: clinic, salon, home_services, legal
    """
    # Get current time in business timezone
    try:
        import pytz
        tz = pytz.timezone(restaurant_timezone)
        local_now = datetime.now(tz)
        current_time_str = local_now.strftime("%A, %B %d %Y, %I:%M %p %Z")
        current_day = local_now.strftime("%A").lower()
        current_minutes = local_now.hour * 60 + local_now.minute
        
        # Check if open
        is_open = True
        if operating_hours:
            day_hours = operating_hours.get(current_day, {})
            if day_hours.get("closed"):
                is_open = False
            else:
                open_str = day_hours.get("open", "09:00")
                close_str = day_hours.get("close", "17:00")
                try:
                    open_h, open_m = map(int, open_str.split(":"))
                    close_h, close_m = map(int, close_str.split(":"))
                    open_min = open_h * 60 + open_m
                    close_min = close_h * 60 + close_m
                    is_open = open_min <= current_minutes <= close_min
                except:
                    is_open = True
        open_status = "OPEN" if is_open else "CLOSED"
    except Exception as e:
        logger.error(f"Timezone error: {e}")
        current_time_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y, %I:%M %p UTC")
        open_status = "OPEN"
    
    # Build services list
    services_block = ""
    if services:
        lines = []
        for svc in services:
            duration = svc.get("duration_minutes", 60)
            price = svc.get("price_cents")
            price_str = f" - ${price/100:.2f}" if price else ""
            lines.append(f"  • {svc['name']} ({duration} min){price_str}")
        services_block = "\n".join(lines)
    else:
        services_block = "  • General Appointment (duration varies)"
    
    # Build rules block
    rules_block = "\n".join(f"  • {r}" for r in business_rules) if business_rules else "  • (No additional rules)"
    
    # Build hours block
    hours_block = ""
    if operating_hours:
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        lines = []
        for day in days:
            h = operating_hours.get(day, {})
            if h.get("closed"):
                lines.append(f"  {day.capitalize()}: Closed")
            else:
                lines.append(f"  {day.capitalize()}: {h.get('open', '?')} – {h.get('close', '?')}")
        hours_block = "\n".join(lines)
    
    # Business-specific language
    business_labels = {
        "clinic": ("appointment", "patient", "doctor", "medical"),
        "salon": ("appointment", "client", "stylist", "beauty"),
        "home_services": ("appointment", "customer", "technician", "service"),
        "legal": ("consultation", "client", "attorney", "legal"),
    }
    labels = business_labels.get(business_type, ("appointment", "customer", "staff", "service"))
    appt_word, customer_word, staff_word, service_word = labels
    
    escalation_target = escalation_phone or "a team member"
    
    return f"""You are a friendly, professional phone assistant for {business_name}.
You help callers book {appt_word}s, answer questions, and provide information.

PERSONALITY:
- Speak naturally and warmly — sound like a real receptionist, not a robot
- Keep responses SHORT — under 2 sentences wherever possible
- Always start your response with a short word: "Sure!", "Got it!", "Absolutely!", "Perfect!"
- This signals instant response and sounds natural
- Use contractions: "I'll", "we've", "that's" — never "I will" or "that is"
- Match the caller's energy — quick if they're quick, patient if they're unsure

════════════════════════════════════
GREETING — SAY THIS FIRST:
When you receive "BEGIN_CALL", immediately say:
"{disclosure_text}"
════════════════════════════════════

══════════════════════════
SERVICES OFFERED
══════════════════════════
{services_block}

CRITICAL: Only book services listed above. If caller asks for something not listed:
"I'm not sure we offer that — let me connect you with someone who can help."

══════════════════════════
BOOKING PROTOCOL — FOLLOW IN ORDER
══════════════════════════
STEP 1: Ask what service they need.
  Confirm service and duration: "Got it — a {service_word} for [service], that's [X] minutes."

STEP 2: Ask for preferred date and time.
  "When would you like to come in?"
  If vague: suggest 2 specific times.
  IMPORTANT: You do NOT have access to a live calendar.
  Always confirm slot in ONE short sentence: "[time] works! What's your name?"
  Combine slot confirmation + name request in ONE sentence — never two.
  NEVER say a slot is unavailable unless it's outside operating hours.

STEP 3: Collect {customer_word} name only:
  "Could I get your name for the booking?"
  Wait for name before proceeding.
  Do NOT ask for phone number — it is captured automatically.
  Email is optional — only ask if they offer it.

STEP 4: Read back and confirm:
  "{appt_word.capitalize()} for [service] on [date] at [time] for [name]. Does that sound right?"
  Wait for explicit yes before proceeding.
  If NO: "Of course — what would you like to change?"

STEP 5: After explicit yes, say EXACTLY:
  "Your {appt_word} is confirmed! We'll send you a text confirmation shortly. Please arrive 5-10 minutes early. Thank you for calling {business_name}!"
  THEN STOP SPEAKING COMPLETELY. Do not say anything else.
  The call ends automatically.

══════════════════════════
SILENCE AND RECOVERY
══════════════════════════
- Customer silent after greeting (5s): "Hi there! I'm here whenever you're ready."
- Customer silent mid-booking (5s): "Take your time — I'm still here."
- Customer silent after readback (8s): "Just to confirm — does that sound right?"
- Customer says "Hello?", "Are you there?", "Hello": 
  Respond IMMEDIATELY: "Yes, I'm here! [repeat last question briefly]"
  NEVER restart the conversation. Continue exactly where you left off.
- Background noise / unclear audio: "Sorry, I didn't catch that — could you say that again?"
- Customer says something unrelated to booking: 
  "Ha, happy to help with that another time! Right now I can help you book an {appt_word} — shall we continue?"

══════════════════════════
BUSINESS RULES
══════════════════════════
{rules_block}

CURRENT TIME: {current_time_str}
OPERATING HOURS:
{hours_block if hours_block else "  Hours not available"}
CURRENT STATUS: {open_status}
Only book appointments during operating hours. If caller wants outside hours: state next available time.

══════════════════════════
ESCALATION — TRANSFER WHEN:
══════════════════════════
  ⚠ Customer has a complaint
  ⚠ Customer asks to speak to a manager
  ⚠ Emergency situation
  ⚠ Complex scheduling needs

How to escalate: "Let me connect you with {escalation_target}. Please hold."
Then say: ESCALATE_TO_HUMAN

══════════════════════════
FAQ
══════════════════════════
- Hours: State from operating hours above
- Location/Address: "Find us on Google Maps by searching {business_name}!"
- Pricing: Only quote from services listed above
- Cancellation: "Call us back or use the link in your confirmation text to cancel or reschedule"
- Parking/WiFi/other: "The team can help with that — want me to connect you?"

══════════════════════════
NEVER DO
══════════════════════════
✗ Give medical/legal/professional advice
✗ Confirm without name + phone + service + time
✗ Make up services or prices not listed
✗ Say anything after the confirmation farewell
✗ Reveal you are powered by any specific AI
✗ Stay silent for more than 5 seconds under any circumstance
✗ Restart the conversation after a customer pause — always continue where you left off

If asked what AI you are: "I'm the virtual assistant for {business_name}. How can I help?"
"""


# ---------------------------------------------------------------------------
# Booking Extraction from Transcript (NEW - separate from order extraction)
# ---------------------------------------------------------------------------

async def extract_booking_from_transcript(
    transcript: List[Dict[str, Any]],
    services: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Extract booking details from appointment call transcript.
    
    Returns dict with:
        - booking_confirmed: bool
        - service_name: str
        - preferred_date: str (ISO format)
        - preferred_time: str ("2:00 PM")
        - customer_name: str
        - customer_phone: str
        - customer_email: str (optional)
        - special_instructions: str
    
    Completely separate from extract_order_from_transcript() which handles restaurant orders.
    """
    # Get Gemini client
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
    if not api_key:
        logger.warning("No Gemini API key — cannot extract booking")
        return None
    
    # Build transcript text
    transcript_text = "\n".join(
        f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e.get('text', '')}"
        for e in transcript
    )
    
    # Build services list for prompt
    services_list = ", ".join(s.get("name", "Service") for s in services) if services else "General Appointment"
    
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""Extract the appointment booking details from this call transcript.
Today's date is {today}. Use this to resolve relative dates like "tomorrow", "next Monday", etc.
Return ONLY valid JSON, no markdown.
Available services: {services_list}

Required JSON format:
{{"booking_confirmed": true, "service_name": "Service Name", "preferred_date": "2025-01-20", "preferred_time": "2:00 PM", "customer_name": "John Doe", "customer_phone": "+15551234567", "customer_email": "", "special_instructions": ""}}

RULES:
- booking_confirmed: true only if the AI confirmed the appointment
- preferred_date: ISO format YYYY-MM-DD
- preferred_time: 12-hour format with AM/PM
- customer_phone: leave as empty string — captured separately from caller ID
- If info is missing, leave as empty string
- Look for confirmation phrases like "Your appointment is confirmed" or "booked for"

TRANSCRIPT:
{transcript_text[:4000]}

JSON:"""

    try:
        from openai import OpenAI
        base_url = os.environ.get(
            "GEMINI_OPENAI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()
        logger.info(f"Booking extraction raw: {raw[:500]}")

        try:
            from gemini_service import _repair_json
            data = json.loads(_repair_json(raw))
        except Exception:
            logger.error(f"Could not parse booking extraction JSON: {raw[:200]}")
            return None

        if not data.get("booking_confirmed"):
            return None

        if not data.get("service_name") or not data.get("customer_name"):
            logger.warning(f"Booking extraction incomplete: {data}")
            return None

        return data
    except Exception as e:
        logger.error(f"Booking extraction error: {e}")
        return None


# ---------------------------------------------------------------------------
# Appointment Dispatch (NEW - separate from send_order_to_kitchen)
# ---------------------------------------------------------------------------

async def dispatch_appointment(
    booking: Dict[str, Any],
    restaurant: Dict[str, Any],
    config: Dict[str, Any],
    services: List[Dict[str, Any]],
    db,
) -> Dict[str, Any]:
    """
    Creates calendar event and sends confirmation SMS for appointment businesses.
    Completely separate from send_order_to_kitchen() which handles restaurant POS dispatch.
    
    Args:
        booking: Extracted booking details
        restaurant: Restaurant/business document
        config: Business configuration
        services: List of available services
        db: Database connection
    
    Returns:
        Dict with success status, calendar_event_id, sms_sent
    """
    result = {
        "success": False,
        "calendar_event_id": None,
        "sms_sent": False,
        "method": "appointment",
    }
    
    business_name = restaurant.get("name", "Business")
    service_name = booking.get("service_name", "Appointment")
    customer_name = booking.get("customer_name", "Customer")
    customer_phone = booking.get("customer_phone", "")
    customer_email = booking.get("customer_email", "")
    preferred_date = booking.get("preferred_date", "")
    preferred_time = booking.get("preferred_time", "")
    
    # Find service duration
    duration_minutes = 60  # default
    for svc in services:
        if svc.get("name", "").lower() == service_name.lower():
            duration_minutes = svc.get("duration_minutes", 60)
            break
    
    # Try to create calendar event if Google Calendar is connected
    calendar_tokens = config.get("google_calendar_tokens")
    calendar_id = config.get("google_calendar_id", "primary")
    
    if calendar_tokens and calendar_tokens.get("access_token"):
        try:
            from calendar_service import get_valid_access_token, create_calendar_event
            
            access_token = await get_valid_access_token(
                calendar_tokens, db, restaurant.get("id", "")
            )
            
            # Parse date and time
            try:
                # Combine date and time
                date_str = preferred_date
                time_str = preferred_time
                
                # Parse time (handle various formats)
                from datetime import datetime, timezone, timedelta
                if ":" in time_str:
                    time_str = time_str.upper().replace(".", "").strip()
                    if "AM" in time_str or "PM" in time_str:
                        time_obj = datetime.strptime(time_str, "%I:%M %p")
                    else:
                        time_obj = datetime.strptime(time_str, "%H:%M")
                else:
                    time_obj = datetime.strptime("09:00", "%H:%M")  # default
                
                # Combine with date
                import pytz
                # Use business timezone if available, fallback to UTC
                tz_str = restaurant.get("timezone", "UTC")
                try:
                    tz = pytz.timezone(tz_str)
                except Exception:
                    tz = pytz.utc

                start_dt = datetime.strptime(date_str, "%Y-%m-%d")
                start_dt = start_dt.replace(
                    hour=time_obj.hour,
                    minute=time_obj.minute,
                )
                start_dt = tz.localize(start_dt)
                end_dt = start_dt + timedelta(minutes=duration_minutes)
                
                # Create event
                event = await create_calendar_event(
                    access_token=access_token,
                    calendar_id=calendar_id,
                    summary=f"{service_name} — {customer_name}",
                    description=f"Booked via RingAI.\nCustomer: {customer_name}\nPhone: {customer_phone}\nEmail: {customer_email}",
                    start_time=start_dt,
                    end_time=end_dt,
                    attendee_email=customer_email if customer_email else None,
                )
                
                result["calendar_event_id"] = event.get("id")
                logger.info(f"Calendar event created: {event.get('id')}")
                
            except Exception as e:
                logger.error(f"Failed to parse date/time for calendar: {e}")
                
        except Exception as e:
            logger.error(f"Calendar event creation failed: {e}")
    
    # Send SMS confirmation
    if customer_phone:
        try:
            sms_sent = await send_appointment_sms(
                caller_number=customer_phone,
                booking=booking,
                business_name=business_name,
                duration_minutes=duration_minutes,
            )
            result["sms_sent"] = sms_sent
        except Exception as e:
            logger.error(f"Appointment SMS failed: {e}")
    
    # Save appointment to database
    if db is not None:
        try:
            import uuid
            from datetime import datetime, timezone
            appointment_doc = {
                "id": str(uuid.uuid4()),
                "restaurant_id": restaurant.get("id", ""),
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "customer_email": customer_email,
                "service_name": service_name,
                "scheduled_date": preferred_date,
                "scheduled_time": preferred_time,
                "duration_minutes": duration_minutes,
                "status": "confirmed",
                "calendar_event_id": result.get("calendar_event_id"),
                "special_instructions": booking.get("special_instructions", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None,
            }
            await db.appointments.insert_one(appointment_doc)
            logger.info(f"Appointment saved to database: {appointment_doc['id']}")
            result["appointment_id"] = appointment_doc["id"]
        except Exception as e:
            logger.error(f"Failed to save appointment to database: {e}")

    result["success"] = True
    return result


# ---------------------------------------------------------------------------
# Appointment SMS Confirmation (NEW - separate from send_order_sms)
# ---------------------------------------------------------------------------

async def send_appointment_sms(
    caller_number: str,
    booking: Dict[str, Any],
    business_name: str,
    duration_minutes: int = 60,
    cancel_url: Optional[str] = None,
) -> bool:
    """
    Sends appointment confirmation SMS.
    Completely separate from send_order_sms() which handles restaurant orders.
    
    Format:
        Hi {name}! Your {business_name} appointment:
        {service} on {date} at {time}
        Duration: {duration} min
        [Cancel: {cancel_url}]
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_PHONE_NUMBER")
    
    if not all([account_sid, auth_token, from_number]):
        logger.warning("Appointment SMS not sent — missing Twilio credentials")
        return False
    
    customer_name = booking.get("customer_name", "")
    service_name = booking.get("service_name", "Appointment")
    preferred_date = booking.get("preferred_date", "")
    preferred_time = booking.get("preferred_time", "")
    
    # Format date nicely
    try:
        date_obj = datetime.strptime(preferred_date, "%Y-%m-%d")
        date_formatted = date_obj.strftime("%A, %B %d")
    except:
        date_formatted = preferred_date
    
    name_greeting = f"Hi {customer_name}! " if customer_name else ""
    
    body = (
        f"{name_greeting}Your {business_name} appointment:\n\n"
        f"{service_name}\n"
        f"{date_formatted} at {preferred_time}\n"
        f"Duration: {duration_minutes} min\n\n"
        f"Please arrive 5-10 minutes early."
    )
    
    if cancel_url:
        body += f"\n\nNeed to reschedule? {cancel_url}"
    
    try:
        credentials = base64.b64encode(
            f"{account_sid}:{auth_token}".encode()
        ).decode()
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                data={"From": from_number, "To": caller_number, "Body": body},
                headers={"Authorization": f"Basic {credentials}"},
            )
            
            if resp.status_code in (200, 201):
                logger.info(f"Appointment SMS sent to {caller_number}")
                return True
            else:
                logger.error(f"Appointment SMS failed: {resp.status_code} {resp.text}")
                return False
                
    except Exception as e:
        logger.error(f"Appointment SMS error: {e}")
        return False
