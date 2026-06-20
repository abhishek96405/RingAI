"""
Restaurant Reservation System for RingAI

Provides:
- Reservation data model
- Availability checking
- AI extraction from transcripts
- SMS confirmation
- API endpoints helpers

Part of Prompt 1 - Voice-Based Reservation System
"""
import asyncio
import os
import logging
import json
from datetime import datetime, timezone, timedelta
from datetime import datetime, timezone, timedelta, date as _date
from typing import Dict, Any, Optional, List
import re

logger = logging.getLogger(__name__)


# ============================================================
# RESERVATION DATA MODEL
# ============================================================

class ReservationStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    COMPLETED = "completed"


def create_reservation_doc(
    restaurant_id: str,
    customer_name: str,
    customer_phone: str,
    party_size: int,
    reservation_date: str,  # YYYY-MM-DD
    reservation_time: str,  # HH:MM (24h)
    call_id: Optional[str] = None,
    special_requests: Optional[str] = None,
    status: str = ReservationStatus.CONFIRMED,
    customer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a reservation document for MongoDB."""
    import uuid
    return {
        "id": str(uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "call_id": call_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "party_size": party_size,
        "reservation_date": reservation_date,
        "reservation_time": reservation_time,
        "special_requests": special_requests,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "confirmation_sent": False,
        "reminder_sent": False,
    }


# ============================================================
# RESERVATION SETTINGS (per restaurant)
# ============================================================

DEFAULT_RESERVATION_SETTINGS = {
    "reservations_enabled": True,
    "max_party_size": 8,
    "min_party_size": 1,
    "advance_booking_days": 30,  # How far ahead can book
    "slot_duration_minutes": 90,  # How long a table is held
    "slot_interval_minutes": 30,  # Time between available slots
    "capacity_per_slot": 10,  # Max reservations per time slot
    "blackout_dates": [],  # Dates when reservations are disabled
    "special_hours": {},  # Override hours for specific dates
}


def get_reservation_settings(config: Dict[str, Any], restaurant: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get reservation settings from restaurant document and config with defaults."""
    settings = dict(DEFAULT_RESERVATION_SETTINGS)
    # Reservations are opt-in and plan-gated: default OFF unless config or the
    # restaurant doc explicitly turns them on. This aligns the booking path with
    # build_system_prompt, which treats an absent reservations_enabled as False
    # (server.py). The config/restaurant merges below still honor an explicit
    # True or False from either source.
    settings["reservations_enabled"] = False
    # Merge with config values first
    if config:
        for key in settings:
            if key in config:
                settings[key] = config[key]
    # Restaurant document overrides config (restaurant fields are source of truth)
    if restaurant:
        # The dashboard reservations toggle is stored on the restaurant doc
        # (same signal build_system_prompt derives reservations_enabled from).
        # get_reservation_settings previously ignored it, so the disabled-gate
        # in dispatch_reservation couldn't see a restaurant-level "off".
        if "reservations_enabled" in restaurant:
            settings["reservations_enabled"] = restaurant["reservations_enabled"]
        if restaurant.get("reservation_slot_duration"):
            settings["slot_interval_minutes"] = restaurant["reservation_slot_duration"]
        if restaurant.get("reservation_max_per_slot"):
            settings["capacity_per_slot"] = restaurant["reservation_max_per_slot"]
        if restaurant.get("reservation_advance_booking_days"):
            settings["advance_booking_days"] = restaurant["reservation_advance_booking_days"]
        if restaurant.get("reservation_party_limit"):
            settings["max_party_size"] = restaurant["reservation_party_limit"]
    return settings


# ============================================================
# AVAILABILITY CHECKING
# ============================================================

async def get_reservation_slots(
    restaurant_id: str,
    date_str: str,  # YYYY-MM-DD
    config: Dict[str, Any],
    operating_hours: Dict[str, Any],
    db,
    restaurant_timezone: str = "America/Chicago",
    restaurant: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    Get available reservation slots for a date.
    
    Returns list of slots with:
    - time: "HH:MM" (24h format)
    - display_time: "6:00 PM" (formatted)
    - available: bool
    - remaining_capacity: int
    """
    import pytz
    
    settings = get_reservation_settings(config, restaurant)

    if not settings.get("reservations_enabled", True):
        return []
    
    # Check blackout dates
    if date_str in settings.get("blackout_dates", []):
        return []
    
    # Parse date
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.error(f"Invalid date format: {date_str}")
        return []
    
    # Get operating hours for this day
    day_name = target_date.strftime("%A").lower()
    day_hours = operating_hours.get(day_name, {})
    
    # Check special hours override
    if date_str in settings.get("special_hours", {}):
        day_hours = settings["special_hours"][date_str]
    
    if day_hours.get("closed", False):
        return []
    
    # Parse open/close times
    def parse_time(t: str) -> Optional[int]:
        """Convert time string to minutes since midnight."""
        if not t:
            return None
        t = t.strip()
        try:
            parsed = datetime.strptime(t, "%H:%M")
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            try:
                parsed = datetime.strptime(t, "%I:%M %p")
                return parsed.hour * 60 + parsed.minute
            except ValueError:
                return None
    
    open_minutes = parse_time(day_hours.get("open", ""))
    close_minutes = parse_time(day_hours.get("close", ""))

    # Missing/unparseable hours for this day → no slots. Don't fabricate a
    # default window: the old `... or 17*60` silently showed every such day —
    # and every midnight "00:00"/"12:00 AM" open (which parses to 0, a falsy
    # value) — as a 5 PM start. Use explicit None checks and surface gaps.
    if open_minutes is None or close_minutes is None:
        logger.warning(
            f"get_reservation_slots: missing/unparseable hours for {restaurant_id} "
            f"on {date_str} (day={day_name}, open={day_hours.get('open')!r}, "
            f"close={day_hours.get('close')!r}) — returning no slots"
        )
        return []

    # Overnight hours (e.g. 8 AM → 2 AM, or a midnight close): close is at/before
    # open. Cap slot generation at end of day rather than wrapping into the next
    # calendar day (which would make the reservation's date ambiguous). Without
    # this, close <= open yields zero slots.
    if close_minutes <= open_minutes:
        close_minutes = 24 * 60

    # Don't accept reservations within 1 hour of closing
    close_minutes -= 60
    
    # Get existing reservations for this date
    existing = await db.reservations.find({
        "restaurant_id": restaurant_id,
        "reservation_date": date_str,
        "status": {"$in": [ReservationStatus.CONFIRMED, ReservationStatus.PENDING]}
    }, {"_id": 0}).to_list(100)
    # Count reservations per slot
    slot_counts: Dict[str, int] = {}
    for res in existing:
        slot_time = res.get("reservation_time", "")
        slot_counts[slot_time] = slot_counts.get(slot_time, 0) + 1
    # Get blocked slots for this date
    blocked_slot_times = set()
    try:
        blocked_docs = await db.blocked_slots.find({
            "restaurant_id": restaurant_id,
            "date": date_str,
        }, {"_id": 0}).to_list(100)
        for b in blocked_docs:
            blocked_slot_times.add(b.get("time", ""))
    except Exception:
        pass
    # Calculate current time in restaurant timezone for past-slot filtering
    import pytz
    now_minutes = None
    try:
        tz = pytz.timezone(restaurant_timezone)
        local_now = datetime.now(tz)
        local_today = local_now.strftime("%Y-%m-%d")
        if date_str == local_today:
            now_minutes = local_now.hour * 60 + local_now.minute
    except Exception:
        pass
    # Generate slots
    slots = []
    interval = settings.get("slot_interval_minutes", 30)
    capacity = settings.get("capacity_per_slot", 10)
    current = open_minutes
    while current <= close_minutes:
        hour = current // 60
        minute = current % 60
        slot_time = f"{hour:02d}:{minute:02d}"
        # Skip past slots for today
        if now_minutes is not None and current <= now_minutes:
            current += interval
            continue
        # Format for display
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        ampm = "AM" if hour < 12 else "PM"
        display_time = f"{display_hour}:{minute:02d} {ampm}"
        # Check if blocked by owner
        is_blocked = slot_time in blocked_slot_times
        # Check capacity
        booked = slot_counts.get(slot_time, 0)
        remaining = max(0, capacity - booked)
        slots.append({
            "time": slot_time,
            "display_time": display_time,
            "available": not is_blocked and remaining > 0,
            "remaining_capacity": 0 if is_blocked else remaining,
            "total_capacity": capacity,
            "blocked": is_blocked,
        })
        current += interval
    return slots


async def check_reservation_availability(
    restaurant_id: str,
    date_str: str,
    time_str: str,
    party_size: int,
    config: Dict[str, Any],
    operating_hours: Dict[str, Any],
    db,
    restaurant_timezone: str = "America/Chicago",
    restaurant: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Check if a specific reservation slot is available.

    Returns:
        Dict with available: bool, and either confirmation or suggested_times
    """
    settings = get_reservation_settings(config, restaurant)
    
    # Validate party size
    max_party = settings.get("max_party_size", 8)
    if party_size > max_party:
        return {
            "available": False,
            "reason": f"Party size exceeds maximum of {max_party}",
            "max_party_size": max_party
        }
    
    # Get slots for the date
    slots = await get_reservation_slots(
        restaurant_id, date_str, config, operating_hours, db, restaurant_timezone,
        restaurant=restaurant,
    )
    
    if not slots:
        return {
            "available": False,
            "reason": "No reservations available for this date"
        }
    
    # Find the requested slot
    requested_slot = None
    for slot in slots:
        if slot["time"] == time_str:
            requested_slot = slot
            break
    
    if not requested_slot:
        # Find closest available slot
        available_slots = [s for s in slots if s["available"]]
        return {
            "available": False,
            "reason": "Requested time not available",
            "suggested_times": [s["display_time"] for s in available_slots[:5]]
        }
    
    if not requested_slot["available"]:
        # Find nearby available slots
        slot_times = [s["time"] for s in slots]
        try:
            idx = slot_times.index(time_str)
            nearby = []
            # Check slots before and after
            for offset in [-2, -1, 1, 2]:
                check_idx = idx + offset
                if 0 <= check_idx < len(slots) and slots[check_idx]["available"]:
                    nearby.append(slots[check_idx]["display_time"])
            
            return {
                "available": False,
                "reason": "This time slot is fully booked",
                "suggested_times": nearby[:3]
            }
        except ValueError:
            pass
        
        return {
            "available": False,
            "reason": "This time slot is fully booked"
        }
    
    return {
        "available": True,
        "slot": requested_slot,
        "party_size": party_size
    }


# ============================================================
# AI EXTRACTION FROM TRANSCRIPT
# ============================================================

async def extract_reservation_from_transcript(
    transcript: List[Dict],
    menu_index,  # Not used for reservations but kept for API consistency
) -> Optional[Dict[str, Any]]:
    """
    Extract reservation details from call transcript using AI.
    
    Returns:
        Dict with reservation details or None if no reservation detected
    """
    from gemini_service import _get_client, _repair_json
    
    client = _get_client()
    if not client:
        return None
    
    # Build transcript text
    transcript_text = "\n".join(
        f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e.get('text', '')}"
        for e in transcript
    )
    
    # Check for reservation signals
    reservation_keywords = [
        "reservation", "book a table", "table for", "party of",
        "book for", "make a reservation", "reserve"
    ]
    
    has_reservation_signal = any(
        kw in transcript_text.lower() for kw in reservation_keywords
    )
    
    if not has_reservation_signal:
        return None
    
    prompt = f"""Extract restaurant reservation details from this call transcript.
Return ONLY valid JSON, no markdown, no code blocks.

Required JSON format:
{{"reservation_confirmed":true,"customer_name":"John Smith","party_size":4,"date":"2025-01-20","time":"6:30 PM","special_requests":"window seat"}}

RULES:
- reservation_confirmed: true only if the AI explicitly confirmed the booking
- customer_name: exactly as spoken (romanize if in another script)
- party_size: integer number of guests
- date: YYYY-MM-DD format. Convert relative dates using today's date (today is {datetime.now().strftime("%Y-%m-%d")}). "28th" means the 28th of the current month.
- time: use 12-hour format with AM/PM (e.g. "4:30 PM", "7:00 PM")
- special_requests: any special requests mentioned, or empty string if none

If no confirmed reservation found, return: {{"reservation_confirmed":false}}

TRANSCRIPT:
{transcript_text[:4000]}
JSON:"""

    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content.strip()
        logger.info(f"Reservation extraction raw response: {raw}")
        
        data = json.loads(_repair_json(raw))
        
        if not data.get("reservation_confirmed"):
            return None
        
        return {
            "customer_name": data.get("customer_name", ""),
            "party_size": int(data.get("party_size", 2)),
            "reservation_date": data.get("date", ""),
            "reservation_time": data.get("time", ""),
            "special_requests": data.get("special_requests") or "",
        }
        
    except Exception as e:
        logger.error(f"Reservation extraction error: {e}")
        return None


# ============================================================
# RESERVATION DISPATCH (CREATE + SMS)
# ============================================================

def _normalize_time_to_24h(time_str: str) -> str:
    """Normalize a reservation time to 24-hour "HH:MM".

    extract_reservation_from_transcript returns 12-hour times ("6:30 PM"),
    but get_reservation_slots / check_reservation_availability work in 24h
    "HH:MM" — and capacity counting in get_reservation_slots only matches
    reservations STORED in 24h. Normalizing here keeps the availability
    re-check, storage, and capacity counting consistent. Already-24h values
    and unparseable strings are returned unchanged.
    """
    if not time_str:
        return time_str
    t = time_str.strip()
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            return datetime.strptime(t, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return t


def _format_time_12h(time_24h: str) -> str:
    """Format a 24h "HH:MM" time as "7:00 PM" (no leading zero, cross-platform)."""
    try:
        return datetime.strptime(time_24h, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return time_24h


async def dispatch_reservation(
    reservation_data: Dict[str, Any],
    restaurant: Dict[str, Any],
    config: Dict[str, Any],
    db,
) -> Dict[str, Any]:
    """
    Create reservation in database and send SMS confirmation.

    Before creating, re-checks live DB availability so a confirmed-but-
    unavailable slot (capacity filled between the live call and this dispatch,
    or a hallucinated slot) never becomes a real booking. If the slot is no
    longer available, sends an apology SMS naming open alternatives and
    returns {"success": False, ...} WITHOUT creating a reservation.

    Returns:
        Dict with success status, reservation_id, sms_sent (on success), or
        {"success": False, "reason": ..., "suggested_times": [...]} when the
        availability gate blocks the booking.
    """
    restaurant_id = restaurant.get("id", "")
    config = config or {}

    # Hard gate: reservations disabled for this restaurant → never book.
    # Clean no-op (no SMS): the availability path below can otherwise fire a
    # confusing "couldn't confirm your table" apology when the real reason is
    # that the venue doesn't take reservations at all.
    settings = get_reservation_settings(config, restaurant)
    if not settings.get("reservations_enabled", True):
        logger.warning(
            f"dispatch_reservation blocked — reservations disabled for {restaurant_id}"
        )
        return {"success": False, "reason": "reservations_disabled"}

    # Normalize the requested time to 24h "HH:MM" so the availability re-check
    # below matches the slot grid, and so the reservation is STORED in 24h for
    # correct future capacity counting in get_reservation_slots.
    reservation_date = reservation_data.get("reservation_date", "")
    reservation_time_24h = _normalize_time_to_24h(reservation_data.get("reservation_time", ""))
    party_size = reservation_data.get("party_size", 2)

    # ── Live availability gate ─────────────────────────────────────────────
    operating_hours = config.get("operating_hours", {}) or {}
    restaurant_timezone = restaurant.get("timezone", "America/Chicago")
    availability = await check_reservation_availability(
        restaurant_id=restaurant_id,
        date_str=reservation_date,
        time_str=reservation_time_24h,
        party_size=party_size,
        config=config,
        operating_hours=operating_hours,
        db=db,
        restaurant_timezone=restaurant_timezone,
        restaurant=restaurant,
    )

    if not availability.get("available"):
        suggested_times = availability.get("suggested_times", []) or []
        reason = availability.get("reason", "Requested time is no longer available")
        logger.warning(
            f"Reservation availability gate blocked booking "
            f"({restaurant_id} {reservation_date} {reservation_time_24h} "
            f"party={party_size}): {reason}"
        )
        # NOTE: the customer-facing "couldn't confirm your table" SMS is NOT sent
        # here. It's sent once at end-of-call by the session
        # (CallSession._notify_reservation_unavailable_if_pending), after every
        # booking attempt — so a reservation that books on a later retry never
        # also gets an apology, and a persistently unavailable one is apologized
        # for exactly once.
        return {
            "success": False,
            "reason": reason,
            "suggested_times": suggested_times,
            "reservation_date": reservation_date,
            "reservation_time": reservation_time_24h,
        }

    # Create reservation document (store time in 24h for capacity counting)
    doc = create_reservation_doc(
        restaurant_id=restaurant_id,
        customer_name=reservation_data.get("customer_name", "Guest"),
        customer_phone=reservation_data.get("customer_phone", ""),
        party_size=party_size,
        reservation_date=reservation_date,
        reservation_time=reservation_time_24h,
        call_id=reservation_data.get("call_id"),
        special_requests=reservation_data.get("special_requests"),
    )

    # Save to database
    await db.reservations.insert_one(doc)
    
    result = {
        "success": True,
        "reservation_id": doc["id"],
        "sms_sent": False,
    }
    
    # Send SMS confirmation if enabled
    if config.get("sms_enabled", True) and doc["customer_phone"]:
        try:
            sms_sent = await send_reservation_sms(
                customer_phone=doc["customer_phone"],
                customer_name=doc["customer_name"],
                restaurant_name=restaurant.get("name", "the restaurant"),
                party_size=doc["party_size"],
                reservation_date=doc["reservation_date"],
                reservation_time=doc["reservation_time"],
                restaurant_address=restaurant.get("address", ""),
            )
            result["sms_sent"] = sms_sent
            
            if sms_sent:
                await db.reservations.update_one(
                    {"id": doc["id"]},
                    {"$set": {"confirmation_sent": True}}
                )
        except Exception as e:
            logger.error(f"Reservation SMS error: {e}")
    
    return result


async def send_reservation_sms(
    customer_phone: str,
    customer_name: str,
    restaurant_name: str,
    party_size: int,
    reservation_date: str,
    reservation_time: str,
    restaurant_address: str = "",
) -> bool:
    """Send reservation confirmation SMS via Telnyx."""
    # Format date for display
    try:
        date_obj = datetime.strptime(reservation_date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%A, %B %d")
    except ValueError:
        formatted_date = reservation_date
    
    # Format time for display
    try:
        time_obj = datetime.strptime(reservation_time, "%H:%M")
        formatted_time = time_obj.strftime("%I:%M %p")
    except ValueError:
        formatted_time = reservation_time
    
    # Build message
    message = (
        f"Hi {customer_name}! Your reservation at {restaurant_name} is confirmed.\n\n"
        f"Party of {party_size}\n"
        f"{formatted_date} at {formatted_time}\n"
    )
    
    if restaurant_address:
        message += f"\n{restaurant_address}"
    
    message += "\n\nReply CANCEL to cancel your reservation."
    
    from telnyx_service import send_sms
    result = await send_sms(
        to=customer_phone,
        body=message,
        idempotency_key=f"reservation_confirm:{customer_phone}:{reservation_date}:{reservation_time}",
        metadata={
            "purpose": "reservation_confirmation",
            "restaurant_name": restaurant_name,
            "party_size": party_size,
            "reservation_date": reservation_date,
            "reservation_time": reservation_time,
        },
    )
    return result.success


async def send_reservation_unavailable_sms(
    customer_phone: str,
    restaurant_name: str,
    reservation_date: str,  # YYYY-MM-DD
    reservation_time: str,  # HH:MM (24h)
    suggested_times: List[str],
) -> bool:
    """Send an apology SMS when a requested reservation slot can't be confirmed.

    Names the open alternatives so the customer can pick another time. The copy
    never references "AI" — it reads as a normal "that time just filled up" note.
    """
    # Format requested date/time for display
    try:
        date_obj = datetime.strptime(reservation_date, "%Y-%m-%d")
        day_label = date_obj.strftime("%a")
    except ValueError:
        day_label = ""
    time_label = _format_time_12h(reservation_time)
    when = f"{day_label} {time_label}".strip()

    message = f"Sorry, we couldn't confirm your table at {restaurant_name}"
    if when:
        message += f" for {when}"
    message += "."
    if suggested_times:
        message += f" Next open times: {', '.join(suggested_times)}."
    message += " Reply or call to lock one in."

    from telnyx_service import send_sms
    result = await send_sms(
        to=customer_phone,
        body=message,
        idempotency_key=f"reservation_unavailable:{customer_phone}:{reservation_date}:{reservation_time}",
        metadata={
            "purpose": "reservation_unavailable",
            "restaurant_name": restaurant_name,
            "reservation_date": reservation_date,
            "reservation_time": reservation_time,
        },
    )
    return result.success


# ============================================================
# SYSTEM PROMPT ADDITIONS FOR RESERVATIONS
# ============================================================

def build_reservation_prompt_block(
    settings: Dict[str, Any],
    available_slots: List[Dict[str, Any]],
    restaurant_timezone: str = "America/Chicago"
) -> str:
    """
    Build the reservation-specific block for the AI system prompt.
    """
    if not settings.get("reservations_enabled", False):
        return ""
    
    max_party = settings.get("max_party_size", 8)
    advance_days = settings.get("advance_booking_days", 30)
    
    # Format available slots for today
    today_slots = ", ".join(s["display_time"] for s in available_slots if s["available"])[:200]
    
    return f"""
═══════════════════════════
RESERVATION SYSTEM
═══════════════════════════
This restaurant accepts table reservations.

RESERVATION RULES:
- Maximum party size: {max_party} guests
- Can book up to {advance_days} days in advance
- Reservation duration: {settings.get('slot_duration_minutes', 90)} minutes

AVAILABLE SLOTS TODAY: {today_slots or "None available today"}

RESERVATION FLOW:
1. When customer asks for a reservation, gather:
   - Party size (how many guests?)
   - Preferred date
   - Preferred time
   
2. Check availability against the slots listed above
   - If not available, suggest nearby times
   
3. Collect customer name (required)

4. Confirm the reservation:
   "Perfect! I have a table for [party_size] on [date] at [time] under [name]. 
    We'll send you a confirmation text. Is there anything else I can help with?"

5. Signal completion with: RESERVATION_CONFIRMED

IMPORTANT:
- Never confirm a time that's not in the available slots
- If party size exceeds {max_party}, politely say you can accommodate up to {max_party} and suggest calling for larger parties
- Always repeat the full details before confirming
"""