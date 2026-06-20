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
import asyncio
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

# ---------------------------------------------------------------------------
# Slot availability engine
# ---------------------------------------------------------------------------

async def get_available_slots(
    restaurant_id: str,
    date_str: str,
    service_name: Optional[str],
    services: List[Dict[str, Any]],
    config: Dict[str, Any],
    db,
) -> List[Dict[str, Any]]:
    """
    Return available slot times for a given date.

    A slot is unavailable if:
      - Already booked >= slot_capacity times
      - Explicitly blocked in db.blocked_slots
      - Outside operating hours
    """
    from datetime import datetime, timedelta

    slot_interval = int(config.get("slot_interval_minutes", 30))
    slot_capacity = int(config.get("slot_capacity", 1))
    operating_hours = config.get("operating_hours", {})

    # Resolve service duration
    duration_minutes = 60
    if service_name and services:
        for svc in services:
            if svc.get("name", "").lower() == service_name.lower():
                duration_minutes = svc.get("duration_minutes", 60)
                break

    # Parse requested date
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logger.error(f"get_available_slots: invalid date {date_str!r}")
        return []

    # Business hours for that day
    day_name = date_obj.strftime("%A").lower()
    day_hours = operating_hours.get(day_name, {})
    if day_hours.get("closed"):
        return []

    open_str = day_hours.get("open", "09:00")
    close_str = day_hours.get("close", "17:00")
    try:
        open_h, open_m = map(int, open_str.split(":"))
        close_h, close_m = map(int, close_str.split(":"))
    except ValueError:
        return []

    # Generate slot grid
    slots_grid: List[str] = []
    cursor_total = open_h * 60 + open_m
    close_total = close_h * 60 + close_m

    while cursor_total + duration_minutes <= close_total:
        h, m = divmod(cursor_total, 60)
        slots_grid.append(f"{h:02d}:{m:02d}")
        cursor_total += slot_interval

    if not slots_grid:
        return []

    # Filter out past slots if the requested date is today
    import pytz
    try:
        tz_str = config.get("timezone", "UTC")
        tz = pytz.timezone(tz_str)
        now_local = datetime.now(pytz.utc).astimezone(tz)
        today_str = now_local.strftime("%Y-%m-%d")
        if date_str == today_str:
            current_minutes = now_local.hour * 60 + now_local.minute
            slots_grid = [
                s for s in slots_grid
                if int(s.split(":")[0]) * 60 + int(s.split(":")[1]) > current_minutes
            ]
    except Exception:
        pass  # timezone error — keep all slots rather than blocking everything

    if not slots_grid:
        return []

    # Fetch existing bookings
    booked_counts: Dict[str, int] = {}
    if db is not None:
        existing = await db.appointments.find(
            {
                "restaurant_id": restaurant_id,
                "scheduled_date": date_str,
                "status": {"$nin": ["cancelled"]},
            },
            {"_id": 0, "scheduled_time": 1},
        ).to_list(500)
        for appt in existing:
            raw = appt.get("scheduled_time", "")
            try:
                t_upper = raw.strip().upper()
                if "AM" in t_upper or "PM" in t_upper:
                    t = datetime.strptime(t_upper, "%I:%M %p")
                else:
                    t = datetime.strptime(raw.strip(), "%H:%M")
                key = t.strftime("%H:%M")
                booked_counts[key] = booked_counts.get(key, 0) + 1
            except Exception:
                pass

    # Fetch blocked slots
    blocked_times: set = set()
    if db is not None:
        blocked_docs = await db.blocked_slots.find(
            {"restaurant_id": restaurant_id, "date": date_str},
            {"_id": 0, "slot_time": 1},
        ).to_list(200)
        blocked_times = {d["slot_time"] for d in blocked_docs}

    # Build result
    result = []
    for slot in slots_grid:
        booked = booked_counts.get(slot, 0)
        blocked = slot in blocked_times
        available = booked < slot_capacity and not blocked
        h, m = map(int, slot.split(":"))
        dt = datetime(2000, 1, 1, h, m)
        try:
            display = dt.strftime("%-I:%M %p")   # Linux/Mac
        except ValueError:
            display = dt.strftime("%I:%M %p").lstrip("0")  # fallback
        result.append({
            "slot_time": slot,
            "display_time": display,
            "booked": booked,
            "capacity": slot_capacity,
            "blocked": blocked,
            "available": available,
        })

    return result


