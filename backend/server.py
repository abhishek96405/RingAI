from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import math
import logging
import signal
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Set
from bson import ObjectId
import uuid
import random
from datetime import datetime, timezone, timedelta
import stripe
from twilio.rest import Client as TwilioClient

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


# ============================================================
# GRACEFUL SHUTDOWN
# ============================================================
_active_websockets: Set[WebSocket] = set()
_shutdown_requested = False

def register_active_websocket(ws: WebSocket):
    _active_websockets.add(ws)

def unregister_active_websocket(ws: WebSocket):
    _active_websockets.discard(ws)

def is_shutdown_requested() -> bool:
    return _shutdown_requested

async def graceful_shutdown_handler(sig, frame):
    global _shutdown_requested
    logger = logging.getLogger(__name__)
    if _shutdown_requested:
        return
    _shutdown_requested = True
    active_count = len(_active_websockets)
    logger.info(f"🛑 Graceful shutdown initiated (signal: {sig})")
    logger.info(f"📞 Active calls: {active_count}")
    if active_count == 0:
        logger.info("✅ No active calls — shutting down immediately")
        return
    logger.info(f"⏳ Waiting up to 600s for {active_count} active call(s) to complete...")
    start_time = asyncio.get_event_loop().time()
    while len(_active_websockets) > 0:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > 600:
            logger.warning(f"⚠️ Timeout — forcibly closing {len(_active_websockets)} call(s)")
            break
        await asyncio.sleep(1)
        if int(elapsed) % 30 == 0:
            logger.info(f"⏳ Still waiting... {len(_active_websockets)} call(s) active")
    logger.info("✅ Graceful shutdown complete")

def setup_signal_handlers():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(graceful_shutdown_handler(s, None))
        )
    logging.getLogger(__name__).info("✅ Graceful shutdown handlers registered")


def serialize_mongo_doc(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [serialize_mongo_doc(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_mongo_doc(v) for k, v in value.items()}
    return value


def demo_mode_enabled() -> bool:
    return os.environ.get("ENABLE_DEMO_MODE", "false").lower() == "true"


def _normalize_origin(origin: str) -> str:
    return origin.strip().strip('"').strip("'").rstrip("/")


def get_cors_origins() -> List[str]:
    defaults = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    }

    configured = set()

    raw_cors = os.environ.get("CORS_ORIGINS", "")
    if raw_cors:
        for origin in raw_cors.split(","):
            normalized = _normalize_origin(origin)
            if normalized:
                configured.add(normalized)

    frontend_url = os.environ.get("FRONTEND_URL", "")
    if frontend_url:
        normalized = _normalize_origin(frontend_url)
        if normalized:
            configured.add(normalized)

    all_origins = defaults | configured
    return sorted(all_origins)


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get("DB_NAME", "ringai_db")]

def get_business_collection(business_type: str):
    """Route to the correct business collection based on business_type."""
    return {
        "restaurant": db.restaurants,
        "clinic": db.clinics,
        "salon": db.salons,
        "home_services": db.home_services,
        "legal": db.legal,
    }.get(business_type, db.restaurants)

def get_config_collection(business_type: str):
    """Route to the correct config collection based on business_type."""
    return {
        "restaurant": db.restaurant_configs,
        "clinic": db.clinic_configs,
        "salon": db.salon_configs,
        "home_services": db.home_service_configs,
        "legal": db.legal_configs,
    }.get(business_type, db.restaurant_configs)

# Gemini + Pipeline imports
from gemini_service import (
    is_gemini_available,
    parse_menu_text,
    analyse_call_transcript,
    get_conversation_response,
    build_system_prompt,
    send_order_sms,
    send_menu_sms,
)
from call_pipeline import (
    is_pipeline_available,
    create_call_pipeline,
    generate_twiml_stream_response,
    provision_phone_number,
    validate_twilio_request,
    CallSession,
)

from auth_helpers import verify_clerk_token

from test_mode import (
    get_test_mode_status,
    get_test_scenarios,
    get_scenario_by_id,
    is_sandbox_mode,
    SAMPLE_CUSTOMER_SCENARIOS,
)

# Create the main app
app = FastAPI(title="RingAI API", version="1.0.0")
api_router = APIRouter(prefix="/api")

@app.on_event("startup")
async def migrate_businesses_to_typed_collections():
    """
    One-time migration: move documents from db.restaurants to the correct
    typed collection based on their business_type field.
    Idempotent — safe to run on every startup.
    """
    try:
        all_docs = await db.restaurants.find(
            {"business_type": {"$in": ["clinic", "salon", "home_services", "legal"]}},
            {"_id": 0}
        ).to_list(1000)
        
        if not all_docs:
            return
            
        logger.info(f"[Migration] Found {len(all_docs)} non-restaurant businesses to migrate")
        
        for doc in all_docs:
            business_type = doc.get("business_type")
            target_coll = get_business_collection(business_type)
            existing = await target_coll.find_one({"id": doc["id"]}, {"_id": 0})
            if not existing:
                await target_coll.insert_one(doc)
                logger.info(f"[Migration] Moved {doc.get('name')} ({doc['id']}) → {business_type}")
            await db.restaurants.delete_one({"id": doc["id"]})
        
        logger.info("[Migration] Business collection migration complete")
    except Exception as e:
        logger.error(f"[Migration] Error during migration: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def get_twilio_client():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise HTTPException(status_code=400, detail="Twilio credentials are not configured")
    return TwilioClient(sid, token)


def get_backend_public_url() -> str:
    return os.environ.get("BACKEND_PUBLIC_URL", "http://localhost:8001").rstrip("/")


def get_frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:8080").rstrip("/")


async def auto_detect_timezone(address: str) -> Optional[str]:
    """Auto-detect timezone from address using Google Maps Geocoding + Timezone API."""
    maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not maps_key or not address:
        return None
    try:
        import httpx
        import time

        # Step 1: Geocode address to lat/lng
        async with httpx.AsyncClient(timeout=5.0) as client:
            geo_res = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": maps_key}
            )
            geo_data = geo_res.json()

        if not geo_data.get("results"):
            logger.warning(f"Geocoding failed for address: {address}")
            return None

        location = geo_data["results"][0]["geometry"]["location"]
        lat, lng = location["lat"], location["lng"]

        # Step 2: Get timezone from coordinates
        async with httpx.AsyncClient(timeout=5.0) as client:
            tz_res = await client.get(
                "https://maps.googleapis.com/maps/api/timezone/json",
                params={
                    "location": f"{lat},{lng}",
                    "timestamp": int(time.time()),
                    "key": maps_key,
                }
            )
            tz_data = tz_res.json()

        tz = tz_data.get("timeZoneId")
        if tz:
            logger.info(f"Auto-detected timezone: {tz} for address: {address}")
        return tz
    except Exception as e:
        logger.warning(f"Could not auto-detect timezone for '{address}': {e}")
        return None


# ============================================================
# PYDANTIC MODELS
# ============================================================

class RestaurantBase(BaseModel):
    name: str
    cuisine_type: Optional[str] = None

    # owner / business contact
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None
    billing_email: Optional[str] = None
    business_phone: Optional[str] = None
    website: Optional[str] = None

    # location
    phone_number: Optional[str] = None
    timezone: str = "America/Chicago"
    address: Optional[str] = None
    primary_language: str = "en"

    # operations
    pickup_enabled: bool = True
    delivery_enabled: bool = True
    dine_in_enabled: bool = True
    reservations_enabled: bool = False
    catering_enabled: bool = False
    avg_prep_time_minutes: int = 20
    reservation_party_limit: int = 8

    # lifecycle
    status: str = "draft"
    onboarding_step: int = 1


class RestaurantCreate(RestaurantBase):
    pass


class RestaurantUpdate(BaseModel):
    name: Optional[str] = None
    cuisine_type: Optional[str] = None

    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None
    billing_email: Optional[str] = None
    business_phone: Optional[str] = None
    website: Optional[str] = None

    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    address: Optional[str] = None
    primary_language: Optional[str] = None

    pickup_enabled: Optional[bool] = None
    delivery_enabled: Optional[bool] = None
    dine_in_enabled: Optional[bool] = None
    reservations_enabled: Optional[bool] = None
    catering_enabled: Optional[bool] = None
    avg_prep_time_minutes: Optional[int] = None
    reservation_party_limit: Optional[int] = None

    status: Optional[str] = None
    onboarding_step: Optional[int] = None
    is_active: Optional[bool] = None

    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_status: Optional[str] = None
    twilio_number_sid: Optional[str] = None
    square_connected: Optional[bool] = None
    onboarding_completed_at: Optional[str] = None


