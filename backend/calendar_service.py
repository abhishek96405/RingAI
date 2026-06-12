"""
Google Calendar Integration Service for RingAI Appointment Booking

Handles:
- OAuth 2.0 flow for Google Calendar
- Availability checking (free/busy)
- Event creation for appointments
- Token management with auto-refresh

IMPORTANT: This is NEW code - does NOT modify any existing restaurant functionality.
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import httpx

from encryption_utils import encrypt_calendar_tokens, decrypt_calendar_tokens

logger = logging.getLogger(__name__)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_CALENDAR_REDIRECT_URI", "")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def is_google_calendar_configured() -> bool:
    """Check if Google Calendar OAuth is configured."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_google_auth_url(state: str, redirect_uri: str) -> str:
    """Generate Google OAuth authorization URL.

    `state` is an opaque single-use CSRF token from oauth_state_service,
    echoed back by Google to the callback. It is NOT the restaurant_id.
    """
    if not is_google_calendar_configured():
        raise ValueError("Google Calendar OAuth not configured")

    import urllib.parse

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    base_url = "https://accounts.google.com/o/oauth2/auth"
    return f"{base_url}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    if not is_google_calendar_configured():
        raise ValueError("Google Calendar OAuth not configured")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} {response.text}")
            raise ValueError(f"Token exchange failed: {response.text}")
        
        return response.json()


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """Refresh an expired access token."""
    if not is_google_calendar_configured():
        raise ValueError("Google Calendar OAuth not configured")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_token,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code} {response.text}")
            raise ValueError(f"Token refresh failed: {response.text}")
        
        return response.json()


async def get_valid_access_token(tokens: Dict[str, Any], db, restaurant_id: str) -> str:
    """Get a valid access token, refreshing if necessary."""
    # Tokens are encrypted at rest (B3-7). Decrypt the secret values before use;
    # legacy plaintext tokens pass through decrypt unchanged.
    tokens = decrypt_calendar_tokens(tokens)
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at", 0)
    
    # Check if token is expired (with 5 minute buffer)
    current_time = datetime.now(timezone.utc).timestamp()
    if expires_at and current_time >= (expires_at - 300):
        if not refresh_token:
            raise ValueError("Token expired and no refresh token available")
        
        # Refresh the token
        new_tokens = await refresh_access_token(refresh_token)
        
        # Calculate new expiry
        expires_in = new_tokens.get("expires_in", 3600)
        new_expires_at = current_time + expires_in
        
        # Update stored tokens
        updated_tokens = {
            **tokens,
            "access_token": new_tokens["access_token"],
            "expires_at": new_expires_at,
        }
        
        # Persist to database (re-encrypt the refreshed secret values at rest)
        await db.restaurant_configs.update_one(
            {"restaurant_id": restaurant_id},
            {"$set": {"google_calendar_tokens": encrypt_calendar_tokens(updated_tokens)}}
        )
        
        return new_tokens["access_token"]
    
    return access_token


async def get_calendar_list(access_token: str) -> List[Dict[str, Any]]:
    """Get list of user's calendars."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        
        if response.status_code != 200:
            logger.error(f"Get calendar list failed: {response.status_code} {response.text}")
            raise ValueError(f"Failed to get calendars: {response.text}")
        
        data = response.json()
        return data.get("items", [])


async def get_free_busy(
    access_token: str,
    calendar_id: str,
    start_time: datetime,
    end_time: datetime,
) -> List[Dict[str, str]]:
    """Get free/busy information for a calendar."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "timeMin": start_time.isoformat(),
                "timeMax": end_time.isoformat(),
                "items": [{"id": calendar_id}],
            },
        )
        
        if response.status_code != 200:
            logger.error(f"Get free/busy failed: {response.status_code} {response.text}")
            raise ValueError(f"Failed to get availability: {response.text}")
        
        data = response.json()
        calendars = data.get("calendars", {})
        calendar_data = calendars.get(calendar_id, {})
        return calendar_data.get("busy", [])


async def create_calendar_event(
    access_token: str,
    calendar_id: str,
    summary: str,
    description: str,
    start_time: datetime,
    end_time: datetime,
    attendee_email: Optional[str] = None,
    attendee_phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a calendar event for an appointment."""
    event_body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "UTC",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},  # 1 day before
                {"method": "popup", "minutes": 60},  # 1 hour before
            ],
        },
    }
    
    # Add attendee if email provided
    if attendee_email:
        event_body["attendees"] = [{"email": attendee_email}]
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=event_body,
        )
        
        if response.status_code not in (200, 201):
            logger.error(f"Create event failed: {response.status_code} {response.text}")
            raise ValueError(f"Failed to create event: {response.text}")
        
        return response.json()


async def delete_calendar_event(
    access_token: str,
    calendar_id: str,
    event_id: str,
) -> bool:
    """Delete a calendar event."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.delete(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        
        if response.status_code not in (200, 204):
            logger.error(f"Delete event failed: {response.status_code} {response.text}")
            return False
        
        return True


def calculate_available_slots(
    date: datetime,
    operating_hours: Dict[str, Any],
    service_duration_minutes: int,
    buffer_minutes: int,
    busy_periods: List[Dict[str, str]],
    lead_time_hours: int = 2,
    slot_interval_minutes: int = 30,
) -> List[Dict[str, Any]]:
    """
    Calculate available appointment slots for a given date.
    
    Args:
        date: The date to check availability for
        operating_hours: Business operating hours configuration
        service_duration_minutes: Duration of the service
        buffer_minutes: Buffer time between appointments
        busy_periods: List of busy periods from calendar
        lead_time_hours: Minimum hours before an appointment can be booked
        slot_interval_minutes: Interval between slot start times
    
    Returns:
        List of available time slots with start/end times
    """
    day_name = date.strftime("%A").lower()
    day_hours = operating_hours.get(day_name, {})
    
    if day_hours.get("closed", False):
        return []
    
    open_time_str = day_hours.get("open", "09:00")
    close_time_str = day_hours.get("close", "17:00")
    
    # Parse hours
    try:
        open_hour, open_min = map(int, open_time_str.split(":"))
        close_hour, close_min = map(int, close_time_str.split(":"))
    except (ValueError, AttributeError):
        logger.warning(f"Invalid operating hours format for {day_name}")
        return []
    
    # Create datetime objects for business hours
    business_start = date.replace(hour=open_hour, minute=open_min, second=0, microsecond=0)
    business_end = date.replace(hour=close_hour, minute=close_min, second=0, microsecond=0)
    
    # Apply lead time constraint
    now = datetime.now(timezone.utc)
    earliest_booking = now + timedelta(hours=lead_time_hours)
    if business_start < earliest_booking:
        business_start = earliest_booking
    
    # Parse busy periods
    busy_intervals = []
    for period in busy_periods:
        start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
        busy_intervals.append((start, end))
    
    # Generate slots
    slots = []
    total_duration = service_duration_minutes + buffer_minutes
    current_time = business_start
    
    while current_time + timedelta(minutes=service_duration_minutes) <= business_end:
        slot_end = current_time + timedelta(minutes=service_duration_minutes)
        
        # Check if slot conflicts with any busy period
        is_available = True
        for busy_start, busy_end in busy_intervals:
            if not (slot_end <= busy_start or current_time >= busy_end):
                is_available = False
                break
        
        if is_available:
            slots.append({
                "start": current_time.isoformat(),
                "end": slot_end.isoformat(),
                "display_time": current_time.strftime("%I:%M %p"),
            })
        
        current_time += timedelta(minutes=slot_interval_minutes)
    
    return slots