async def pre_fetch_availability(
    restaurant_id: str,
    services: List[Dict[str, Any]],
    config: Dict[str, Any],
    db,
    days_ahead: int = 7,
) -> Dict[str, Any]:
    """
    Pre-fetches availability for today + next N days before the call starts.
    Result is injected into the system prompt so the AI never needs a mid-call
    tool call for common date requests (today, tomorrow, this week).

    Returns dict: {"2026-03-29": ["9:00 AM", "10:00 AM", ...], ...}
    Empty list means closed or fully booked.
    """
    from datetime import date, timedelta
    import pytz

    tz_str = config.get("timezone", "UTC")
    try:
        tz = pytz.timezone(tz_str)
        today = datetime.now(pytz.utc).astimezone(tz).date()
    except Exception:
        today = date.today()

    result: Dict[str, List[str]] = {}

    for i in range(days_ahead):
        target_date = today + timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")
        try:
            slots = await get_available_slots(
                restaurant_id=restaurant_id,
                date_str=date_str,
                service_name=None,   # fetch all regardless of service
                services=services,
                config=config,
                db=db,
            )
            result[date_str] = [
                s["display_time"] for s in slots if s["available"]
            ]
        except Exception as e:
            logger.warning(f"pre_fetch_availability: failed for {date_str}: {e}")
            result[date_str] = []

    return result