class Restaurant(RestaurantBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_active: bool = False
    plan: str = "STARTER"
    monthly_call_count: int = 0

    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_status: str = "not_started"
    twilio_number_sid: Optional[str] = None
    square_connected: bool = False

    onboarding_completed_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UserProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Membership(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    restaurant_id: str
    role: str = "owner"
    business_type: str = "restaurant"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RestaurantSelection(BaseModel):
    restaurant_id: str


class BillingCheckoutRequest(BaseModel):
    restaurant_id: str
    price_id: Optional[str] = None


class TwilioProvisionRequest(BaseModel):
    restaurant_id: str
    area_code: Optional[str] = None


class TwilioAssignNumberRequest(BaseModel):
    restaurant_id: str
    phone_number: str


class BootstrapResponse(BaseModel):
    user: Dict[str, Any]
    memberships: List[Dict[str, Any]]
    restaurants: List[Dict[str, Any]]
    active_restaurant: Optional[Dict[str, Any]] = None
    onboarding_complete: bool = False


class RestaurantConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str

    # Business type for horizontal platform support
    # "restaurant" | "clinic" | "salon" | "home_services" | "legal"
    business_type: str = "restaurant"

    persona: str = "friendly"
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    primary_language: str = "en"

    business_rules: List[str] = []
    few_shot_examples: List[Dict] = []
    escalation_rules: List[str] = []

    upsell_enabled: bool = True
    disclosure_text: str = "Hi! I'm an AI assistant. How can I help you today?"
    delivery_enabled: bool = True
    delivery_minimum: int = 1500

    after_hours_mode: str = "voicemail"
    voicemail_enabled: bool = True
    escalation_phone_number: Optional[str] = None
    sms_enabled: bool = True
    sms_payment_enabled: bool = False
    operating_hours: Dict[str, Any] = {
        "monday": {"closed": False, "open": "09:00", "close": "21:00"},
        "tuesday": {"closed": False, "open": "09:00", "close": "21:00"},
        "wednesday": {"closed": False, "open": "09:00", "close": "21:00"},
        "thursday": {"closed": False, "open": "09:00", "close": "21:00"},
        "friday": {"closed": False, "open": "09:00", "close": "22:00"},
        "saturday": {"closed": False, "open": "09:00", "close": "22:00"},
        "sunday": {"closed": False, "open": "09:00", "close": "20:00"},
    }


    # Google Calendar integration for appointment businesses
    google_calendar_tokens: Optional[Dict[str, Any]] = None
    google_calendar_id: Optional[str] = None

    # Slot scheduling config (appointment businesses)
    slot_capacity: int = 1            # max concurrent bookings per slot
    slot_interval_minutes: int = 30   # minutes between slot start times


class RestaurantConfigUpdate(BaseModel):
    business_type: Optional[str] = None

    persona: Optional[str] = None
    voice_id: Optional[str] = None
    primary_language: Optional[str] = None

    business_rules: Optional[List[str]] = None
    escalation_rules: Optional[List[str]] = None
    sms_enabled: Optional[bool] = None
    sms_payment_enabled: Optional[bool] = None

    upsell_enabled: Optional[bool] = None
    disclosure_text: Optional[str] = None
    delivery_enabled: Optional[bool] = None
    delivery_minimum: Optional[int] = None

    after_hours_mode: Optional[str] = None
    voicemail_enabled: Optional[bool] = None
    escalation_phone_number: Optional[str] = None
    operating_hours: Optional[Dict[str, Any]] = None

    google_calendar_tokens: Optional[Dict[str, Any]] = None
    google_calendar_id: Optional[str] = None

    slot_capacity: Optional[int] = None
    slot_interval_minutes: Optional[int] = None


# ============================================================
# MODIFIER MODELS (restaurant-level reusable modifier library)
# ============================================================

class ModifierOption(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    price_delta: int = 0          # cents, can be negative
    default_selected: bool = False
    in_stock: bool = True
    display_order: int = 0
    ai_aliases: List[str] = []    # e.g. ["medium", "regular"] for "Medium"

class ModifierGroupBase(BaseModel):
    name: str
    selection_type: str = "single"  # "single" or "multiple"
    required: bool = False
    min_selections: int = 0
    max_selections: int = 1
    display_order: int = 0
    active: bool = True
    options: List[ModifierOption] = []

class ModifierGroupCreate(ModifierGroupBase):
    pass

class ModifierGroupUpdate(BaseModel):
    name: Optional[str] = None
    selection_type: Optional[str] = None
    required: Optional[bool] = None
    min_selections: Optional[int] = None
    max_selections: Optional[int] = None
    display_order: Optional[int] = None
    active: Optional[bool] = None
    options: Optional[List[ModifierOption]] = None

class ModifierGroup(ModifierGroupBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MenuItemModifierAssignment(BaseModel):
    modifier_group_id: str
    override_required: Optional[bool] = None
    override_min: Optional[int] = None
    override_max: Optional[int] = None
    override_name: Optional[str] = None
    display_order: int = 0

# Legacy — kept for backward compatibility
class MenuItemModifier(BaseModel):
    name: str
    required: bool = False
    options: List[Dict[str, Any]] = []


class MenuItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    price: int  # cents
    available: bool = True
    modifiers: List[MenuItemModifier] = []          # legacy
    modifier_group_assignments: List[MenuItemModifierAssignment] = []  # new
    allergens: List[str] = []
    image_url: Optional[str] = None
    special_instructions_enabled: bool = True


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[int] = None
    available: Optional[bool] = None
    modifiers: Optional[List[MenuItemModifier]] = None
    modifier_group_assignments: Optional[List[MenuItemModifierAssignment]] = None
    allergens: Optional[List[str]] = None
    special_instructions_enabled: Optional[bool] = None


class MenuItem(MenuItemBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    pos_item_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TranscriptEntry(BaseModel):
    role: str  # "customer" or "ai"
    text: str
    timestamp: str


class CallRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    twilio_call_sid: str = Field(default_factory=lambda: f"CA{uuid.uuid4().hex[:32]}")
    caller_number: str
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str = "COMPLETED"  # IN_PROGRESS, COMPLETED, FAILED, ESCALATED
    contained_by_ai: bool = True
    escalated_to_human: bool = False
    transcript: List[Dict] = []
    order_json: Optional[Dict] = None
    pos_order_id: Optional[str] = None
    quality_score: Optional[int] = None
    analysis_json: Optional[Dict] = None
    claude_tokens_used: int = 0
    caller_name: Optional[str] = None
    order_total: Optional[int] = None  # cents

    # ── Internal cost tracking (admin only — never exposed to business owners) ──
    cost_twilio_voice_cents: Optional[float] = None   # $0.0085/min inbound
    cost_twilio_sms_cents: Optional[float] = None     # $0.0083/message
    cost_gemini_live_cents: Optional[float] = None    # $0 now (free preview), track duration for future
    cost_gemini_extract_cents: Optional[float] = None # $0.075/1M input + $0.30/1M output
    cost_gemini_tts_cents: Optional[float] = None     # voice preview calls
    cost_total_cents: Optional[float] = None          # sum of all above
    gemini_extract_tokens: Optional[int] = None       # input + output tokens from extraction
    twilio_sms_count: int = 0                         # number of SMS sent this call
    duration_seconds_twilio: Optional[int] = None     # exact from Twilio status callback


class CallAnalysis(BaseModel):
    quality_score: int
    order_accuracy: str
    issues: List[str]
    highlights: List[str]
    menu_suggestions: List[str]
    rule_suggestions: List[str]
    summary: str


class DashboardSummary(BaseModel):
    total_calls: int
    completed_calls: int
    escalated_calls: int
    avg_quality_score: float
    total_revenue: int  # cents
    avg_duration: float
    ai_containment_rate: float
    calls_today: int
    calls_this_week: int
    revenue_this_week: int
    daily_call_data: List[Dict]
    hourly_distribution: List[Dict]
    top_items: List[Dict]
    recent_calls: List[Dict]


class OnboardingMenuParse(BaseModel):
    menu_text: str
    restaurant_id: str


class OnboardingActivate(BaseModel):
    restaurant_id: str


# ============================================================
# SERVICE ITEM MODEL (for appointment businesses)
# ============================================================

class ServiceItemBase(BaseModel):
    name: str
    duration_minutes: int
    buffer_minutes: int = 15
    price_cents: Optional[int] = None
    description: Optional[str] = None
    available: bool = True


class ServiceItemCreate(ServiceItemBase):
    pass


class ServiceItemUpdate(BaseModel):
    name: Optional[str] = None
    duration_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None
    price_cents: Optional[int] = None
    description: Optional[str] = None
    available: Optional[bool] = None


class ServiceItem(ServiceItemBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================
# APPOINTMENT/BOOKING MODEL (for appointment businesses)
# ============================================================

class AppointmentRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    call_id: Optional[str] = None

    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None

    service_name: str
    service_id: Optional[str] = None
    scheduled_date: str
    scheduled_time: str
    duration_minutes: int = 60

    status: str = "confirmed"
    calendar_event_id: Optional[str] = None

    special_instructions: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None


# ============================================================
# AUTH / TENANCY HELPERS
# ============================================================

class BlockSlotRequest(BaseModel):
    date: str         # "YYYY-MM-DD"
    slot_time: str    # "HH:MM" 24h local time
    reason: str = "walk-in / manual block"


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = await verify_clerk_token(token)
    except Exception as exc:
        logger.exception("Failed to verify Clerk token")
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    email = None
    emails = claims.get("email_addresses") or claims.get("email")
    if isinstance(emails, list) and emails:
        first = emails[0]
        email = first.get("email_address") if isinstance(first, dict) else str(first)
    elif isinstance(emails, str):
        email = emails

    user_doc = {
        "id": user_id,
        "email": email,
        "first_name": claims.get("given_name") or claims.get("first_name"),
        "last_name": claims.get("family_name") or claims.get("last_name"),
        "image_url": claims.get("picture") or claims.get("image_url"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = await db.users.find_one({"id": user_id}, {"_id": 0})
    if existing:
        await db.users.update_one({"id": user_id}, {"$set": user_doc})
        return {**existing, **user_doc}

    new_user = UserProfile(**user_doc).model_dump()
    await db.users.insert_one(new_user)
    return new_user


async def ensure_restaurant_access(restaurant_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    if not membership:
        raise HTTPException(status_code=403, detail="You do not have access to this restaurant")
    business_type = membership.get("business_type", "restaurant")
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant


async def get_bootstrap_payload(user: Dict[str, Any], preferred_restaurant_id: Optional[str] = None) -> Dict[str, Any]:
    memberships = await db.memberships.find({"user_id": user["id"]}, {"_id": 0}).to_list(100)
    restaurant_ids = [m["restaurant_id"] for m in memberships]
    restaurants = []
    if restaurant_ids:
        # Query all business collections in parallel
        import asyncio as _asyncio
        results = await _asyncio.gather(
            db.restaurants.find({"id": {"$in": restaurant_ids}}, {"_id": 0}).to_list(100),
            db.clinics.find({"id": {"$in": restaurant_ids}}, {"_id": 0}).to_list(100),
            db.salons.find({"id": {"$in": restaurant_ids}}, {"_id": 0}).to_list(100),
            db.home_services.find({"id": {"$in": restaurant_ids}}, {"_id": 0}).to_list(100),
            db.legal.find({"id": {"$in": restaurant_ids}}, {"_id": 0}).to_list(100),
        )
        for r in results:
            restaurants.extend(r)

    active_restaurant = None
    if restaurants:
        active_restaurant = next((r for r in restaurants if r["id"] == preferred_restaurant_id), restaurants[0])

    payload = BootstrapResponse(
        user=serialize_mongo_doc(user),
        memberships=serialize_mongo_doc(memberships),
        restaurants=serialize_mongo_doc(restaurants),
        active_restaurant=serialize_mongo_doc(active_restaurant),
        onboarding_complete=bool(active_restaurant and active_restaurant.get("is_active")),
    ).model_dump()

    return serialize_mongo_doc(payload)


# ============================================================
# ROOT ENDPOINT
# ============================================================

@api_router.get("/")
async def root():
    return {"message": "RingAI API v1.0", "status": "operational"}


# ============================================================
# SESSION / BOOTSTRAP ENDPOINTS
# ============================================================

@api_router.get("/me/bootstrap")
async def me_bootstrap(
    restaurant_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(get_current_user)
):
    payload = await get_bootstrap_payload(user, restaurant_id)
    return payload


@api_router.post("/me/repair-membership")
async def repair_membership(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Dev/fix endpoint: finds any restaurant where the user is NOT yet a member
    and auto-creates an owner membership. Safe to call multiple times.
    """
    import asyncio as _asyncio
    all_results = await _asyncio.gather(
        db.restaurants.find({}, {"_id": 0}).to_list(100),
        db.clinics.find({}, {"_id": 0}).to_list(100),
        db.salons.find({}, {"_id": 0}).to_list(100),
        db.home_services.find({}, {"_id": 0}).to_list(100),
        db.legal.find({}, {"_id": 0}).to_list(100),
    )
    all_restaurants = [r for results in all_results for r in results]
    repaired = []
    for restaurant in all_restaurants:
        rid = restaurant.get("id")
        if not rid:
            continue
        existing = await db.memberships.find_one({"user_id": user["id"], "restaurant_id": rid})
        if not existing:
            membership = Membership(user_id=user["id"], restaurant_id=rid, role="owner")
            await db.memberships.insert_one(membership.model_dump())
            repaired.append(rid)
    return {"repaired": repaired, "message": f"Created {len(repaired)} membership(s)"}



async def select_restaurant(data: RestaurantSelection, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant = await ensure_restaurant_access(data.restaurant_id, user)
    return {"active_restaurant": restaurant}


# ============================================================
# RESTAURANT ENDPOINTS
# ============================================================

@api_router.post("/restaurants", response_model=Restaurant)
async def create_restaurant(data: RestaurantCreate, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant_data = data.model_dump()

    # Auto-detect timezone from address if not explicitly set
    if restaurant_data.get("address") and restaurant_data.get("timezone") == "America/Chicago":
        detected_tz = await auto_detect_timezone(restaurant_data["address"])
        if detected_tz:
            restaurant_data["timezone"] = detected_tz

    restaurant = Restaurant(**restaurant_data)
    doc = restaurant.model_dump()
    business_type = doc.get("business_type", "restaurant")
    await get_business_collection(business_type).insert_one(doc)
    membership = Membership(user_id=user["id"], restaurant_id=restaurant.id, role="owner", business_type=business_type)
    await db.memberships.insert_one(membership.model_dump())
    return restaurant


@api_router.get("/restaurants")
async def list_restaurants(user: Dict[str, Any] = Depends(get_current_user)):
    payload = await get_bootstrap_payload(user)
    return payload.get("restaurants", [])


@api_router.get("/restaurants/{restaurant_id}")
async def get_restaurant(restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return await ensure_restaurant_access(restaurant_id, user)


@api_router.put("/restaurants/{restaurant_id}")
async def update_restaurant(restaurant_id: str, data: RestaurantUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    # Also manually preserve integer fields that could be 0 (falsy but valid)
    for field in ("slot_capacity", "slot_interval_minutes", "delivery_minimum"):
        val = getattr(data, field, None)
        if val is not None:
            update_data[field] = val
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Auto-detect timezone if address changed
    if "address" in update_data and update_data["address"]:
        detected_tz = await auto_detect_timezone(update_data["address"])
        if detected_tz:
            update_data["timezone"] = detected_tz
            logger.info(f"Updated timezone to {detected_tz} for restaurant {restaurant_id}")

    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    coll = get_business_collection(business_type)
    result = await coll.update_one({"id": restaurant_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = await coll.find_one({"id": restaurant_id}, {"_id": 0})
    return restaurant


# ============================================================
# RESTAURANT CONFIG ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/config")
async def get_restaurant_config(restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    if not config:
        default_config = RestaurantConfig(restaurant_id=restaurant_id)
        return default_config.model_dump()
    return config


@api_router.put("/restaurants/{restaurant_id}/config")
async def update_restaurant_config(restaurant_id: str, data: RestaurantConfigUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    cfg_coll = get_config_collection(business_type)
    existing = await cfg_coll.find_one({"restaurant_id": restaurant_id})
    if existing:
        await cfg_coll.update_one({"restaurant_id": restaurant_id}, {"$set": update_data})
    else:
        config = RestaurantConfig(restaurant_id=restaurant_id, **update_data)
        await cfg_coll.insert_one(config.model_dump())
    config = await cfg_coll.find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    return config

@api_router.get("/voice-preview/{voice_name}")
async def voice_preview(voice_name: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Generate a short audio preview of a Gemini voice using TTS API."""
    import base64
    ALLOWED_VOICES = {"Puck", "Charon", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"}
    if voice_name not in ALLOWED_VOICES:
        raise HTTPException(status_code=400, detail=f"Invalid voice name: {voice_name}")
    try:
        from google import genai
        from google.genai import types
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents="Hi! I'm your AI assistant. How can I help you today?",
            config=types.GenerateContentConfig(
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
                response_modalities=["AUDIO"],
            ),
        )
        audio_data = response.candidates[0].content.parts[0].inline_data.data
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        return {"audio_base64": audio_b64, "format": "wav"}
    except Exception as e:
        logger.error(f"Voice preview error for {voice_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# PUBLIC MENU PAGE (no auth required)
# ---------------------------------------------------------------------------
@app.get("/menu/{restaurant_id}", include_in_schema=False)
async def public_menu_page(restaurant_id: str):
    import asyncio as _asyncio
    results = await _asyncio.gather(
        db.restaurants.find_one({"id": restaurant_id}, {"_id": 0}),
        db.clinics.find_one({"id": restaurant_id}, {"_id": 0}),
        db.salons.find_one({"id": restaurant_id}, {"_id": 0}),
        db.home_services.find_one({"id": restaurant_id}, {"_id": 0}),
        db.legal.find_one({"id": restaurant_id}, {"_id": 0}),
    )
    restaurant = next((r for r in results if r), None)
    if not restaurant:
        return HTMLResponse("<h2>Menu not found</h2>", status_code=404)

    items = await db.menu_items.find(
        {"restaurant_id": restaurant_id}, {"_id": 0}
    ).to_list(500)

    # Group by category
    categories: Dict[str, list] = {}
    for item in sorted(items, key=lambda x: (x.get("category", ""), x.get("name", ""))):
        cat = item.get("category", "Other").title()
        if cat not in categories:
            categories[cat] = []
        price = f"${item.get('price', 0) / 100:.2f}"
        categories[cat].append({
            "name": item.get("name", ""),
            "price": price,
            "description": item.get("description", ""),
        })

    restaurant_name = restaurant.get("name", "Restaurant")
    cuisine = restaurant.get("cuisine_type", "")

    # Build HTML
    category_html = ""
    for cat_name, cat_items in categories.items():
        items_html = ""
        for i in cat_items:
            desc_html = f'<p class="desc">{i["description"]}</p>' if i["description"] else ""
            items_html += f"""
            <div class="item">
                <div class="item-header">
                    <span class="item-name">{i["name"]}</span>
                    <span class="item-price">{i["price"]}</span>
                </div>
                {desc_html}
            </div>"""
        category_html += f"""
        <div class="category">
            <h2>{cat_name}</h2>
            {items_html}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{restaurant_name} Menu</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                background: #f9f5f0; color: #1a1a1a; }}
        .header {{ background: #c8602a; color: white; padding: 24px 20px; text-align: center; }}
        .header h1 {{ font-size: 1.8rem; font-weight: 700; }}
        .header p {{ font-size: 0.95rem; opacity: 0.85; margin-top: 4px; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 16px; }}
        .category {{ background: white; border-radius: 12px; margin-bottom: 16px; 
                     overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .category h2 {{ background: #f0e8df; color: #c8602a; padding: 12px 16px; 
                        font-size: 0.85rem; font-weight: 700; text-transform: uppercase; 
                        letter-spacing: 0.05em; }}
        .item {{ padding: 12px 16px; border-bottom: 1px solid #f5f5f5; }}
        .item:last-child {{ border-bottom: none; }}
        .item-header {{ display: flex; justify-content: space-between; align-items: baseline; }}
        .item-name {{ font-size: 0.95rem; font-weight: 500; }}
        .item-price {{ font-size: 0.95rem; font-weight: 600; color: #c8602a; 
                       margin-left: 12px; white-space: nowrap; }}
        .desc {{ font-size: 0.8rem; color: #888; margin-top: 3px; }}
        .footer {{ text-align: center; padding: 20px; font-size: 0.75rem; color: #aaa; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{restaurant_name}</h1>
        <p>{cuisine} cuisine</p>
    </div>
    <div class="container">
        {category_html}
        <div class="footer">Powered by RingAI</div>
    </div>
</body>
</html>"""

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


# ============================================================
# MENU ITEM ENDPOINTS
# ============================================================

@api_router.post("/restaurants/{restaurant_id}/menu", response_model=MenuItem)
async def create_menu_item(restaurant_id: str, data: MenuItemCreate, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    item = MenuItem(restaurant_id=restaurant_id, **data.model_dump())
    await db.menu_items.insert_one(item.model_dump())
    return item


@api_router.get("/restaurants/{restaurant_id}/menu")
async def list_menu_items(restaurant_id: str, category: Optional[str] = None, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    query = {"restaurant_id": restaurant_id}
    if category:
        query["category"] = category
    items = await db.menu_items.find(query, {"_id": 0}).to_list(500)
    return items


@api_router.put("/menu/{item_id}")
async def update_menu_item(item_id: str, data: MenuItemUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    existing_item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    if not existing_item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    await ensure_restaurant_access(existing_item["restaurant_id"], user)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if isinstance(update_data.get("modifiers"), list):
        update_data["modifiers"] = [m.model_dump() if hasattr(m, "model_dump") else m for m in update_data["modifiers"]]
    result = await db.menu_items.update_one({"id": item_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")
    item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    return item


@api_router.delete("/menu/{item_id}")
async def delete_menu_item(item_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    existing_item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    if not existing_item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    await ensure_restaurant_access(existing_item["restaurant_id"], user)
    result = await db.menu_items.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return {"message": "Menu item deleted"}


@api_router.patch("/menu/{item_id}/toggle")
async def toggle_menu_item_availability(item_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    await ensure_restaurant_access(item["restaurant_id"], user)
    new_availability = not item.get("available", True)
    await db.menu_items.update_one({"id": item_id}, {"$set": {"available": new_availability}})
    return {"id": item_id, "available": new_availability}


# ============================================================
# MODIFIER GROUP ENDPOINTS (restaurant-level modifier library)
# ============================================================

@api_router.post("/restaurants/{restaurant_id}/modifier-groups")
async def create_modifier_group(
    restaurant_id: str,
    data: ModifierGroupCreate,
    user: Dict[str, Any] = Depends(get_current_user)
):
    await ensure_restaurant_access(restaurant_id, user)
    group = ModifierGroup(restaurant_id=restaurant_id, **data.model_dump())
    await db.modifier_groups.insert_one(group.model_dump())
    return group.model_dump()

@api_router.get("/restaurants/{restaurant_id}/modifier-groups")
async def get_modifier_groups(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    await ensure_restaurant_access(restaurant_id, user)
    groups = await db.modifier_groups.find(
        {"restaurant_id": restaurant_id},
        {"_id": 0}
    ).sort("display_order", 1).to_list(200)
    return groups

@api_router.put("/modifier-groups/{group_id}")
async def update_modifier_group(
    group_id: str,
    data: ModifierGroupUpdate,
    user: Dict[str, Any] = Depends(get_current_user)
):
    group = await db.modifier_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    await ensure_restaurant_access(group["restaurant_id"], user)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "options" in update_data:
        update_data["options"] = [
            o.model_dump() if hasattr(o, "model_dump") else o
            for o in update_data["options"]
        ]
    await db.modifier_groups.update_one({"id": group_id}, {"$set": update_data})
    return await db.modifier_groups.find_one({"id": group_id}, {"_id": 0})

@api_router.delete("/modifier-groups/{group_id}")
async def delete_modifier_group(
    group_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    group = await db.modifier_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    await ensure_restaurant_access(group["restaurant_id"], user)
    await db.modifier_groups.delete_one({"id": group_id})
    await db.menu_items.update_many(
        {"restaurant_id": group["restaurant_id"]},
        {"$pull": {"modifier_group_assignments": {"modifier_group_id": group_id}}}
    )
    return {"deleted": group_id}

@api_router.put("/menu/{item_id}/modifier-assignments")
async def update_item_modifier_assignments(
    item_id: str,
    assignments: List[MenuItemModifierAssignment],
    user: Dict[str, Any] = Depends(get_current_user)
):
    item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    await ensure_restaurant_access(item["restaurant_id"], user)
    await db.menu_items.update_one(
        {"id": item_id},
        {"$set": {"modifier_group_assignments": [a.model_dump() for a in assignments]}}
    )
    return {"id": item_id, "modifier_group_assignments": [a.model_dump() for a in assignments]}

@api_router.get("/restaurants/{restaurant_id}/menu-with-modifiers")
async def get_menu_with_modifiers(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Returns full menu with modifier groups resolved — used by dashboard and AI."""
    await ensure_restaurant_access(restaurant_id, user)
    items = await db.menu_items.find(
        {"restaurant_id": restaurant_id},
        {"_id": 0}
    ).to_list(500)
    groups = await db.modifier_groups.find(
        {"restaurant_id": restaurant_id},
        {"_id": 0}
    ).to_list(200)
    group_map = {g["id"]: g for g in groups}

    for item in items:
        resolved = []
        for assignment in item.get("modifier_group_assignments", []):
            gid = assignment.get("modifier_group_id")
            if gid in group_map:
                g = dict(group_map[gid])
                if assignment.get("override_required") is not None:
                    g["required"] = assignment["override_required"]
                if assignment.get("override_min") is not None:
                    g["min_selections"] = assignment["override_min"]
                if assignment.get("override_max") is not None:
                    g["max_selections"] = assignment["override_max"]
                if assignment.get("override_name"):
                    g["name"] = assignment["override_name"]
                g["display_order"] = assignment.get("display_order", g.get("display_order", 0))
                resolved.append(g)
        resolved.sort(key=lambda x: x.get("display_order", 0))
        item["resolved_modifiers"] = resolved

    return items


# ============================================================
# SERVICE ITEM ENDPOINTS (for appointment businesses)
# ============================================================

@api_router.post("/restaurants/{restaurant_id}/services", response_model=ServiceItem)
async def create_service(
    restaurant_id: str,
    data: ServiceItemCreate,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new service for appointment businesses."""
    await ensure_restaurant_access(restaurant_id, user)
    
    from security_utils import sanitize_string
    
    name = sanitize_string(data.name, max_length=100)
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Service name must be at least 2 characters")
    
    if data.duration_minutes < 5 or data.duration_minutes > 480:
        raise HTTPException(status_code=400, detail="Duration must be between 5 and 480 minutes")
    
    if data.buffer_minutes < 0 or data.buffer_minutes > 120:
        raise HTTPException(status_code=400, detail="Buffer time must be between 0 and 120 minutes")
    
    if data.price_cents is not None and (data.price_cents < 0 or data.price_cents > 10000000):
        raise HTTPException(status_code=400, detail="Invalid price value")
    
    description = sanitize_string(data.description or "", max_length=500) or None
    
    service_data = data.model_dump()
    service_data["name"] = name
    service_data["description"] = description
    
    service = ServiceItem(restaurant_id=restaurant_id, **service_data)
    await db.services.insert_one(service.model_dump())
    return service


@api_router.get("/restaurants/{restaurant_id}/services")
async def list_services(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """List all services for a business."""
    await ensure_restaurant_access(restaurant_id, user)
    services = await db.services.find(
        {"restaurant_id": restaurant_id},
        {"_id": 0}
    ).to_list(100)
    return services


@api_router.put("/services/{service_id}")
async def update_service(
    service_id: str,
    data: ServiceItemUpdate,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Update an existing service."""
    existing = await db.services.find_one({"id": service_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found")
    await ensure_restaurant_access(existing["restaurant_id"], user)
    
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    await db.services.update_one({"id": service_id}, {"$set": update_data})
    service = await db.services.find_one({"id": service_id}, {"_id": 0})
    return service


@api_router.delete("/services/{service_id}")
async def delete_service(
    service_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Delete a service."""
    existing = await db.services.find_one({"id": service_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found")
    await ensure_restaurant_access(existing["restaurant_id"], user)
    
    await db.services.delete_one({"id": service_id})
    return {"message": "Service deleted"}


# ============================================================
# APPOINTMENT ENDPOINTS (for appointment businesses)
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/appointments")
async def list_appointments(
    restaurant_id: str,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """List appointments for a business."""
    await ensure_restaurant_access(restaurant_id, user)
    
    query = {"restaurant_id": restaurant_id}
    if status and status != "ALL":
        query["status"] = status
    
    total = await db.appointments.count_documents(query)
    appointments = await (
        db.appointments.find(query, {"_id": 0})
        .sort("scheduled_date", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    
    return {
        "appointments": appointments,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@api_router.get("/appointments/{appointment_id}")
async def get_appointment(
    appointment_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get a single appointment."""
    appointment = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await ensure_restaurant_access(appointment["restaurant_id"], user)
    return appointment


# ── BLOCKED SLOTS ENDPOINTS ───────────────────────────────────────────────

@api_router.get("/restaurants/{restaurant_id}/blocked-slots")
async def get_blocked_slots(
    restaurant_id: str,
    date: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return all blocked slots for a business on a given date (YYYY-MM-DD)."""
    await ensure_restaurant_access(restaurant_id, user)
    slots = await db.blocked_slots.find(
        {"restaurant_id": restaurant_id, "date": date},
        {"_id": 0},
    ).to_list(200)
    return {"blocked_slots": slots}


@api_router.post("/restaurants/{restaurant_id}/blocked-slots")
async def block_slot(
    restaurant_id: str,
    data: BlockSlotRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Block a specific slot (prevents AI from booking it)."""
    await ensure_restaurant_access(restaurant_id, user)
    import uuid as _uuid
    doc = {
        "id": str(_uuid.uuid4()),
        "restaurant_id": restaurant_id,
        "date": data.date,
        "slot_time": data.slot_time,
        "reason": data.reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.blocked_slots.insert_one(doc)
    return serialize_mongo_doc(doc)


@api_router.delete("/restaurants/{restaurant_id}/blocked-slots/{slot_id}")
async def unblock_slot(
    restaurant_id: str,
    slot_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Unblock a previously blocked slot."""
    await ensure_restaurant_access(restaurant_id, user)
    result = await db.blocked_slots.delete_one(
        {"id": slot_id, "restaurant_id": restaurant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blocked slot not found")
    return {"deleted": True}


@api_router.get("/restaurants/{restaurant_id}/available-slots")
async def get_available_slots_endpoint(
    restaurant_id: str,
    date: str,
    service_name: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return computed available slots for the dashboard Availability tab."""
    await ensure_restaurant_access(restaurant_id, user)
    from appointment_service import get_available_slots
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    config = await get_config_collection(business_type).find_one(
        {"restaurant_id": restaurant_id}, {"_id": 0}
    ) or {}
    services = await db.services.find(
        {"restaurant_id": restaurant_id}, {"_id": 0}
    ).to_list(100)
    slots = await get_available_slots(
        restaurant_id=restaurant_id,
        date_str=date,
        service_name=service_name,
        services=services,
        config=config,
        db=db,
    )
    return {"date": date, "slots": slots}


@api_router.patch("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Cancel an appointment."""
    appointment = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await ensure_restaurant_access(appointment["restaurant_id"], user)
    
    await db.appointments.update_one(
        {"id": appointment_id},
        {"$set": {
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Appointment cancelled", "id": appointment_id}


@api_router.post("/appointments/{appointment_id}/send-reminder")
async def send_appointment_reminder(
    appointment_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Manually send a reminder SMS for an appointment."""
    appointment = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await ensure_restaurant_access(appointment["restaurant_id"], user)
    
    if appointment.get("status") != "confirmed":
        raise HTTPException(status_code=400, detail="Can only send reminders for confirmed appointments")
    
    try:
        from reminder_service import send_single_reminder
        success = await send_single_reminder(db, appointment_id)
        if success:
            return {"message": "Reminder sent successfully", "id": appointment_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to send reminder")
    except ImportError:
        raise HTTPException(status_code=500, detail="Reminder service not available")


@api_router.post("/admin/process-reminders")
async def process_reminders(user: Dict[str, Any] = Depends(get_current_user)):
    """Process all due appointment reminders (admin/cron endpoint)."""
    try:
        from reminder_service import process_appointment_reminders
        result = await process_appointment_reminders(db)
        return result
    except ImportError:
        raise HTTPException(status_code=500, detail="Reminder service not available")


# ============================================================
# GOOGLE CALENDAR INTEGRATION ENDPOINTS
# ============================================================

@api_router.get("/calendar/google/connect")
async def google_calendar_connect(
    restaurant_id: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Start Google Calendar OAuth flow."""
    await ensure_restaurant_access(restaurant_id, user)
    
    try:
        from calendar_service import is_google_calendar_configured, get_google_auth_url
        
        if not is_google_calendar_configured():
            raise HTTPException(
                status_code=400,
                detail="Google Calendar integration not configured. Please add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            )
        
        backend_url = get_backend_public_url()
        redirect_uri = f"{backend_url}/api/calendar/google/callback"
        
        auth_url = get_google_auth_url(restaurant_id, redirect_uri)
        return {"authorization_url": auth_url}
        
    except ImportError:
        raise HTTPException(status_code=500, detail="Calendar service not available")


@api_router.get("/calendar/google/callback")
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle Google Calendar OAuth callback."""
    try:
        from calendar_service import exchange_code_for_tokens
        
        backend_url = get_backend_public_url()
        redirect_uri = f"{backend_url}/api/calendar/google/callback"
        
        tokens = await exchange_code_for_tokens(code, redirect_uri)
        
        expires_in = tokens.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc).timestamp() + expires_in
        tokens["expires_at"] = expires_at
        
        restaurant_id = state
        _biz = await db.restaurants.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1})
        if not _biz:
            import asyncio as _asyncio
            _results = await _asyncio.gather(
                db.clinics.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
                db.salons.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
                db.home_services.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
                db.legal.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
            )
            _biz = next((r for r in _results if r), None)
        _business_type = _biz.get("business_type", "restaurant") if _biz else "restaurant"
        await get_config_collection(_business_type).update_one(
            {"restaurant_id": restaurant_id},
            {"$set": {
                "google_calendar_tokens": tokens,
                "google_calendar_id": "primary",
            }},
            upsert=True
        )
        
        frontend_url = get_frontend_url()
        from fastapi.responses import RedirectResponse
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/settings?calendar_connected=true"
        )
        
    except Exception as e:
        logger.error(f"Google Calendar callback error: {e}")
        frontend_url = get_frontend_url()
        from fastapi.responses import RedirectResponse
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/settings?calendar_error=true"
        )


@api_router.get("/restaurants/{restaurant_id}/calendar/status")
async def get_calendar_status(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Check if Google Calendar is connected."""
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    config = await get_config_collection(business_type).find_one(
        {"restaurant_id": restaurant_id},
        {"_id": 0, "google_calendar_tokens": 1, "google_calendar_id": 1}
    )
    
    is_connected = bool(
        config and
        config.get("google_calendar_tokens") and
        config["google_calendar_tokens"].get("access_token")
    )
    
    return {
        "connected": is_connected,
        "calendar_id": config.get("google_calendar_id") if config else None
    }


@api_router.get("/restaurants/{restaurant_id}/calendar/availability")
async def get_calendar_availability(
    restaurant_id: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    service_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get available appointment slots for a given date."""
    await ensure_restaurant_access(restaurant_id, user)
    
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    config = await get_config_collection(business_type).find_one(
        {"restaurant_id": restaurant_id},
        {"_id": 0}
    )
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    
    duration_minutes = 60
    buffer_minutes = 15
    
    if service_id:
        service = await db.services.find_one({"id": service_id}, {"_id": 0})
        if service:
            duration_minutes = service.get("duration_minutes", 60)
            buffer_minutes = service.get("buffer_minutes", 15)
    
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        target_date = target_date.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    busy_periods = []
    calendar_tokens = config.get("google_calendar_tokens")
    
    if calendar_tokens and calendar_tokens.get("access_token"):
        try:
            from calendar_service import get_valid_access_token, get_free_busy
            
            access_token = await get_valid_access_token(
                calendar_tokens, db, restaurant_id
            )
            
            calendar_id = config.get("google_calendar_id", "primary")
            start_time = target_date.replace(hour=0, minute=0)
            end_time = target_date.replace(hour=23, minute=59)
            
            busy_periods = await get_free_busy(
                access_token, calendar_id, start_time, end_time
            )
        except Exception as e:
            logger.warning(f"Could not get calendar availability: {e}")
    
    from calendar_service import calculate_available_slots
    
    operating_hours = config.get("operating_hours", {})
    slots = calculate_available_slots(
        date=target_date,
        operating_hours=operating_hours,
        service_duration_minutes=duration_minutes,
        buffer_minutes=buffer_minutes,
        busy_periods=busy_periods,
    )
    
    return {"date": date, "slots": slots}


@api_router.post("/restaurants/{restaurant_id}/calendar/book")
async def book_appointment(
    restaurant_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Book an appointment and create calendar event."""
    await ensure_restaurant_access(restaurant_id, user)
    
    body = await request.json()
    
    from security_utils import (
        validate_phone, validate_email, validate_date_format,
        validate_time_format, sanitize_string
    )
    
    required = ["service_name", "scheduled_date", "scheduled_time", "customer_name", "customer_phone"]
    for field in required:
        if not body.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    customer_phone = body["customer_phone"]
    if not validate_phone(customer_phone):
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    
    customer_email = body.get("customer_email")
    if customer_email and not validate_email(customer_email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    scheduled_date = body["scheduled_date"]
    if not validate_date_format(scheduled_date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    scheduled_time = body["scheduled_time"]
    if not validate_time_format(scheduled_time):
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM AM/PM or HH:MM")
    
    customer_name = sanitize_string(body["customer_name"], max_length=100)
    service_name = sanitize_string(body["service_name"], max_length=100)
    special_instructions = sanitize_string(body.get("special_instructions", ""), max_length=500)
    
    if not customer_name:
        raise HTTPException(status_code=400, detail="Customer name cannot be empty")
    
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    config = await get_config_collection(business_type).find_one(
        {"restaurant_id": restaurant_id},
        {"_id": 0}
    )
    
    restaurant = await get_business_collection(business_type).find_one(
        {"id": restaurant_id},
        {"_id": 0}
    )
    
    service_id = body.get("service_id")
    duration_minutes = 60
    
    if service_id:
        service = await db.services.find_one({"id": service_id}, {"_id": 0})
        if service:
            duration_minutes = service.get("duration_minutes", 60)
    
    appointment = AppointmentRecord(
        restaurant_id=restaurant_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        service_name=service_name,
        service_id=service_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        duration_minutes=duration_minutes,
        special_instructions=special_instructions,
        status="confirmed",
    )
    
    calendar_event_id = None
    calendar_tokens = config.get("google_calendar_tokens") if config else None
    
    if calendar_tokens and calendar_tokens.get("access_token"):
        try:
            from calendar_service import get_valid_access_token, create_calendar_event
            
            access_token = await get_valid_access_token(
                calendar_tokens, db, restaurant_id
            )
            
            date_str = body["scheduled_date"]
            time_str = body["scheduled_time"].upper().replace(".", "").strip()
            
            try:
                if "AM" in time_str or "PM" in time_str:
                    time_obj = datetime.strptime(time_str, "%I:%M %p")
                else:
                    time_obj = datetime.strptime(time_str, "%H:%M")
            except ValueError:
                time_obj = datetime.strptime("09:00", "%H:%M")
            
            start_dt = datetime.strptime(date_str, "%Y-%m-%d")
            start_dt = start_dt.replace(
                hour=time_obj.hour,
                minute=time_obj.minute,
                tzinfo=timezone.utc
            )
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            calendar_id = config.get("google_calendar_id", "primary")
            
            event = await create_calendar_event(
                access_token=access_token,
                calendar_id=calendar_id,
                summary=f"{body['service_name']} — {body['customer_name']}",
                description=f"Booked via RingAI.\nPhone: {body['customer_phone']}\nEmail: {body.get('customer_email', '')}",
                start_time=start_dt,
                end_time=end_dt,
                attendee_email=body.get("customer_email"),
            )
            
            calendar_event_id = event.get("id")
            appointment.calendar_event_id = calendar_event_id
            
        except Exception as e:
            logger.error(f"Failed to create calendar event: {e}")
    
    await db.appointments.insert_one(appointment.model_dump())
    
    try:
        from websocket_notifications import notify_new_appointment
        await notify_new_appointment(
            restaurant_id=restaurant_id,
            appointment_id=appointment.id,
            customer_name=customer_name,
            service_name=service_name,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
        )
    except Exception as e:
        logger.warning(f"Could not send WebSocket notification: {e}")
    
    try:
        from appointment_service import send_appointment_sms
        
        business_name = restaurant.get("name", "Business") if restaurant else "Business"
        
        await send_appointment_sms(
            caller_number=body["customer_phone"],
            booking={
                "customer_name": body["customer_name"],
                "service_name": body["service_name"],
                "preferred_date": body["scheduled_date"],
                "preferred_time": body["scheduled_time"],
            },
            business_name=business_name,
            duration_minutes=duration_minutes,
        )
    except Exception as e:
        logger.warning(f"Could not send appointment SMS: {e}")
    
    return {
        "success": True,
        "appointment": appointment.model_dump(),
        "calendar_event_id": calendar_event_id,
    }


@api_router.delete("/restaurants/{restaurant_id}/calendar/disconnect")
async def disconnect_calendar(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Disconnect Google Calendar integration."""
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    await get_config_collection(business_type).update_one(
        {"restaurant_id": restaurant_id},
        {"$set": {
            "google_calendar_tokens": None,
            "google_calendar_id": None,
        }}
    )
    
    return {"message": "Google Calendar disconnected"}


# ============================================================
# CALL RECORD ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/calls")
async def list_calls(
    restaurant_id: str,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    await ensure_restaurant_access(restaurant_id, user)
    query = {"restaurant_id": restaurant_id}
    if status and status != "ALL":
        query["status"] = status
    if search:
        query["$or"] = [
            {"caller_number": {"$regex": search, "$options": "i"}},
            {"caller_name": {"$regex": search, "$options": "i"}},
        ]
    # Date range filtering
    if date_from or date_to:
        date_query = {}
        if date_from:
            date_query["$gte"] = f"{date_from}T00:00:00"
        if date_to:
            date_query["$lte"] = f"{date_to}T23:59:59"
        if date_query:
            query["started_at"] = date_query
    total = await db.call_records.count_documents(query)
    calls = await (
        db.call_records.find(query, {"_id": 0})
        .sort("started_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    return {"calls": calls, "total": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit}


@api_router.get("/calls/{call_id}")
async def get_call(call_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    call = await db.call_records.find_one({"id": call_id}, {"_id": 0})
    if not call:
        raise HTTPException(status_code=404, detail="Call record not found")
    await ensure_restaurant_access(call["restaurant_id"], user)
    return call


# ============================================================
# ANALYTICS / DASHBOARD ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/analytics/summary")
async def get_analytics_summary(restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    all_calls = await db.call_records.find({"restaurant_id": restaurant_id}, {"_id": 0}).to_list(5000)

    total_calls = len(all_calls)
    completed_calls = sum(1 for c in all_calls if c.get("status") == "COMPLETED")
    escalated_calls = sum(1 for c in all_calls if c.get("escalated_to_human"))
    quality_scores = [c.get("quality_score", 0) for c in all_calls if c.get("quality_score")]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    durations = [c.get("duration_seconds", 0) for c in all_calls if c.get("duration_seconds")]
    avg_duration = sum(durations) / len(durations) if durations else 0
    total_revenue = sum(c.get("order_total", 0) for c in all_calls if c.get("order_total"))
    contained = sum(1 for c in all_calls if c.get("contained_by_ai"))
    containment_rate = (contained / total_calls * 100) if total_calls > 0 else 0

    calls_today = sum(1 for c in all_calls if c.get("started_at", "") >= today_start.isoformat())
    week_calls = [c for c in all_calls if c.get("started_at", "") >= week_ago.isoformat()]
    calls_this_week = len(week_calls)
    revenue_this_week = sum(c.get("order_total", 0) for c in week_calls if c.get("order_total"))

    month_ago = now - timedelta(days=30)
    month_calls = [c for c in all_calls if c.get("started_at", "") >= month_ago.isoformat()]
    calls_this_month = len(month_calls)
    revenue_this_month = sum(c.get("order_total", 0) for c in month_calls if c.get("order_total"))

    monthly_data = []
    for i in range(29, -1, -1):
        day = now - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        day_calls = [c for c in all_calls if c.get("started_at", "")[:10] == day_str]
        monthly_data.append({
            "date": day_str,
            "label": day.strftime("%b %d"),
            "calls": len(day_calls),
            "revenue": sum(c.get("order_total", 0) for c in day_calls if c.get("order_total")) / 100,
            "orders": sum(1 for c in day_calls if c.get("order_json")),
        })

    daily_data = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        day_label = day.strftime("%a")
        day_calls = [c for c in all_calls if c.get("started_at", "")[:10] == day_str]
        daily_data.append({
            "date": day_str,
            "label": day_label,
            "calls": len(day_calls),
            "revenue": sum(c.get("order_total", 0) for c in day_calls if c.get("order_total")) / 100,
            "orders": sum(1 for c in day_calls if c.get("order_json")),
        })

    hourly = [0] * 24
    for c in all_calls:
        try:
            h = int(c.get("started_at", "")[11:13])
            hourly[h] += 1
        except (ValueError, IndexError):
            pass
    hourly_data = [{"hour": f"{h:02d}:00", "calls": hourly[h]} for h in range(24)]

    item_counts = {}
    for c in all_calls:
        order = c.get("order_json")
        if order and isinstance(order, dict):
            for item in order.get("items", []):
                name = item.get("name", "Unknown")
                item_counts[name] = item_counts.get(name, 0) + item.get("quantity", 1)
    top_items = sorted([{"name": k, "count": v} for k, v in item_counts.items()], key=lambda x: -x["count"])[:10]

    recent = sorted(all_calls, key=lambda x: x.get("started_at", ""), reverse=True)[:5]
    recent_calls = [{
        "id": c.get("id"),
        "caller_number": c.get("caller_number"),
        "caller_name": c.get("caller_name"),
        "status": c.get("status"),
        "duration_seconds": c.get("duration_seconds"),
        "quality_score": c.get("quality_score"),
        "order_total": c.get("order_total"),
        "started_at": c.get("started_at"),
    } for c in recent]

    return {
        "total_calls": total_calls,
        "completed_calls": completed_calls,
        "escalated_calls": escalated_calls,
        "avg_quality_score": round(avg_quality, 1),
        "total_revenue": total_revenue,
        "avg_duration": round(avg_duration, 1),
        "ai_containment_rate": round(containment_rate, 1),
        "calls_today": calls_today,
        "calls_this_week": calls_this_week,
        "revenue_this_week": revenue_this_week,
        "calls_this_month": calls_this_month,
        "revenue_this_month": revenue_this_month,
        "monthly_call_data": monthly_data,
        "daily_call_data": daily_data,
        "hourly_distribution": hourly_data,
        "top_items": top_items,
        "recent_calls": recent_calls,
    }


@api_router.get("/restaurants/{restaurant_id}/analytics/export")
async def export_analytics(restaurant_id: str, start_date: str = Query(None), end_date: str = Query(None), user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    import csv, io

    now = datetime.now(timezone.utc)
    try:
        since = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc) if start_date else now - timedelta(days=7)
        until = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) if end_date else now
    except ValueError:
        since = now - timedelta(days=7)
        until = now

    calls = await db.call_records.find(
        {"restaurant_id": restaurant_id, "started_at": {"$gte": since.isoformat(), "$lte": until.isoformat()}},
        {"_id": 0}
    ).to_list(10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Caller", "Status", "Duration (s)", "Order Total ($)", "Quality Score"])
    for c in sorted(calls, key=lambda x: x.get("started_at", ""), reverse=True):
        writer.writerow([
            c.get("started_at", "")[:19],
            c.get("caller_name") or c.get("caller_number", ""),
            c.get("status", ""),
            c.get("duration_seconds", ""),
            round(c.get("order_total", 0) / 100, 2) if c.get("order_total") else "",
            c.get("quality_score", ""),
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=duuutah_export_{since.strftime('%Y%m%d')}_to_{until.strftime('%Y%m%d')}.csv"}
    )

# ============================================================
# ONBOARDING ENDPOINTS
# ============================================================

@api_router.post("/onboarding/menu/parse")
async def parse_menu(data: OnboardingMenuParse, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(data.restaurant_id, user)
    result = await parse_menu_text(data.menu_text)
    return result


@api_router.post("/onboarding/menu/confirm")
async def confirm_menu(
    restaurant_id: str = Query(...),
    items: List[Dict[str, Any]] = [],
    user: Dict[str, Any] = Depends(get_current_user),
):
    await ensure_restaurant_access(restaurant_id, user)
    
    # Check business type
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    
    if business_type in ("clinic", "salon", "home_services", "legal"):
        # Save to services collection instead of menu_items
        await db.services.delete_many({"restaurant_id": restaurant_id})
        saved = []
        for item_data in items:
            service = ServiceItem(
                restaurant_id=restaurant_id,
                name=item_data.get("name", ""),
                description=item_data.get("description"),
                duration_minutes=item_data.get("duration_minutes", 60),
                buffer_minutes=15,
                price_cents=item_data.get("price", 0),
                available=True,
            )
            await db.services.insert_one(service.model_dump())
            saved.append(service.model_dump())
        return {"saved": len(saved), "items": saved}
    else:
        # Original restaurant logic — menu_items
        await db.menu_items.delete_many({"restaurant_id": restaurant_id})
        saved = []
        for item_data in items:
            item = MenuItem(
                restaurant_id=restaurant_id,
                name=item_data.get("name", ""),
                description=item_data.get("description"),
                category=item_data.get("category", "Uncategorized"),
                price=item_data.get("price", 0),
                modifiers=[],
                allergens=item_data.get("allergens", []),
            )
            await db.menu_items.insert_one(item.model_dump())
            saved.append(item.model_dump())
        return {"saved": len(saved), "items": saved}


@api_router.post("/onboarding/activate")
async def activate_restaurant(data: OnboardingActivate, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(data.restaurant_id, user)

    membership = await db.memberships.find_one({"restaurant_id": data.restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    _biz_coll = get_business_collection(business_type)
    existing = await _biz_coll.find_one({"id": data.restaurant_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    update_fields = {
        "status": "active",
        "is_active": True,
        "onboarding_step": 7,
        "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
    }

    if not existing.get("phone_number"):
        try:
            twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
            twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
            if twilio_sid and twilio_token:
                twilio_client = TwilioClient(twilio_sid, twilio_token)
                voice_url = f"{get_backend_public_url()}/api/twilio/incoming"
                candidates = twilio_client.available_phone_numbers("US").local.list(
                    sms_enabled=True,
                    voice_enabled=True,
                    limit=1,
                )
                if candidates:
                    purchased = twilio_client.incoming_phone_numbers.create(
                        phone_number=candidates[0].phone_number,
                        voice_url=voice_url,
                        voice_method="POST",
                    )
                    update_fields["phone_number"] = purchased.phone_number
                    update_fields["twilio_number_sid"] = purchased.sid
                    logger.info(f"Auto-provisioned Twilio number {purchased.phone_number} for restaurant {data.restaurant_id}")
                else:
                    logger.warning("No available Twilio numbers found during onboarding")
        except Exception as e:
            logger.warning(f"Could not auto-provision Twilio number: {e}")

    result = await _biz_coll.update_one({"id": data.restaurant_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = await _biz_coll.find_one({"id": data.restaurant_id}, {"_id": 0})
    return restaurant


# ============================================================
# DEMO/SIMULATION ENDPOINTS
# ============================================================

@api_router.post("/demo/simulate-call")
async def simulate_call(restaurant_id: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)

    if not demo_mode_enabled():
        raise HTTPException(status_code=403, detail="Demo mode is disabled")

    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    menu_items = await db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

    caller_names = [
        "Sarah Mitchell", "James Wilson", "Maria Garcia", "David Kim", "Emma Johnson",
        "Robert Chen", "Lisa Park", "Michael Brown", "Jennifer Lee", "Chris Taylor"
    ]
    caller = random.choice(caller_names)
    phone = f"+1{random.randint(200, 999)}{random.randint(1000000, 9999999)}"

    if menu_items:
        order_items = random.sample(menu_items, min(random.randint(1, 4), len(menu_items)))
    else:
        order_items = [{"name": "Classic Burger", "price": 1499}, {"name": "Caesar Salad", "price": 1199}]

    items_for_order = []
    total = 0
    for item in order_items:
        qty = random.choice([1, 1, 1, 2])
        subtotal = item.get("price", 999) * qty
        total += subtotal
        items_for_order.append({
            "name": item.get("name", "Item"),
            "quantity": qty,
            "price": item.get("price", 999),
            "modifiers": [],
            "subtotal": subtotal,
        })

    duration = random.randint(90, 300)
    is_escalated = random.random() < 0.08
    status = "ESCALATED" if is_escalated else "COMPLETED"

    restaurant_name = restaurant.get("name", "the restaurant")
    item_names = [i["name"] for i in items_for_order]

    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    system_prompt = None
    if config and is_gemini_available():
        system_prompt = build_system_prompt(
            restaurant_name=restaurant_name,
            cuisine_type=restaurant.get("cuisine_type", ""),
            persona=config.get("persona", "friendly"),
            business_rules=config.get("business_rules", []),
            escalation_rules=config.get("escalation_rules", []),
            menu_items=menu_items,
            disclosure_text=config.get("disclosure_text", f"Hi! I'm the AI assistant for {restaurant_name}."),
            upsell_enabled=config.get("upsell_enabled", True),
            delivery_enabled=restaurant.get("delivery_enabled", config.get("delivery_enabled", True)),
            delivery_minimum=config.get("delivery_minimum", 1500),
            restaurant_timezone=restaurant.get("timezone", "UTC"),
            restaurant_address=restaurant.get("address"),
        )

    transcript = []
    if system_prompt:
        try:
            greeting = await get_conversation_response(system_prompt, [], "")
            if not greeting or len(greeting) < 5:
                greeting = f"Hi! I'm an AI assistant for {restaurant_name}. How can I help you today?"
            transcript.append({"role": "ai", "text": greeting, "timestamp": "00:00"})

            customer_msg1 = "Hi, I'd like to place an order for pickup."
            transcript.append({"role": "customer", "text": customer_msg1, "timestamp": "00:03"})
            ai_resp1 = await get_conversation_response(system_prompt, transcript, customer_msg1)
            transcript.append({"role": "ai", "text": ai_resp1, "timestamp": "00:05"})

            customer_msg2 = f"Can I get a {item_names[0]} please?"
            transcript.append({"role": "customer", "text": customer_msg2, "timestamp": "00:08"})
            ai_resp2 = await get_conversation_response(system_prompt, transcript, customer_msg2)
            transcript.append({"role": "ai", "text": ai_resp2, "timestamp": "00:10"})

            if len(item_names) > 1:
                customer_msg3 = f"And also a {item_names[1]}."
                transcript.append({"role": "customer", "text": customer_msg3, "timestamp": "00:15"})
                ai_resp3 = await get_conversation_response(system_prompt, transcript, customer_msg3)
                transcript.append({"role": "ai", "text": ai_resp3, "timestamp": "00:17"})

            customer_msg_done = "That's all, thanks."
            transcript.append({"role": "customer", "text": customer_msg_done, "timestamp": "00:22"})
            ai_resp_done = await get_conversation_response(system_prompt, transcript, customer_msg_done)
            transcript.append({"role": "ai", "text": ai_resp_done, "timestamp": "00:25"})

            customer_confirm = "Yes, that's right."
            transcript.append({"role": "customer", "text": customer_confirm, "timestamp": "00:30"})
            ai_close = await get_conversation_response(system_prompt, transcript, customer_confirm)
            transcript.append({"role": "ai", "text": ai_close, "timestamp": "00:33"})
        except Exception as e:
            logger.error(f"Gemini conversation error in simulate_call: {e}")
            transcript = _build_mock_transcript(restaurant_name, item_names, items_for_order, total)
    else:
        transcript = _build_mock_transcript(restaurant_name, item_names, items_for_order, total)

    order_json = {
        "items": items_for_order,
        "total": total,
        "type": random.choice(["pickup", "pickup", "delivery"]),
        "special_instructions": "",
    }
    analysis = await analyse_call_transcript(transcript, order_json, menu_items)
    quality = analysis.get("quality_score", random.randint(78, 99))

    now = datetime.now(timezone.utc)
    start_offset = random.randint(0, 3600 * 4)
    started_at = (now - timedelta(seconds=start_offset)).isoformat()
    ended_at = (now - timedelta(seconds=start_offset - duration)).isoformat()

    call = CallRecord(
        restaurant_id=restaurant_id,
        caller_number=phone,
        caller_name=caller,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        status=status,
        contained_by_ai=not is_escalated,
        escalated_to_human=is_escalated,
        transcript=transcript,
        order_json=order_json,
        pos_order_id=f"POS-{random.randint(10000, 99999)}" if not is_escalated else None,
        quality_score=quality,
        analysis_json=analysis,
        claude_tokens_used=0,
        order_total=total,
    )

    await db.call_records.insert_one(call.model_dump())
    return call.model_dump()


def _build_mock_transcript(restaurant_name, item_names, items_for_order, total):
    transcript = [
        {"role": "ai", "text": f"Hi! I'm an AI assistant for {restaurant_name}. How can I help you today?", "timestamp": "00:00"},
        {"role": "customer", "text": "Hi, I'd like to place an order for pickup.", "timestamp": "00:03"},
        {"role": "ai", "text": "Of course! What would you like to order?", "timestamp": "00:05"},
        {"role": "customer", "text": f"Can I get a {item_names[0]} please?", "timestamp": "00:08"},
        {"role": "ai", "text": f"Great choice! One {item_names[0]}. Anything else?", "timestamp": "00:10"},
    ]
    if len(item_names) > 1:
        transcript.extend([
            {"role": "customer", "text": f"And also a {item_names[1]}.", "timestamp": "00:15"},
            {"role": "ai", "text": f"Got it! One {item_names[1]} added. Would you like anything else?", "timestamp": "00:17"},
        ])
    transcript.extend([
        {"role": "customer", "text": "That's all, thanks.", "timestamp": "00:22"},
        {"role": "ai", "text": "Let me read back your order: " + ", ".join([str(i["quantity"]) + "x " + i["name"] for i in items_for_order]) + f". Your total is ${total / 100:.2f}. Is that correct?", "timestamp": "00:25"},
        {"role": "customer", "text": "Yes, that's right.", "timestamp": "00:30"},
        {"role": "ai", "text": f"Your order has been placed! It'll be ready for pickup in about 20 minutes. Thank you for calling {restaurant_name}!", "timestamp": "00:33"},
    ])
    return transcript


@api_router.post("/demo/seed")
async def seed_demo_data(restaurant_id: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)

    if not demo_mode_enabled():
        raise HTTPException(status_code=403, detail="Demo mode is disabled")

    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    num_calls = random.randint(30, 50)
    now = datetime.now(timezone.utc)

    for _ in range(num_calls):
        offset = random.randint(0, 7 * 24 * 3600)
        call_time = now - timedelta(seconds=offset)
        hour = call_time.hour
        if hour < 10 or hour > 22:
            call_time = call_time.replace(hour=random.randint(10, 22))

        await simulate_call_internal(restaurant_id, call_time)

    return {"message": f"Generated {num_calls} demo calls", "restaurant_id": restaurant_id}


async def simulate_call_internal(restaurant_id: str, call_time: datetime):
    menu_items = await db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

    caller_names = [
        "Sarah Mitchell", "James Wilson", "Maria Garcia", "David Kim", "Emma Johnson",
        "Robert Chen", "Lisa Park", "Michael Brown", "Jennifer Lee", "Chris Taylor",
        "Ana Rodriguez", "Tom Harris", "Priya Patel", "Kevin O'Brien", "Sophie Turner"
    ]
    caller = random.choice(caller_names)
    phone = f"+1{random.randint(200, 999)}{random.randint(1000000, 9999999)}"

    if menu_items:
        order_items = random.sample(menu_items, min(random.randint(1, 4), len(menu_items)))
    else:
        order_items = [{"name": "Classic Burger", "price": 1499}]

    items_for_order = []
    total = 0
    for item in order_items:
        qty = random.choice([1, 1, 1, 2])
        subtotal = item.get("price", 999) * qty
        total += subtotal
        items_for_order.append({
            "name": item.get("name", "Item"),
            "quantity": qty,
            "price": item.get("price", 999),
            "modifiers": [],
            "subtotal": subtotal,
        })

    duration = random.randint(60, 360)
    quality = random.randint(72, 99)
    is_escalated = random.random() < 0.08
    status = "ESCALATED" if is_escalated else ("FAILED" if random.random() < 0.03 else "COMPLETED")

    started_at = call_time.isoformat()
    ended_at = (call_time + timedelta(seconds=duration)).isoformat()

    analysis = {
        "quality_score": quality,
        "order_accuracy": "accurate" if quality > 85 else "minor_issues",
        "issues": random.sample(["Slow response time", "Missed upsell", "Clarification needed", "Menu item confusion"], random.randint(0, 2)),
        "highlights": random.sample(["Natural conversation", "Efficient ordering", "Clear readback", "Good upsell", "Friendly greeting"], random.randint(1, 3)),
        "menu_suggestions": [],
        "rule_suggestions": [],
        "summary": f"{'Successful' if status == 'COMPLETED' else 'Escalated'} call from {caller}. {len(items_for_order)} items ordered.",
    }

    call = CallRecord(
        restaurant_id=restaurant_id,
        caller_number=phone,
        caller_name=caller,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        status=status,
        contained_by_ai=not is_escalated,
        escalated_to_human=is_escalated,
        transcript=[
            {"role": "ai", "text": "Hi! I'm an AI assistant. How can I help?", "timestamp": "00:00"},
            {"role": "customer", "text": f"I'd like to order {items_for_order[0]['name']}.", "timestamp": "00:05"},
            {"role": "ai", "text": f"Great! One {items_for_order[0]['name']}. Anything else?", "timestamp": "00:08"},
            {"role": "customer", "text": "That's all, thanks.", "timestamp": "00:12"},
            {"role": "ai", "text": f"Your total is ${total / 100:.2f}. Order placed!", "timestamp": "00:15"},
        ],
        order_json={"items": items_for_order, "total": total, "type": random.choice(["pickup", "delivery"])},
        pos_order_id=f"POS-{random.randint(10000, 99999)}",
        quality_score=quality,
        analysis_json=analysis,
        claude_tokens_used=random.randint(600, 2200),
        order_total=total,
    )
    await db.call_records.insert_one(call.model_dump())


# ============================================================
# SEED INITIAL DEMO RESTAURANT
# ============================================================

async def create_stripe_payment_link(
    order_total_cents: int,
    restaurant_name: str,
    call_sid: str,
) -> Optional[str]:
    if not stripe.api_key:
        return None
    if order_total_cents <= 0:
        return None
    try:
        # Create a one-time price
        price = stripe.Price.create(
            unit_amount=order_total_cents,
            currency="usd",
            product_data={
                "name": f"{restaurant_name} Phone Order",
            },
        )
        # Create payment link
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            metadata={"call_sid": call_sid},
            after_completion={
                "type": "message",
                "message": {"message": "Payment received! See you soon."},
            },
        )
        return payment_link.url
    except Exception as e:
        logger.error(f"Stripe payment link error: {e}")
        return None

@app.on_event("startup")
async def startup_seed():
    setup_signal_handlers()
    logger.info("Allowed CORS origins: %s", get_cors_origins())
    try:
        from scheduler_service import start_scheduler
        start_scheduler(db)
        logger.info("Background scheduler started")
    except Exception as e:
        logger.warning(f"Could not start scheduler: {e}")

    if os.environ.get("SEED_DEMO_DATA", "false").lower() != "true":
        logger.info("Demo seed disabled")
        return

    import asyncio as _asyncio
    counts = await _asyncio.gather(
        db.restaurants.count_documents({}),
        db.clinics.count_documents({}),
        db.salons.count_documents({}),
        db.home_services.count_documents({}),
        db.legal.count_documents({}),
    )
    count = sum(counts)
    if count == 0:
        logger.info("Seeding demo restaurant...")
        demo_restaurant = Restaurant(
            id="demo-restaurant-001",
            name="Bella Cucina",
            cuisine_type="Italian-American",
            phone_number="+15551234567",
            timezone="America/New_York",
            address="123 Main Street, New York, NY 10001",
            is_active=True,
            plan="GROWTH",
            monthly_call_count=0,
            owner_name="Bella Owner",
            owner_email="owner@bellacucina.example",
            business_phone="+15551234567",
            billing_email="billing@bellacucina.example",
            status="active",
            onboarding_step=7,
        )
        await db.restaurants.insert_one(demo_restaurant.model_dump())  # demo is always restaurant type

        config = RestaurantConfig(
            restaurant_id="demo-restaurant-001",
            persona="warm and friendly Italian-American",
            voice_id="21m00Tcm4TlvDq8ikWAM",
            business_rules=[
                "Maximum party size for reservations is 12",
                "Delivery minimum order is $15",
                "We are closed on Mondays",
                "Happy hour: 4-6pm weekdays, 20% off appetizers",
                "No substitutions on prix fixe menu",
            ],
            escalation_rules=[
                "Customer complaint about food quality",
                "Catering orders (20+ guests)",
                "Customer requests to speak to manager",
                "Allergic reaction concerns",
            ],
            upsell_enabled=True,
            disclosure_text="Hi! I'm Bella, the AI assistant for Bella Cucina. How can I help you today?",
            delivery_enabled=True,
            delivery_minimum=1500,
        )
        await db.restaurant_configs.insert_one(config.model_dump())

        menu_items_data = [
            {"name": "Bruschetta", "category": "Appetizers", "price": 1299, "description": "Toasted bread with fresh tomatoes, basil, garlic & olive oil", "allergens": ["gluten"], "available": True},
            {"name": "Calamari Fritti", "category": "Appetizers", "price": 1499, "description": "Crispy fried calamari with marinara sauce", "allergens": ["gluten", "shellfish"], "available": True},
            {"name": "Caprese Salad", "category": "Appetizers", "price": 1199, "description": "Fresh mozzarella, tomatoes, basil & balsamic glaze", "allergens": ["dairy"], "available": True},
            {"name": "Minestrone Soup", "category": "Appetizers", "price": 899, "description": "Hearty vegetable soup with pasta & parmesan", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Margherita Pizza", "category": "Pizza", "price": 1699, "description": "San Marzano tomatoes, fresh mozzarella, basil", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Pepperoni Pizza", "category": "Pizza", "price": 1899, "description": "Classic pepperoni with mozzarella", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Quattro Formaggi", "category": "Pizza", "price": 1999, "description": "Mozzarella, gorgonzola, parmesan, fontina", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Spaghetti Bolognese", "category": "Pasta", "price": 1899, "description": "Classic meat sauce with spaghetti", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Fettuccine Alfredo", "category": "Pasta", "price": 1799, "description": "Creamy parmesan sauce with fettuccine", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Penne Arrabbiata", "category": "Pasta", "price": 1599, "description": "Spicy tomato sauce with penne", "allergens": ["gluten"], "available": True},
        ]
        for item_data in menu_items_data:
            item = MenuItem(restaurant_id="demo-restaurant-001", **item_data)
            await db.menu_items.insert_one(item.model_dump())

        now = datetime.now(timezone.utc)
        for _ in range(40):
            offset = random.randint(0, 7 * 24 * 3600)
            call_time = now - timedelta(seconds=offset)
            hour = call_time.hour
            if hour < 10 or hour > 22:
                call_time = call_time.replace(hour=random.randint(11, 21))
            await simulate_call_internal("demo-restaurant-001", call_time)

        logger.info("Demo data seeded successfully!")


# ============================================================
# TWILIO WEBHOOK / INTEGRATION ENDPOINTS
# ============================================================

@api_router.get("/integrations/twilio/status")
async def twilio_status(restaurant_id: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    return {
        "configured": bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN")),
        "phone_number": restaurant.get("phone_number"),
        "twilio_number_sid": restaurant.get("twilio_number_sid"),
        "active": bool(restaurant.get("phone_number")),
    }


@api_router.post("/integrations/twilio/provision-number")
async def twilio_provision_number(data: TwilioProvisionRequest, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(data.restaurant_id, user)

    client = get_twilio_client()
    voice_url = f"{get_backend_public_url()}/api/twilio/incoming"

    candidates = client.available_phone_numbers("US").local.list(
        area_code=int(data.area_code) if data.area_code else None,
        sms_enabled=True,
        voice_enabled=True,
        limit=1,
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="No available Twilio numbers found")

    selected = candidates[0]
    purchased = client.incoming_phone_numbers.create(
        phone_number=selected.phone_number,
        voice_url=voice_url,
        voice_method="POST",
    )

    _membership = await db.memberships.find_one({"restaurant_id": data.restaurant_id, "user_id": user["id"]}, {"_id": 0})
    _business_type = _membership.get("business_type", "restaurant") if _membership else "restaurant"
    await get_business_collection(_business_type).update_one(
        {"id": data.restaurant_id},
        {"$set": {
            "phone_number": purchased.phone_number,
            "twilio_number_sid": purchased.sid,
        }}
    )

    return {
        "phone_number": purchased.phone_number,
        "twilio_number_sid": purchased.sid,
        "voice_url": voice_url,
    }


@api_router.post("/integrations/twilio/assign-existing-number")
async def twilio_assign_existing_number(data: TwilioAssignNumberRequest, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(data.restaurant_id, user)

    client = get_twilio_client()
    voice_url = f"{get_backend_public_url()}/api/twilio/incoming"

    numbers = client.incoming_phone_numbers.list(phone_number=data.phone_number, limit=1)
    if not numbers:
        raise HTTPException(status_code=404, detail="Twilio number not found in this account")

    number = numbers[0]
    updated = client.incoming_phone_numbers(number.sid).update(
        voice_url=voice_url,
        voice_method="POST",
    )

    _membership2 = await db.memberships.find_one({"restaurant_id": data.restaurant_id, "user_id": user["id"]}, {"_id": 0})
    _business_type2 = _membership2.get("business_type", "restaurant") if _membership2 else "restaurant"
    await get_business_collection(_business_type2).update_one(
        {"id": data.restaurant_id},
        {"$set": {
            "phone_number": updated.phone_number,
            "twilio_number_sid": updated.sid,
        }}
    )

    return {
        "phone_number": updated.phone_number,
        "twilio_number_sid": updated.sid,
        "voice_url": voice_url,
    }

@api_router.post("/restaurants/{restaurant_id}/send-menu-sms")
async def send_menu_sms_endpoint(
    restaurant_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    restaurant = await get_business_collection(business_type).find_one(
        {"id": restaurant_id}, {"_id": 0}
    )
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    body = await request.json()
    caller_number = body.get("caller_number")
    if not caller_number:
        raise HTTPException(status_code=400, detail="caller_number required")

    base_url = str(request.base_url).rstrip("/")
    success = await send_menu_sms(
        caller_number=caller_number,
        restaurant_name=restaurant.get("name", "the restaurant"),
        restaurant_id=restaurant_id,
        base_url=base_url,
    )
    return {"sent": success}


@api_router.post("/twilio/incoming")
async def twilio_incoming_call(request: Request):
    # ── Security: validate request is genuinely from Twilio ──
    backend_url = get_backend_public_url()
    if "localhost" not in backend_url and "127.0.0.1" not in backend_url:
        sig = request.headers.get("X-Twilio-Signature", "")
        full_url = str(request.url)
        form_dict = dict(await request.form())
        if not validate_twilio_request(full_url, form_dict, sig):
            logger.warning(f"Rejected forged Twilio request from {request.client.host}")
            return Response(status_code=403, content="Forbidden")
        form = form_dict
    else:
        form = await request.form()

    called_number = form.get("Called", "")
    call_sid = form.get("CallSid", "")
    caller_number = form.get("From", "")

    logger.info(f"Incoming call: {caller_number} -> {called_number} (SID: {call_sid})")

    import asyncio as _asyncio
    _phone_results = await _asyncio.gather(
        db.restaurants.find_one({"phone_number": called_number}, {"_id": 0}),
        db.clinics.find_one({"phone_number": called_number}, {"_id": 0}),
        db.salons.find_one({"phone_number": called_number}, {"_id": 0}),
        db.home_services.find_one({"phone_number": called_number}, {"_id": 0}),
        db.legal.find_one({"phone_number": called_number}, {"_id": 0}),
    )
    restaurant = next((r for r in _phone_results if r), None)
    if not restaurant or not restaurant.get("is_active"):
        return Response(
            content='<?xml version="1.0"?><Response><Say>Sorry, this number is not currently active. Goodbye.</Say></Response>',
            media_type="application/xml",
        )

    # Pre-fetch all pipeline data NOW so WebSocket handler starts instantly
    restaurant_id = restaurant["id"]
    business_type = restaurant.get("business_type", "restaurant")
    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    menu_items = await db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(500)

    # Enrich menu items with resolved modifier groups for AI prompt
    if business_type == "restaurant" or config is None:
        modifier_groups = await db.modifier_groups.find(
            {"restaurant_id": restaurant_id, "active": True}, {"_id": 0}
        ).to_list(200)
        group_map = {g["id"]: g for g in modifier_groups}
        for item in menu_items:
            resolved = []
            for assignment in item.get("modifier_group_assignments", []):
                gid = assignment.get("modifier_group_id")
                if gid in group_map:
                    g = dict(group_map[gid])
                    if assignment.get("override_required") is not None:
                        g["required"] = assignment["override_required"]
                    if assignment.get("override_min") is not None:
                        g["min_selections"] = assignment["override_min"]
                    if assignment.get("override_max") is not None:
                        g["max_selections"] = assignment["override_max"]
                    if assignment.get("override_name"):
                        g["name"] = assignment["override_name"]
                    g["display_order"] = assignment.get("display_order", g.get("display_order", 0))
                    resolved.append(g)
            resolved.sort(key=lambda x: x.get("display_order", 0))
            item["resolved_modifiers"] = resolved

    # Get business type for horizontal platform support
    business_type = config.get("business_type", "restaurant") if config else "restaurant"

    # For appointment businesses, get services instead of menu items
    services = []
    if business_type in ("clinic", "salon", "home_services", "legal"):
        services = await db.services.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

    # Pre-fetch availability for appointment businesses before building prompt.
    # This eliminates mid-call tool calls for common date requests entirely.
    cached_availability = None
    if business_type in ("clinic", "salon", "home_services", "legal"):
        logger.info(f"[{call_sid}] Starting availability pre-fetch for {business_type}")
        try:
            from appointment_service import pre_fetch_availability
            cached_availability = await pre_fetch_availability(
                restaurant_id=restaurant_id,
                services=services,
                config={**(config or {}), "timezone": restaurant.get("timezone", "UTC")},
                db=db,
                days_ahead=7,
            )
            logger.info(
                f"[{call_sid}] Availability pre-fetched for "
                f"{len(cached_availability)} days"
            )
        except Exception as _e:
            logger.warning(f"[{call_sid}] Availability pre-fetch failed (non-fatal): {_e}")

    # Use system prompt router for correct prompt by business type
    from gemini_service import get_system_prompt
    system_prompt = get_system_prompt(
        business_type=business_type,
        restaurant_name=restaurant.get("name", "the restaurant"),
        cuisine_type=restaurant.get("cuisine_type", ""),
        persona=config.get("persona", "friendly") if config else "friendly",
        business_rules=config.get("business_rules", []) if config else [],
        escalation_rules=config.get("escalation_rules", []) if config else [],
        menu_items=menu_items,
        disclosure_text=config.get("disclosure_text", "Hi! I'm an AI assistant. How can I help you today?") if config else "Hi! I'm an AI assistant. How can I help you today?",
        upsell_enabled=config.get("upsell_enabled", True) if config else True,
        delivery_enabled=restaurant.get("delivery_enabled", config.get("delivery_enabled", True) if config else True),
        delivery_minimum=config.get("delivery_minimum", 1500) if config else 1500,
        avg_prep_time_minutes=restaurant.get("avg_prep_time_minutes", 20),
        escalation_phone=config.get("escalation_phone_number") if config else None,
        operating_hours=config.get("operating_hours") if config else None,
        restaurant_timezone=restaurant.get("timezone", "UTC"),
        restaurant_address=restaurant.get("address"),
        services=services,
        cached_availability=cached_availability,
    )

    await db.active_calls.update_one(
        {"call_sid": call_sid},
        {"$set": {
            "call_sid": call_sid,
            "restaurant_id": restaurant_id,
            "caller_number": caller_number,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "system_prompt": system_prompt,
            "restaurant": restaurant,
            "config": config or {},
            "menu_items": menu_items,
            "services": services,
        }},
        upsert=True,
    )

    host = request.headers.get("host", "localhost")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/api/twilio/media-stream"

    backend_url = get_backend_public_url()
    status_callback_url = f"{backend_url}/api/twilio/call-status"
    twiml = generate_twiml_stream_response(ws_url, call_sid, status_callback_url)
    return Response(content=twiml, media_type="application/xml")


@api_router.post("/twilio/call-status")
async def twilio_call_status(request: Request):
    """
    Twilio status callback — fires after every call ends.
    Captures exact CallDuration and updates the call record with accurate cost data.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    call_status = form.get("CallStatus", "")
    duration_seconds = form.get("CallDuration")  # exact seconds from Twilio

    if not call_sid:
        return Response(content="ok", media_type="text/plain")

    logger.info(f"[{call_sid}] Twilio status callback: status={call_status} duration={duration_seconds}s")

    if duration_seconds is not None:
        try:
            duration_secs = int(duration_seconds)
            import math

            # Exact costs from Twilio
            cost_twilio_voice = math.ceil(duration_secs / 60) * 0.0085

            # Fetch existing call record to get SMS count
            record = await db.call_records.find_one({"twilio_call_sid": call_sid}, {"_id": 0})
            if record:
                sms_count = record.get("twilio_sms_count", 0)
                cost_twilio_sms = sms_count * 0.0083
                extract_tokens = record.get("gemini_extract_tokens", 0)
                cost_gemini_extract = (
                    (extract_tokens * 0.7 / 1_000_000) * 0.075 +
                    (extract_tokens * 0.3 / 1_000_000) * 0.30
                )
                cost_total = cost_twilio_voice + cost_twilio_sms + cost_gemini_extract

                await db.call_records.update_one(
                    {"twilio_call_sid": call_sid},
                    {"$set": {
                        "duration_seconds_twilio": duration_secs,
                        "cost_twilio_voice_cents": round(cost_twilio_voice * 100, 4),
                        "cost_twilio_sms_cents": round(cost_twilio_sms * 100, 4),
                        "cost_gemini_live_cents": 0.0,
                        "cost_gemini_extract_cents": round(cost_gemini_extract * 100, 4),
                        "cost_total_cents": round(cost_total * 100, 4),
                        "twilio_call_status_final": call_status,
                    }}
                )
                logger.info(f"[{call_sid}] Cost updated: voice=${cost_twilio_voice:.4f} sms=${cost_twilio_sms:.4f} total=${cost_total:.4f}")
        except Exception as e:
            logger.error(f"[{call_sid}] Cost callback error: {e}")

    return Response(content="ok", media_type="text/plain")

@api_router.get("/admin/cost-analytics")
async def admin_cost_analytics(
    days: int = 30,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Admin-only endpoint — internal cost and margin tracking.
    Never exposed to business owners.
    """
    admin_user_id = os.environ.get("ADMIN_USER_ID")
    if not admin_user_id or user.get("id") != admin_user_id:
        raise HTTPException(status_code=403, detail="Admin access required")

    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"started_at": {"$gte": since}}},
        {"$group": {
            "_id": "$restaurant_id",
            "total_calls": {"$sum": 1},
            "total_cost_cents": {"$sum": "$cost_total_cents"},
            "total_voice_cost_cents": {"$sum": "$cost_twilio_voice_cents"},
            "total_sms_cost_cents": {"$sum": "$cost_twilio_sms_cents"},
            "total_gemini_cost_cents": {"$sum": "$cost_gemini_extract_cents"},
            "total_revenue_cents": {"$sum": "$order_total"},
            "total_duration_seconds": {"$sum": "$duration_seconds_twilio"},
            "total_sms_count": {"$sum": "$twilio_sms_count"},
        }},
        {"$sort": {"total_cost_cents": -1}},
    ]

    results = await db.call_records.aggregate(pipeline).to_list(500)

    # Enrich with restaurant names
    restaurant_ids = [r["_id"] for r in results if r["_id"]]
    import asyncio as _asyncio
    _name_results = await _asyncio.gather(
        db.restaurants.find({"id": {"$in": restaurant_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500),
        db.clinics.find({"id": {"$in": restaurant_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500),
        db.salons.find({"id": {"$in": restaurant_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500),
        db.home_services.find({"id": {"$in": restaurant_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500),
        db.legal.find({"id": {"$in": restaurant_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500),
    )
    restaurants = [r for res in _name_results for r in res]
    name_map = {r["id"]: r["name"] for r in restaurants}

    # Overall totals
    overall = {
        "total_calls": sum(r["total_calls"] for r in results),
        "total_cost_dollars": sum(r.get("total_cost_cents", 0) for r in results) / 100,
        "total_revenue_dollars": sum(r.get("total_revenue_cents", 0) or 0 for r in results) / 100,
        "total_sms_sent": sum(r.get("total_sms_count", 0) for r in results),
        "avg_cost_per_call_cents": (
            sum(r.get("total_cost_cents", 0) for r in results) / sum(r["total_calls"] for r in results)
            if results else 0
        ),
    }
    overall["gross_margin_pct"] = (
        ((overall["total_revenue_dollars"] - overall["total_cost_dollars"]) / overall["total_revenue_dollars"] * 100)
        if overall["total_revenue_dollars"] > 0 else 0
    )

    per_restaurant = [
        {
            "restaurant_id": r["_id"],
            "restaurant_name": name_map.get(r["_id"], "Unknown"),
            "total_calls": r["total_calls"],
            "cost_dollars": round(r.get("total_cost_cents", 0) / 100, 4),
            "revenue_dollars": round((r.get("total_revenue_cents", 0) or 0) / 100, 2),
            "voice_cost_dollars": round(r.get("total_voice_cost_cents", 0) / 100, 4),
            "sms_cost_dollars": round(r.get("total_sms_cost_cents", 0) / 100, 4),
            "gemini_cost_dollars": round(r.get("total_gemini_cost_cents", 0) / 100, 6),
            "sms_count": r.get("total_sms_count", 0),
            "avg_duration_seconds": round(
                r.get("total_duration_seconds", 0) / r["total_calls"]
                if r["total_calls"] > 0 else 0, 1
            ),
        }
        for r in results
    ]

    return {
        "period_days": days,
        "overall": overall,
        "per_restaurant": per_restaurant,
    }

@app.websocket("/api/twilio/media-stream")
async def twilio_media_stream(websocket: WebSocket):
    await websocket.accept()
    register_active_websocket(websocket)

    try:
        # Read messages to get stream_sid and call_sid
        # Twilio sends: 'connected' first, then 'start' with callSid
        stream_sid = ""
        call_sid = ""
        while not call_sid:
            msg = await websocket.receive_json()
            event = msg.get("event", "")
            if event == "start":
                stream_sid = msg.get("streamSid", "")
                call_sid = msg.get("start", {}).get("callSid", "")
            elif event == "connected":
                continue
            else:
                break

        logger.info(f"Media stream started: stream={stream_sid} call={call_sid}")

        # All data was pre-fetched during POST /twilio/incoming — just read it
        active_call = await db.active_calls.find_one({"call_sid": call_sid}, {"_id": 0})
        if not active_call:
            logger.error(f"No active call found for SID {call_sid}")
            await websocket.close()
            return

        restaurant_id = active_call["restaurant_id"]
        system_prompt = active_call.get("system_prompt", "")
        restaurant = active_call.get("restaurant", {})
        config = active_call.get("config", {})
        menu_items = active_call.get("menu_items", [])

        # ── Create isolated call session for order tracking ──
        services = active_call.get("services", [])
        session = CallSession(
            call_sid=call_sid,
            restaurant_id=restaurant_id,
            caller_number=active_call.get("caller_number", ""),
            restaurant=restaurant,
            config=config or {},
            menu_items=menu_items,
            services=services,
        )

        async def on_call_complete(call_sid, restaurant_id, transcript, session=None):
            """Save full call record including extracted order and quality eval."""
            try:
                # Use session data if available (has order + quality eval)
                if session:
                    record_data = session.build_final_call_record()
                    order_data = record_data.get("order")
                    order_total = record_data.get("order_total", 0)
                    quality_eval = record_data.get("quality_eval", {})
                    quality_score = quality_eval.get("rule_based_score", 85)
                    status = record_data.get("status", "COMPLETED")
                    escalated = record_data.get("escalated_to_human", False)
                    contained = record_data.get("contained_by_ai", True)
                else:
                    order_data = None
                    order_total = 0
                    quality_score = 85
                    status = "COMPLETED"
                    escalated = False
                    contained = True

                # Run AI analysis on transcript
                analysis = await analyse_call_transcript(transcript, order_data, menu_items)

                call = CallRecord(
                    restaurant_id=restaurant_id,
                    twilio_call_sid=call_sid,
                    caller_number=active_call.get("caller_number", ""),
                    caller_name=record_data.get("caller_name") if session else None,
                    started_at=active_call.get("started_at", datetime.now(timezone.utc).isoformat()),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=len(transcript) * 8,
                    status=status,
                    contained_by_ai=contained,
                    escalated_to_human=escalated,
                    transcript=transcript,
                    order_json=order_data,
                    quality_score=analysis.get("quality_score", quality_score),
                    analysis_json={**analysis, "rule_eval": quality_eval if session else {}},
                    order_total=order_total,
                )
                await db.call_records.insert_one(call.model_dump())
                await db.active_calls.delete_one({"call_sid": call_sid})
                logger.info(f"[{call_sid}] Call record saved. Order total: ${order_total/100:.2f}")
                
                # Send WebSocket notification for completed call
                try:
                    from websocket_notifications import notify_new_call, notify_new_order
                    await notify_new_call(
                        restaurant_id=restaurant_id,
                        call_sid=call_sid,
                        caller_number=active_call.get("caller_number", ""),
                        caller_name=record_data.get("caller_name") if session else None,
                        status=status,
                        order_total=order_total,
                    )
                    if order_total > 0 and order_data:
                        await notify_new_order(
                            restaurant_id=restaurant_id,
                            order_id=call_sid,
                            total=order_total,
                            order_type=order_data.get("type", "pickup"),
                            items_count=len(order_data.get("items", [])),
                        )
                except Exception as e:
                    logger.warning(f"Could not send WebSocket notification: {e}")
                
                # Send SMS confirmation
                sms_enabled = config.get("sms_enabled", True) if config else True
                sms_payment_enabled = config.get("sms_payment_enabled", False) if config else False

                if sms_enabled and session and session.order.items:
                    payment_link = None
                    if sms_payment_enabled and order_total > 0:
                        payment_link = await create_stripe_payment_link(
                            order_total_cents=order_total,
                            restaurant_name=restaurant.get("name", "the restaurant"),
                            call_sid=call_sid,
                        )
                    await send_order_sms(
                        caller_number=active_call.get("caller_number", ""),
                        order=session.order,
                        restaurant_name=restaurant.get("name", "the restaurant"),
                        prep_time_minutes=restaurant.get("avg_prep_time_minutes", 20),
                        payment_link=payment_link,
                    )
                    if session:
                        session._sms_count += 1
            except Exception as e:
                logger.error(f"[{call_sid}] on_call_complete error: {e}", exc_info=True)

        if is_pipeline_available():
            await create_call_pipeline(
                websocket=websocket,
                system_prompt=system_prompt,
                restaurant_id=restaurant_id,
                call_sid=call_sid,
                stream_sid=stream_sid,
                on_call_complete=on_call_complete,
                session=session,
                voice=config.get("voice_id") if config else None,
            )
        else:
            logger.warning("Pipecat pipeline not available — closing WebSocket")
            await websocket.close()

    except Exception as e:
        logger.error(f"Media stream error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        unregister_active_websocket(websocket)


# ============================================================
# BILLING / INTEGRATIONS
# ============================================================

@api_router.post("/billing/create-checkout-session")
async def create_checkout_session(payload: BillingCheckoutRequest, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant = await ensure_restaurant_access(payload.restaurant_id, user)

    if not stripe.api_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured")

    frontend_url = get_frontend_url()
    price_id = payload.price_id or os.environ.get("STRIPE_DEFAULT_PRICE_ID")
    if not price_id:
        raise HTTPException(status_code=400, detail="Stripe price is not configured")

    customer_id = restaurant.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            email=restaurant.get("billing_email") or restaurant.get("owner_email"),
            name=restaurant.get("owner_name") or restaurant.get("name"),
            metadata={"restaurant_id": restaurant["id"]},
        )
        customer_id = customer["id"]
        _m = await db.memberships.find_one({"restaurant_id": restaurant["id"], "user_id": user["id"]}, {"_id": 0})
        _bt = _m.get("business_type", "restaurant") if _m else "restaurant"
        await get_business_collection(_bt).update_one(
            {"id": restaurant["id"]},
            {"$set": {"stripe_customer_id": customer_id, "billing_status": "pending"}}
        )

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{frontend_url}/settings?billing=success",
        cancel_url=f"{frontend_url}/settings?billing=cancelled",
        metadata={"restaurant_id": restaurant["id"]},
    )

    return {"checkout_url": session.url}


@api_router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(status_code=400, detail="Stripe webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        restaurant_id = data.get("metadata", {}).get("restaurant_id")
        subscription_id = data.get("subscription")
        customer_id = data.get("customer")
        if restaurant_id:
            for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
                await _coll.update_one(
                    {"id": restaurant_id},
                    {"$set": {
                        "stripe_customer_id": customer_id,
                        "stripe_subscription_id": subscription_id,
                        "billing_status": "active",
                        "plan": "GROWTH",
                    }}
                )

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        subscription_id = data.get("id")
        customer_id = data.get("customer")
        status = data.get("status")
        for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
            await _coll.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {
                    "stripe_subscription_id": subscription_id,
                    "billing_status": status,
                }}
            )

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
            await _coll.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {"billing_status": "canceled"}}
            )

    return JSONResponse({"received": True})


@api_router.get("/integrations/square/connect")
async def square_connect(restaurant_id: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    application_id = os.environ.get("SQUARE_APPLICATION_ID", "")
    redirect_uri = os.environ.get("SQUARE_REDIRECT_URI", "")
    if not application_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="Square credentials are not configured")
    connect_url = (
        "https://connect.squareup.com/oauth2/authorize"
        f"?client_id={application_id}&scope=ITEMS_READ+ORDERS_READ+PAYMENTS_READ"
        f"&session=false&state={restaurant_id}&redirect_uri={redirect_uri}"
    )
    return {"connect_url": connect_url}


@api_router.get("/integrations/square/callback")
async def square_callback(code: Optional[str] = None, state: Optional[str] = None):
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Square authorization response")
    await db.integrations.update_one(
        {"provider": "square", "restaurant_id": state},
        {"$set": {
            "provider": "square",
            "restaurant_id": state,
            "status": "connected",
            "auth_code": code,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
        await _coll.update_one({"id": state}, {"$set": {"square_connected": True}})
    return {"connected": True, "restaurant_id": state}


@api_router.post("/webhooks/square")
async def square_webhook(request: Request):
    payload = await request.body()
    logger.info("Received Square webhook", extra={"payload_size": len(payload)})
    return JSONResponse({"received": True})


# ============================================================
# AI STATUS / SERVICE HEALTH ENDPOINT
# ============================================================

@api_router.get("/status")
async def get_service_status():
    test_mode = get_test_mode_status()
    return {
        "api": "operational",
        "mode": test_mode["mode"],
        "gemini": {
            "available": is_gemini_available(),
            "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        },
        "twilio": {
            "available": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
            "phone_number": os.environ.get("TWILIO_PHONE_NUMBER"),
            "status": test_mode["integrations"]["twilio"]["status"],
        },
        "stripe": {
            "status": test_mode["integrations"]["stripe"]["status"],
            "configured": test_mode["integrations"]["stripe"]["configured"],
        },
        "clerk": {
            "status": test_mode["integrations"]["clerk"]["status"],
            "configured": test_mode["integrations"]["clerk"]["configured"],
        },
        "pipecat_pipeline": {
            "available": is_pipeline_available(),
        },
        "database": {
            "available": True,
            "type": "MongoDB",
        },
    }


# ============================================================
# RE-ANALYSE A CALL
# ============================================================

@api_router.post("/calls/{call_id}/analyse")
async def reanalyse_call(call_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    call = await db.call_records.find_one({"id": call_id}, {"_id": 0})
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    await ensure_restaurant_access(call["restaurant_id"], user)

    menu_items = await db.menu_items.find(
        {"restaurant_id": call["restaurant_id"], "available": True}, {"_id": 0}
    ).to_list(500)

    analysis = await analyse_call_transcript(
        transcript=call.get("transcript", []),
        order_json=call.get("order_json"),
        menu_items=menu_items,
    )

    await db.call_records.update_one(
        {"id": call_id},
        {"$set": {"analysis_json": analysis, "quality_score": analysis.get("quality_score")}},
    )
    return {"message": "Analysis complete", "analysis": analysis}


# ============================================================
# TEST MODE ENDPOINTS
# ============================================================

@api_router.get("/test-mode/status")
async def get_test_mode():
    return get_test_mode_status()


@api_router.get("/test-mode/scenarios")
async def get_test_call_scenarios():
    return {"scenarios": get_test_scenarios()}


@api_router.post("/test-mode/run-scenario")
async def run_test_scenario(
    restaurant_id: str = Query(...),
    scenario_id: int = Query(0),
    user: Dict[str, Any] = Depends(get_current_user),
):
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    scenario = get_scenario_by_id(scenario_id)
    if not scenario:
        raise HTTPException(status_code=400, detail="Invalid scenario ID")

    menu_items = await db.menu_items.find(
        {"restaurant_id": restaurant_id, "available": True}, {"_id": 0}
    ).to_list(100)

    _biz_doc = await db.restaurants.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1})
    if not _biz_doc:
        import asyncio as _asyncio
        _biz_results = await _asyncio.gather(
            db.clinics.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
            db.salons.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
            db.home_services.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
            db.legal.find_one({"id": restaurant_id}, {"_id": 0, "business_type": 1}),
        )
        _biz_doc = next((r for r in _biz_results if r), None)
    business_type = _biz_doc.get("business_type", "restaurant") if _biz_doc else "restaurant"
    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    
    # For appointment businesses, get services instead of menu items
    services = []
    if business_type in ("clinic", "salon", "home_services", "legal"):
        services = await db.services.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

    # Pre-fetch current availability for appointment businesses.
    # Queries db.appointments + db.blocked_slots fresh at call start —
    # so open, booked, and blocked slots are all accurate at the moment of this call.
    cached_availability = None
    if business_type in ("clinic", "salon", "home_services", "legal"):
        logger.info(f"[{call_sid}] Starting availability pre-fetch for {business_type}")
        try:
            from appointment_service import pre_fetch_availability
            cached_availability = await pre_fetch_availability(
                restaurant_id=restaurant_id,
                services=services,
                config={**(config or {}), "timezone": restaurant.get("timezone", "UTC")},
                db=db,
                days_ahead=7,
            )
            logger.info(
                f"[{call_sid}] Availability pre-fetched: "
                f"{sum(len(v) for v in cached_availability.values())} total open slots "
                f"across {len(cached_availability)} days"
            )
        except Exception as _e:
            logger.warning(f"[{call_sid}] Availability pre-fetch failed (non-fatal): {_e}")

    # Use system prompt router for correct prompt by business type
    from gemini_service import get_system_prompt
    system_prompt = get_system_prompt(
        business_type=business_type,
        restaurant_name=restaurant.get("name", "the restaurant"),
        cuisine_type=restaurant.get("cuisine_type", ""),
        persona=config.get("persona", "friendly") if config else "friendly",
        business_rules=config.get("business_rules", []) if config else [],
        escalation_rules=config.get("escalation_rules", []) if config else [],
        menu_items=menu_items,
        disclosure_text=config.get("disclosure_text", "Hi! How can I help you?") if config else "Hi! How can I help you?",
        upsell_enabled=config.get("upsell_enabled", True) if config else True,
        delivery_enabled=restaurant.get("delivery_enabled", config.get("delivery_enabled", True) if config else True),
        delivery_minimum=config.get("delivery_minimum", 1500),
        operating_hours=config.get("operating_hours"),
        restaurant_timezone=restaurant.get("timezone", "UTC"),
        restaurant_address=restaurant.get("address"),
        services=services,  # For appointment businesses
    )

    transcript = []
    timestamp_counter = 0

    greeting = await get_conversation_response(system_prompt, [], "")
    transcript.append({
        "role": "ai",
        "text": greeting or f"Hi! I'm the AI assistant for {restaurant.get('name')}. How can I help you?",
        "timestamp": f"00:{timestamp_counter:02d}",
    })
    timestamp_counter += 3

    for customer_msg in scenario["messages"]:
        transcript.append({
            "role": "customer",
            "text": customer_msg,
            "timestamp": f"00:{timestamp_counter:02d}",
        })
        timestamp_counter += 2

        ai_response = await get_conversation_response(system_prompt, transcript, customer_msg)
        transcript.append({
            "role": "ai",
            "text": ai_response or "I'd be happy to help with that!",
            "timestamp": f"00:{timestamp_counter:02d}",
        })
        timestamp_counter += 3

    order_items = []
    total = 0
    for item_name in scenario.get("expected_items", []):
        menu_item = next((m for m in menu_items if item_name.lower() in m["name"].lower()), None)
        if menu_item:
            price = menu_item.get("price", 999)
            order_items.append({
                "name": menu_item["name"],
                "quantity": 1,
                "price": price,
                "modifiers": [],
                "subtotal": price,
            })
            total += price

    order_json = {
        "items": order_items,
        "total": total,
        "type": scenario.get("order_type", "pickup"),
        "special_instructions": "",
    } if order_items else None

    analysis = await analyse_call_transcript(transcript, order_json, menu_items)

    now = datetime.now(timezone.utc)
    call = CallRecord(
        restaurant_id=restaurant_id,
        caller_number=f"+1555{random.randint(1000000, 9999999)}",
        caller_name=scenario["caller_name"],
        started_at=now.isoformat(),
        ended_at=(now + timedelta(seconds=timestamp_counter)).isoformat(),
        duration_seconds=timestamp_counter,
        status="ESCALATED" if scenario.get("order_type") == "escalation" else "COMPLETED",
        contained_by_ai=scenario.get("order_type") != "escalation",
        escalated_to_human=scenario.get("order_type") == "escalation",
        transcript=transcript,
        order_json=order_json,
        quality_score=analysis.get("quality_score", 85),
        analysis_json=analysis,
        order_total=total,
    )

    await db.call_records.insert_one(call.model_dump())

    return {
        "call": call.model_dump(),
        "scenario": {"id": scenario_id, "name": scenario["name"]},
        "ai_powered": is_gemini_available(),
    }


# ============================================================
# CLOUDFLARE SECURITY MIDDLEWARE
# ============================================================
CF_SECRET_TOKEN = os.environ.get("CF_SECRET_TOKEN", "")
CF_BYPASS_PREFIXES = ["/api/twilio", "/api/call", "/health"]

@app.middleware("http")
async def cloudflare_security_middleware(request: Request, call_next):
    cf_ip = request.headers.get("CF-Connecting-IP")
    request.state.client_ip = cf_ip if cf_ip else request.client.host

    if CF_SECRET_TOKEN:
        path = request.url.path
        if not any(path.startswith(p) for p in CF_BYPASS_PREFIXES):
            if request.headers.get("CF-Secret-Token", "") != CF_SECRET_TOKEN:
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    return await call_next(request)

# ============================================================
# CORS MIDDLEWARE
# ============================================================

cors_origins = get_cors_origins()
cors_origin_regex = os.environ.get("CORS_ORIGIN_REGEX")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex if cors_origin_regex else None,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# INCLUDE ROUTER
# ============================================================

app.include_router(api_router)


# ============================================================
# WEBSOCKET NOTIFICATION ENDPOINT
# ============================================================

@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, restaurant_id: Optional[str] = None):
    from websocket_notifications import manager
    await manager.connect(websocket, restaurant_id)
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connected for real-time notifications",
            "restaurant_id": restaurant_id,
        })
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(websocket)


@app.on_event("startup")
async def startup_scheduler():
    """Start background scheduler on app startup."""
    try:
        from scheduler_service import start_scheduler
        start_scheduler(db)
        logger.info("Background scheduler started")
    except Exception as e:
        logger.warning(f"Could not start scheduler: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    """Clean up on shutdown."""
    try:
        from scheduler_service import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    client.close()