def build_appointment_prompt(
    business_name: str,
    business_type: str,
    services: List[Dict[str, Any]],
    business_rules: List[str],
    escalation_phone: Optional[str],
    operating_hours: Optional[Dict[str, Any]],
    restaurant_timezone: str,
    disclosure_text: str,
    cached_availability: Optional[Dict[str, List[str]]] = None,
    customer_profile: dict = None,
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

    # Build availability block from pre-cached data.
    # Format: compressed ranges to minimise system prompt size.
    # Instead of listing every slot (168+ tokens for 7 days),
    # show open range(s) per day and only call out taken slots.
    availability_block = ""
    if cached_availability:
        from datetime import datetime as _dt, timedelta as _td

        def _slots_to_compressed(slots: list) -> str:
            """
            Convert a flat list of display times into a compact range string.
            e.g. ["9:00 AM","9:30 AM","10:00 AM","1:00 PM"] →
                 "9:00 AM–10:00 AM, 1:00 PM"
            Consecutive slots (30-min apart) are merged into ranges.
            Isolated slots are shown as-is.
            """
            if not slots:
                return "Fully booked"

            # Parse to minutes-since-midnight for arithmetic
            def _parse(t: str) -> int:
                try:
                    dt = _dt.strptime(t.strip().upper(), "%I:%M %p")
                    return dt.hour * 60 + dt.minute
                except ValueError:
                    return -1

            def _fmt(minutes: int) -> str:
                h, m = divmod(minutes, 60)
                period = "AM" if h < 12 else "PM"
                h12 = h % 12 or 12
                return f"{h12}:{m:02d} {period}"

            parsed = sorted(set(_parse(s) for s in slots if _parse(s) >= 0))
            if not parsed:
                return "Fully booked"

            # Group into consecutive runs (allow up to 30-min gap = one slot interval)
            groups = []
            start = parsed[0]
            prev = parsed[0]
            for t in parsed[1:]:
                if t - prev <= 30:
                    prev = t
                else:
                    groups.append((start, prev))
                    start = t
                    prev = t
            groups.append((start, prev))

            parts = []
            for s, e in groups:
                if s == e:
                    parts.append(_fmt(s))
                else:
                    parts.append(f"{_fmt(s)}–{_fmt(e)}")
            return ", ".join(parts)

        lines = []
        for date_str, slots in sorted(cached_availability.items()):
            try:
                label = _dt.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")
            except ValueError:
                label = date_str
            compressed = _slots_to_compressed(slots)
            lines.append(f"  {label}: {compressed}")

        if lines:
            availability_block = (
                "\n══════════════════════════\n"
                "AVAILABILITY (loaded at call start — accurate as of now)\n"
                "══════════════════════════\n"
                + "\n".join(lines)
                + "\n\nFor dates beyond this list, call check_availability."
                + "\nSystem verifies slot at confirmation — if taken, staff will follow up."
            )

    if customer_profile:
        appt_last = f"Last appointment: {customer_profile.get('last_order', {}).get('service_name', 'not available')}" if customer_profile.get("last_order") else "Last appointment: not available"
        customer_block = f"""
═══════════════════════════
RETURNING CUSTOMER
═══════════════════════════
- Customer name: {customer_profile.get("last_name") or "unknown"}
- Visit count: {customer_profile.get("visit_count", 1)}
- {appt_last}

GREETING BEHAVIOR FOR RETURNING CUSTOMER:
- If name is known: greet by name — "Welcome back, {customer_profile.get("last_name", "")}! Great to hear from you."
- If last appointment is available: offer rebook — "Last time you booked a {customer_profile.get('last_order', {}).get('service_name', '')} — would you like the same again?"
- If yes: confirm service, proceed to STEP 2 (date/time)
- If no: proceed normally from STEP 1
- NEVER reveal phone number or personal data
═══════════════════════════
"""
    else:
        customer_block = ""

    return f"""You are a friendly, professional phone assistant for {business_name}.
You help callers book {appt_word}s, answer questions, and provide information.

PERSONALITY:
- Speak naturally and warmly — sound like a real receptionist, not a robot
- Keep responses SHORT — 1 sentence wherever possible, 2 maximum
- Never combine acknowledgment + confirmation + question in one response — pick one
- Always start your response with a short word: "Sure!", "Got it!", "Absolutely!", "Perfect!"
- This signals instant response and sounds natural
- Use contractions: "I'll", "we've", "that's" — never "I will" or "that is"
- Match the caller's energy — quick if they're quick, patient if they're unsure

{customer_block}
════════════════════════════════════
GREETING:
When BEGIN_CALL fires, immediately say:
"{disclosure_text}"
If the customer says "hello" or any greeting BEFORE or DURING your greeting,
do NOT restart or repeat yourself. Simply continue the greeting naturally
as if their hello was expected. Never say the greeting twice.
════════════════════════════════════

══════════════════════════
SERVICES OFFERED
══════════════════════════
{services_block}

CRITICAL: Only book services listed above.
- Phone audio is imperfect — if a caller says something that SOUNDS like a service name, assume it's a mishearing and confirm the closest match first.
  Example: "bust cut" = "Buzz Cut" ✅  "clipper cup" = "Clipper Cut" ✅
- NEVER escalate for a mishearing. Always clarify first: "Did you mean a [closest service]?"
- Only escalate if the caller explicitly confirms they want something not on the list after you've clarified.
- If genuinely not offered after clarification: "I'm not sure we offer that — let me connect you with someone who can help."
{availability_block}

══════════════════════════
BOOKING PROTOCOL — FOLLOW IN ORDER
══════════════════════════
STEP 1: Ask what service they need.
  Confirm service and duration: "Got it — a {service_word} for [service], that's [X] minutes."

STEP 2: Ask for preferred date and time.
  "When would you like to come in?"
  If vague: suggest 2 specific times from the AVAILABILITY section above.

  AVAILABILITY CHECKING — TWO PATHS:

  PATH A — Date is listed in the AVAILABILITY section above (pre-loaded):
  - Answer DIRECTLY from the list. Do NOT say "let me check". Do NOT call check_availability.
  - Customer asks for a time that IS in the list → confirm it instantly.
    Example: "3 PM works! What's your name?"
  - Customer asks for a time NOT in the list for that date → redirect instantly.
    Example: "3 PM isn't available, but I have 2 PM and 4 PM open — which works?"
  - Date is fully booked → "We're fully booked that day. The next available day is [next open date from the list]."

  PATH B — Date is NOT in the AVAILABILITY section above:
  - Say "One moment..." then call check_availability with the date and service name.
  - Stay silent until the result returns. Do NOT guess or confirm before the result arrives.
  - If slot available: confirm it. If not: offer nearest available from results.
  - If no slots at all: "Sorry, fully booked that day. Can I check another?"

  After confirming a slot (either path), ask for name in the SAME sentence:
  "[time] works! What's your name?"
  Never split this into two sentences.

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
- When customer says "bye", "goodbye", "hang up", "end the call", "that's all", "nothing else": Say "Thanks for calling {business_name}! Goodbye!" then say CALL_END
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
    extract_booking_from_transcript._last_tokens = 0  # reset each call
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
        
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()
        logger.info(f"Booking extraction raw: {raw[:500]}")
        # Capture token usage for cost tracking
        if hasattr(response, "usage") and response.usage:
            extract_booking_from_transcript._last_tokens = (
                (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)
            )

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
    
    # Send SMS confirmation — deferred until after race check
    # sms_sent will be set below after slot_status is determined
    
    # Save appointment to database
    saved = False
    save_error = None
    if db is not None:
        try:
            import uuid
            from datetime import datetime, timezone

            # ── Race condition check: re-verify slot before saving ────────
            slot_status = "confirmed"
            if preferred_date and preferred_time:
                try:
                    _t = preferred_time.strip().upper()
                    if "AM" in _t or "PM" in _t:
                        _parsed = datetime.strptime(_t, "%I:%M %p")
                    else:
                        _parsed = datetime.strptime(_t, "%H:%M")
                    _slot_key = _parsed.strftime("%H:%M")

                    available_slots = await get_available_slots(
                        restaurant_id=restaurant.get("id", ""),
                        date_str=preferred_date,
                        service_name=service_name,
                        services=services,
                        config=config,
                        db=db,
                    )
                    slot_still_open = any(
                        s["slot_time"] == _slot_key and s["available"]
                        for s in available_slots
                    )
                    if not slot_still_open:
                        slot_status = "conflict"
                        logger.warning(
                            f"Slot conflict detected for {preferred_date} {_slot_key} "
                            f"— saving with status='conflict'"
                        )
                except Exception as _race_err:
                    logger.warning(f"Race check skipped (non-fatal): {_race_err}")

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
                "status": slot_status,
                "calendar_event_id": result.get("calendar_event_id"),
                "special_instructions": booking.get("special_instructions", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None,
            }
            await db.appointments.insert_one(appointment_doc)
            saved = True
            logger.info(f"Appointment saved: {appointment_doc['id']} status={slot_status}")
            result["appointment_id"] = appointment_doc["id"]
            result["slot_conflict"] = slot_status == "conflict"

            # Send SMS only if slot was clean — don't confirm a conflicted booking
            if slot_status == "confirmed" and customer_phone:
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
            elif slot_status == "conflict":
                logger.warning(
                    f"SMS suppressed — slot conflict for "
                    f"{preferred_date} {preferred_time}. "
                    f"Dashboard review required."
                )
                result["sms_sent"] = False

        except Exception as e:
            save_error = str(e)
            logger.error(f"Failed to save appointment to database: {e}")
    else:
        save_error = "no database handle"

    # Success now reflects actual persistence. A booking that was never written to
    # db.appointments is NOT a success — even if calendar/parse steps ran — because
    # the live call already told the caller they were booked. Reporting success here
    # would silently lose the booking (B2-1). Mirrors the restaurant A7-1 fix. The
    # slot-conflict case still persists (status="conflict") and stays a success with
    # slot_conflict=True for dashboard review.
    result["success"] = saved
    if not saved:
        result["error"] = save_error or "appointment was not saved"
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
    
    from telnyx_service import send_sms
    result = await send_sms(
        to=caller_number,
        body=body,
        idempotency_key=f"appointment_confirm:{booking.get('id') or booking.get('appointment_id') or ''}:{preferred_date}:{preferred_time}",
        metadata={
            "purpose": "appointment_confirmation",
            "restaurant_id": booking.get("restaurant_id"),
            "appointment_id": booking.get("id") or booking.get("appointment_id"),
            "service_name": service_name,
        },
    )
    return result.success
