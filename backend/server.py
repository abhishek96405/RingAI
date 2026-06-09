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
import hmac
import hashlib
import html
import base64
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Set
from bson import ObjectId
import uuid
import random
from datetime import datetime, timezone, timedelta
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


# ============================================================
# PLAN CONFIGURATION — SINGLE SOURCE OF TRUTH
# ============================================================

PLAN_CONFIG = {
    "STARTER": {
        "price_env": "STRIPE_PRICE_STARTER",
        "monthly_call_limit": 500,
        "overage_per_call_cents": 25,
        "max_call_duration_sec": 180,
        "warn_at_sec": 150,
        "phone_numbers": 1,
        "delivery_enabled": False,
        "reservations_enabled": False,
        "upsell_enabled": False,
        "customer_recognition": False,
        "auto_learning": False,
        "multi_language": False,
        "multi_voice": False,
        "prepayment_fee_pct": 1.0,
    },
    "PRO": {
        "price_env": "STRIPE_PRICE_PRO",
        "monthly_call_limit": 1000,
        "overage_per_call_cents": 20,
        "max_call_duration_sec": None,
        "warn_at_sec": None,
        "phone_numbers": 1,
        "delivery_enabled": True,
        "reservations_enabled": True,
        "upsell_enabled": True,
        "customer_recognition": True,
        "auto_learning": True,
        "multi_language": True,
        "multi_voice": True,
        "prepayment_fee_pct": 1.0,
    },
}


def get_plan_features(plan_name: str) -> dict:
    """Get feature config for a plan. Defaults to STARTER if unknown."""
    return PLAN_CONFIG.get(plan_name, PLAN_CONFIG["STARTER"])


def get_price_id_to_plan_map() -> dict:
    """Reverse lookup: Stripe Price ID -> plan name."""
    mapping = {}
    for plan_name, config in PLAN_CONFIG.items():
        price_id = os.environ.get(config["price_env"], "")
        if price_id:
            mapping[price_id] = plan_name
    return mapping


# ============================================================
# GRACEFUL SHUTDOWN
# ============================================================
_active_websockets: Set[WebSocket] = set()
_shutdown_requested = False

# In-process registry for live CallSession objects, keyed on A-leg
# call_control_id (== CallSession.call_sid == db.active_calls.call_sid ==
# payload.call_control_id in every Telnyx webhook). Lets webhook handlers
# reach the live session for events like call.bridged. Process-local;
# horizontal scaling would need a Redis pub/sub layer in front of this.
_ACTIVE_SESSIONS: Dict[str, Any] = {}

def register_call_session(call_sid: str, session: Any) -> None:
    _ACTIVE_SESSIONS[call_sid] = session

def unregister_call_session(call_sid: str) -> None:
    _ACTIVE_SESSIONS.pop(call_sid, None)

def get_call_session(call_sid: str) -> Optional[Any]:
    return _ACTIVE_SESSIONS.get(call_sid)

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


SENSITIVE_FIELDS = {
    "clover_api_token", "clover_merchant_id", "square_access_token", "square_location_id",
    "toast_client_id", "toast_client_secret", "toast_restaurant_guid",
    "google_calendar_tokens",
}

def strip_sensitive_fields(doc: dict) -> dict:
    """Remove sensitive POS credentials from restaurant documents before returning to client."""
    if not doc:
        return doc
    return {k: v for k, v in doc.items() if k not in SENSITIVE_FIELDS}

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

# --- Error monitoring (Sentry) ---
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            release=os.environ.get("RENDER_GIT_COMMIT"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            send_default_pii=False,
        )
        logging.getLogger(__name__).info("Sentry initialized (env=%s)", os.environ.get("SENTRY_ENVIRONMENT", "production"))
    except Exception as _sentry_err:
        logging.getLogger(__name__).warning("Sentry init skipped: %s", _sentry_err)

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
    calculate_is_open,
)
from call_pipeline import (
    is_pipeline_available,
    create_call_pipeline,
    generate_twiml_stream_response,
    CallSession,
)

from auth_helpers import verify_clerk_token
from pos_sync import sync_menu_from_pos

# New imports for security, rate limiting, and features
from security_middleware import (
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    sanitize_mongo_query,
    sanitize_string_input,
    redact_for_logging,
    safe_log_error,
    get_secure_cors_origins,
)
from rate_limiting import (
    limiter,
    rate_limit_exceeded_handler,
    LIMIT_AUTH,
    LIMIT_RESTAURANT_READ,
    LIMIT_RESTAURANT_WRITE,
    LIMIT_MENU_READ,
    LIMIT_MENU_BULK,
    LIMIT_ANALYTICS,
    LIMIT_POS_CREDENTIALS,
    check_ws_connection_limit,
    register_ws_connection,
    unregister_ws_connection,
)
from encryption_utils import (
    encrypt_sensitive_fields,
    decrypt_sensitive_fields,
    ENCRYPTED_CREDENTIAL_FIELDS,
    mask_for_display,
)
from toast_integration import (
    sync_menu_from_toast,
    send_order_to_toast,
    get_toast_queue_depth,
    test_toast_connection,
    clear_toast_token_cache,
)
from reservation_service import (
    ReservationStatus,
    create_reservation_doc,
    get_reservation_settings,
    get_reservation_slots,
    check_reservation_availability,
    extract_reservation_from_transcript,
    dispatch_reservation,
    build_reservation_prompt_block,
)
from eta_service import (
    calculate_dynamic_eta,
    format_eta_for_speech,
    get_item_prep_time,
)

try:
    from payment_service import send_order_confirmation_sms
    _PAYMENT_SERVICE_AVAILABLE = True
except ImportError:
    _PAYMENT_SERVICE_AVAILABLE = False
    logging.getLogger(__name__).warning("payment_service not available — SMS payment links disabled")

try:
    from auto_learning_service import AutoLearningService, get_learning_service
    _LEARNING_SERVICE_AVAILABLE = True
except ImportError:
    _LEARNING_SERVICE_AVAILABLE = False
    logging.getLogger(__name__).warning("auto_learning_service not available — AI learning disabled")

from slowapi.errors import RateLimitExceeded

from oauth_state_service import issue_oauth_state, consume_oauth_state

try:
    from test_mode import (
        get_test_mode_status,
        get_test_scenarios,
        get_scenario_by_id,
        is_sandbox_mode,
        SAMPLE_CUSTOMER_SCENARIOS,
    )
    _TEST_MODE_AVAILABLE = True
except ImportError:
    _TEST_MODE_AVAILABLE = False
    logging.getLogger(__name__).warning("test_mode not available")

# Create the main app
app = FastAPI(title="RingAI API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Add rate limiting state to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# CORS middleware MUST be added FIRST (Starlette LIFO means it runs LAST in request, FIRST in response)
# This ensures preflight OPTIONS requests are handled before other middleware
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",") if os.environ.get("CORS_ORIGINS") else ["*"]
cors_origin_regex = os.environ.get("CORS_ORIGIN_REGEX")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex if cors_origin_regex else None,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middleware (runs after CORS)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)

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

    # Business type for horizontal platform support
    # "restaurant" | "clinic" | "salon" | "home_services" | "legal"
    business_type: str = "restaurant"

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
    offers_delivery: bool = True
    offers_reservations: bool = True
    delivery_enabled: bool = True
    delivery_fee: int = 0
    delivery_radius_miles: float = 5.0
    delivery_zip_codes: List[str] = []
    delivery_eta_offset_minutes: int = 15
    dine_in_enabled: bool = True
    reservations_enabled: bool = False
    catering_enabled: bool = False
    avg_prep_time_minutes: int = 20
    reservation_party_limit: int = 8
    reservation_slot_duration: int = 30
    reservation_max_per_slot: int = 5
    reservation_advance_booking_days: int = 7

    # POS integration
    pos_type: Optional[str] = None  # "clover", "square", "toast", or None
    pos_env: Optional[str] = "sandbox"  # "sandbox" or "production"
    last_pos_sync: Optional[str] = None
    clover_api_token: Optional[str] = None
    clover_merchant_id: Optional[str] = None
    square_access_token: Optional[str] = None
    square_location_id: Optional[str] = None
    # Toast POS credentials
    toast_client_id: Optional[str] = None
    toast_client_secret: Optional[str] = None
    toast_restaurant_guid: Optional[str] = None
    # SMS payment link option
    prepayment_enabled: bool = False
    # Stripe Connect (order prepayment)
    stripe_account_id: Optional[str] = None
    stripe_connect_status: Optional[str] = None  # "pending" | "active" | "disconnected"
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
    offers_delivery: Optional[bool] = None
    offers_reservations: Optional[bool] = None
    delivery_enabled: Optional[bool] = None
    delivery_fee: Optional[int] = None
    delivery_radius_miles: Optional[float] = None
    delivery_zip_codes: Optional[List[str]] = None
    delivery_eta_offset_minutes: Optional[int] = None
    dine_in_enabled: Optional[bool] = None
    reservations_enabled: Optional[bool] = None
    catering_enabled: Optional[bool] = None
    avg_prep_time_minutes: Optional[int] = None
    reservation_party_limit: Optional[int] = None
    reservation_slot_duration: Optional[int] = None
    reservation_max_per_slot: Optional[int] = None
    reservation_advance_booking_days: Optional[int] = None

    status: Optional[str] = None
    onboarding_step: Optional[int] = None
    is_active: Optional[bool] = None

    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_status: Optional[str] = None
    phone_number_id: Optional[str] = None
    square_connected: Optional[bool] = None
    onboarding_completed_at: Optional[str] = None
    pos_type: Optional[str] = None
    pos_env: Optional[str] = None
    last_pos_sync: Optional[str] = None
    clover_api_token: Optional[str] = None
    clover_merchant_id: Optional[str] = None
    square_access_token: Optional[str] = None
    square_location_id: Optional[str] = None
    # Toast POS credentials
    toast_client_id: Optional[str] = None
    toast_client_secret: Optional[str] = None
    toast_restaurant_guid: Optional[str] = None
    # SMS payment link option
    prepayment_enabled: Optional[bool] = None
    # Stripe Connect (order prepayment)
    stripe_account_id: Optional[str] = None
    stripe_connect_status: Optional[str] = None


class Restaurant(RestaurantBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_active: bool = False
    plan: str = "STARTER"
    billing_status: str = "none"
    trial_ends_at: Optional[str] = None
    monthly_call_count: int = 0

    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    phone_number_id: Optional[str] = None
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
    plan: Optional[str] = None
    price_id: Optional[str] = None
    source: Optional[str] = None


class TelnyxProvisionRequest(BaseModel):
    restaurant_id: str
    area_code: Optional[str] = None    # search if no phone_number given
    phone_number: Optional[str] = None  # exact number from search results, E.164


class TelnyxAssignNumberRequest(BaseModel):
    restaurant_id: str
    phone_number: str  # must already be owned by the Telnyx account


class TelnyxReleaseRequest(BaseModel):
    restaurant_id: str
    phone_number_id: Optional[str] = None  # defaults to restaurant's current number


class TelnyxSearchResponse(BaseModel):
    available: List[Dict[str, Any]]
    count: int


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
    multilingual_enabled: bool = False
    additional_languages: List[str] = []

    business_rules: List[str] = []
    few_shot_examples: List[Dict] = []
    escalation_rules: List[str] = []

    upsell_enabled: bool = True
    disclosure_text: str = "Hi! I'm an AI assistant. How can I help you today?"
    delivery_enabled: bool = True
    delivery_minimum: int = 1500

    after_hours_mode: str = "voicemail"
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

    # Reservation settings (restaurants)
    reservation_max_party_size: int = 8
    reservation_min_party_size: int = 1
    reservation_advance_booking_days: int = 30
    reservation_slot_duration_minutes: int = 90
    reservation_capacity_per_slot: int = 10
    reservation_blackout_dates: List[str] = []  # ["2025-12-25", "2026-01-01"]
    reservation_special_hours: Dict[str, Any] = {}  # {"2025-12-24": {"open": "16:00", "close": "20:00"}}


class RestaurantConfigUpdate(BaseModel):
    business_type: Optional[str] = None

    persona: Optional[str] = None
    voice_id: Optional[str] = None
    primary_language: Optional[str] = None
    multilingual_enabled: Optional[bool] = None
    additional_languages: Optional[List[str]] = None

    business_rules: Optional[List[str]] = None
    escalation_rules: Optional[List[str]] = None
    sms_enabled: Optional[bool] = None
    sms_payment_enabled: Optional[bool] = None

    upsell_enabled: Optional[bool] = None
    disclosure_text: Optional[str] = None
    delivery_enabled: Optional[bool] = None
    delivery_minimum: Optional[int] = None

    after_hours_mode: Optional[str] = None
    escalation_phone_number: Optional[str] = None
    operating_hours: Optional[Dict[str, Any]] = None

    google_calendar_tokens: Optional[Dict[str, Any]] = None
    google_calendar_id: Optional[str] = None

    slot_capacity: Optional[int] = None
    slot_interval_minutes: Optional[int] = None

    # Reservation settings (restaurants)
    reservation_max_party_size: Optional[int] = None
    reservation_min_party_size: Optional[int] = None
    reservation_advance_booking_days: Optional[int] = None
    reservation_slot_duration_minutes: Optional[int] = None
    reservation_capacity_per_slot: Optional[int] = None
    reservation_blackout_dates: Optional[List[str]] = None
    reservation_special_hours: Optional[Dict[str, Any]] = None


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
    prep_time_minutes: Optional[int] = None  # Item-level prep time for dynamic ETA
    aliases: List[str] = []  # Auto-learned alternative names (e.g., "coke" → "Coca-Cola")


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
    prep_time_minutes: Optional[int] = None  # Item-level prep time


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
    call_sid: str = Field(default_factory=lambda: f"CA{uuid.uuid4().hex[:32]}")
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
    cost_voice_cents: Optional[float] = None   # $0.0085/min inbound
    cost_sms_cents: Optional[float] = None     # $0.0083/message
    cost_gemini_live_cents: Optional[float] = None    # $0 now (free preview), track duration for future
    cost_gemini_extract_cents: Optional[float] = None # $0.075/1M input + $0.30/1M output
    cost_gemini_tts_cents: Optional[float] = None     # voice preview calls
    cost_total_cents: Optional[float] = None          # sum of all above
    gemini_extract_tokens: Optional[int] = None       # input + output tokens from extraction
    sms_count: int = 0                         # number of SMS sent this call
    duration_seconds_actual: Optional[int] = None     # exact from telephony status callback


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
        raise HTTPException(status_code=404, detail="Restaurant not found")
    business_type = membership.get("business_type", "restaurant")
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return strip_sensitive_fields(restaurant)


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
            restaurants.extend([strip_sensitive_fields(doc) for doc in r])

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
    # Removed: previously iterated every business collection and granted the
    # caller owner-membership on every restaurant where they had no row,
    # which let any authenticated user take ownership of every unowned
    # tenant in the database. Restoring memberships must go through an
    # admin-authenticated path that verifies the user's prior Clerk org
    # membership; until that exists, the route is permanently gone.
    raise HTTPException(
        status_code=410,
        detail="This endpoint has been removed. Contact support to restore memberships.",
    )


async def select_restaurant(data: RestaurantSelection, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant = await ensure_restaurant_access(data.restaurant_id, user)
    return {"active_restaurant": restaurant}


# ============================================================
# RESTAURANT ENDPOINTS
# ============================================================

@api_router.post("/restaurants", response_model=Restaurant)
async def create_restaurant(data: RestaurantCreate, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant_data = data.model_dump()

    # Normalize the two phones now stored on the Restaurant document so that
    # the distinctness check (and downstream lookups) compare canonical forms.
    from security_utils import normalize_e164, validate_phones_distinct
    for field in ("phone_number", "business_phone"):
        raw = restaurant_data.get(field)
        if raw:
            try:
                restaurant_data[field] = normalize_e164(raw)
            except ValueError:
                # Leave the raw value; field-level validation lives elsewhere.
                pass
    try:
        validate_phones_distinct(
            restaurant_data.get("phone_number"),
            restaurant_data.get("business_phone"),
            None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Auto-detect timezone from address if not explicitly set
    if restaurant_data.get("address") and restaurant_data.get("timezone") == "America/Chicago":
        detected_tz = await auto_detect_timezone(restaurant_data["address"])
        if detected_tz:
            restaurant_data["timezone"] = detected_tz

    business_type = restaurant_data.get("business_type", "restaurant")

    # Resume an in-progress onboarding instead of creating a parallel record.
    # If this owner already has a not-yet-activated (draft) restaurant of this
    # business_type, return it — so leaving onboarding and later continuing OR
    # restarting reuses the same restaurant instead of spawning duplicates.
    # Keyed on server state (not the browser), so it holds across cleared
    # storage and device switches. Only resumes drafts (is_active != True),
    # so an already-activated restaurant is never affected.
    existing_memberships = await db.memberships.find(
        {"user_id": user["id"], "role": "owner", "business_type": business_type}, {"_id": 0}
    ).to_list(100)
    existing_ids = [m["restaurant_id"] for m in existing_memberships]
    if existing_ids:
        drafts = await get_business_collection(business_type).find(
            {"id": {"$in": existing_ids}, "is_active": {"$ne": True}}, {"_id": 0}
        ).to_list(100)
        if drafts:
            drafts.sort(key=lambda r: r.get("created_at") or "")
            return strip_sensitive_fields(drafts[-1])   # resume the existing draft

    restaurant = Restaurant(**restaurant_data)
    doc = restaurant.model_dump()
    await get_business_collection(business_type).insert_one(doc)
    membership = Membership(user_id=user["id"], restaurant_id=restaurant.id, role="owner", business_type=business_type)
    await db.memberships.insert_one(membership.model_dump())
    return strip_sensitive_fields(restaurant.model_dump())
@api_router.get("/restaurants")
async def list_restaurants(user: Dict[str, Any] = Depends(get_current_user)):
    payload = await get_bootstrap_payload(user)
    return payload.get("restaurants", [])


@api_router.get("/restaurants/{restaurant_id}")
async def get_restaurant(restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return await ensure_restaurant_access(restaurant_id, user)


@api_router.put("/restaurants/{restaurant_id}")
async def update_restaurant(restaurant_id: str, data: RestaurantUpdate, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    # Also manually preserve integer fields that could be 0 (falsy but valid)
    for field in ("slot_capacity", "slot_interval_minutes", "delivery_minimum"):
        val = getattr(data, field, None)
        if val is not None:
            update_data[field] = val
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Plan-based feature enforcement (restaurant only)
    plan_features = get_plan_features(restaurant.get("plan", "STARTER"))
    if not plan_features["delivery_enabled"]:
        update_data.pop("delivery_enabled", None)
        if "delivery_enabled" in update_data:
            update_data["delivery_enabled"] = False
    if not plan_features["reservations_enabled"]:
        update_data.pop("reservations_enabled", None)
        if "reservations_enabled" in update_data:
            update_data["reservations_enabled"] = False

    # Auto-detect timezone if address changed
    if "address" in update_data and update_data["address"]:
        detected_tz = await auto_detect_timezone(update_data["address"])
        if detected_tz:
            update_data["timezone"] = detected_tz
            logger.info(f"Updated timezone to {detected_tz} for restaurant {restaurant_id}")

    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    coll = get_business_collection(business_type)

    # Phone validation: only when phone_number or business_phone is being changed.
    # Partial updates that don't touch phone fields do not re-validate existing data.
    if "phone_number" in update_data or "business_phone" in update_data:
        from security_utils import normalize_e164, validate_phones_distinct
        for field in ("phone_number", "business_phone"):
            if field in update_data and update_data[field]:
                try:
                    update_data[field] = normalize_e164(update_data[field])
                except ValueError:
                    pass
        post_phone = update_data.get("phone_number", restaurant.get("phone_number"))
        post_business = update_data.get("business_phone", restaurant.get("business_phone"))
        existing_config = await get_config_collection(business_type).find_one(
            {"restaurant_id": restaurant_id}, {"_id": 0}
        )
        existing_escalation = (existing_config or {}).get("escalation_phone_number")
        try:
            validate_phones_distinct(post_phone, post_business, existing_escalation)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    result = await coll.update_one({"id": restaurant_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = await coll.find_one({"id": restaurant_id}, {"_id": 0})
    return strip_sensitive_fields(restaurant)
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
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}

    # Plan-based feature enforcement
    plan_features = get_plan_features(restaurant.get("plan", "STARTER"))
    if not plan_features["upsell_enabled"]:
        update_data.pop("upsell_enabled", None)

    # Phone validation: escalation_phone_number must differ from the
    # restaurant's AI DID and publicly-listed business phone.
    if "escalation_phone_number" in update_data and update_data["escalation_phone_number"]:
        from security_utils import normalize_e164, validate_phones_distinct
        try:
            update_data["escalation_phone_number"] = normalize_e164(update_data["escalation_phone_number"])
        except ValueError:
            pass
        try:
            validate_phones_distinct(
                restaurant.get("phone_number"),
                restaurant.get("business_phone"),
                update_data["escalation_phone_number"],
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
            desc_html = f'<p class="desc">{html.escape(i["description"])}</p>' if i["description"] else ""
            items_html += f"""
            <div class="item">
                <div class="item-header">
                    <span class="item-name">{html.escape(i["name"])}</span>
                    <span class="item-price">{html.escape(str(i["price"]))}</span>
                </div>
                {desc_html}
            </div>"""
        category_html += f"""
        <div class="category">
            <h2>{html.escape(cat_name)}</h2>
            {items_html}
        </div>"""

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(restaurant_name)} Menu</title>
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
        <h1>{html.escape(restaurant_name)}</h1>
        <p>{html.escape(cuisine)} cuisine</p>
    </div>
    <div class="container">
        {category_html}
        <div class="footer">Powered by RingAI</div>
    </div>
</body>
</html>"""

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=page_html)


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
# ============================================================

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
    business = await get_business_collection(business_type).find_one(
        {"id": restaurant_id}, {"_id": 0}
    ) or {}
    config["timezone"] = business.get("timezone", "America/Chicago")
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
    admin_user_id = os.environ.get("ADMIN_USER_ID")
    if not admin_user_id or user.get("id") != admin_user_id:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        from reminder_service import process_appointment_reminders
        result = await process_appointment_reminders(db)
        return result
    except ImportError:
        raise HTTPException(status_code=500, detail="Reminder service not available")


# ============================================================
# RESTAURANT RESERVATION ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/reservations")
@limiter.limit(LIMIT_RESTAURANT_READ)
async def list_reservations(
    request: Request,
    restaurant_id: str,
    status: Optional[str] = None,
    date: Optional[str] = None,  # YYYY-MM-DD
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """List reservations for a restaurant."""
    await ensure_restaurant_access(restaurant_id, user)
    
    query = {"restaurant_id": restaurant_id}
    if status:
        query["status"] = status
    if date:
        query["reservation_date"] = date
    
    total = await db.reservations.count_documents(query)
    reservations = await (
        db.reservations.find(query, {"_id": 0})
        .sort([("reservation_date", 1), ("reservation_time", 1)])
        .skip(offset)
        .limit(limit)
        .to_list(limit)
    )
    
    return {
        "reservations": reservations,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@api_router.get("/reservations/{reservation_id}")
async def get_reservation(reservation_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get a single reservation."""
    reservation = await db.reservations.find_one({"id": reservation_id}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    await ensure_restaurant_access(reservation["restaurant_id"], user)
    return reservation


class ReservationCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    party_size: int
    reservation_date: str  # YYYY-MM-DD
    reservation_time: str  # HH:MM
    special_requests: Optional[str] = None


@api_router.post("/restaurants/{restaurant_id}/reservations")
@limiter.limit(LIMIT_RESTAURANT_WRITE)
async def create_reservation(
    request: Request,
    restaurant_id: str,
    data: ReservationCreate,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new reservation."""
    await ensure_restaurant_access(restaurant_id, user)
    
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0}) or {}
    
    # Check availability
    availability = await check_reservation_availability(
        restaurant_id=restaurant_id,
        date_str=data.reservation_date,
        time_str=data.reservation_time,
        party_size=data.party_size,
        config=config,
        operating_hours=config.get("operating_hours", {}),
        db=db,
        restaurant_timezone=restaurant.get("timezone", "America/Chicago"),
    )
    
    if not availability.get("available"):
        raise HTTPException(
            status_code=400,
            detail=availability.get("reason", "Slot not available"),
        )
    
    # Create reservation
    doc = create_reservation_doc(
        restaurant_id=restaurant_id,
        customer_name=sanitize_string_input(data.customer_name, 100),
        customer_phone=sanitize_string_input(data.customer_phone, 20),
        customer_email=sanitize_string_input(data.customer_email, 100) if data.customer_email else None,
        party_size=data.party_size,
        reservation_date=data.reservation_date,
        reservation_time=data.reservation_time,
        special_requests=sanitize_string_input(data.special_requests, 500) if data.special_requests else None,
    )
    
    await db.reservations.insert_one(doc)
    
    return {"reservation": doc, "message": "Reservation created successfully"}


@api_router.patch("/reservations/{reservation_id}/cancel")
async def cancel_reservation(reservation_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Cancel a reservation."""
    reservation = await db.reservations.find_one({"id": reservation_id}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    await ensure_restaurant_access(reservation["restaurant_id"], user)
    
    await db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {
            "status": ReservationStatus.CANCELLED,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    
    return {"message": "Reservation cancelled", "id": reservation_id}


@api_router.patch("/reservations/{reservation_id}/confirm")
async def confirm_reservation(reservation_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Confirm a pending reservation."""
    reservation = await db.reservations.find_one({"id": reservation_id}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    await ensure_restaurant_access(reservation["restaurant_id"], user)
    
    await db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {
            "status": ReservationStatus.CONFIRMED,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    
    return {"message": "Reservation confirmed", "id": reservation_id}


@api_router.get("/restaurants/{restaurant_id}/reservation-slots")
@limiter.limit(LIMIT_RESTAURANT_READ)
async def get_reservation_slots_endpoint(
    request: Request,
    restaurant_id: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get available reservation slots for a specific date."""
    await ensure_restaurant_access(restaurant_id, user)
    
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    restaurant = await get_business_collection(business_type).find_one({"id": restaurant_id}, {"_id": 0})
    config = await get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0}) or {}
    
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    slots = await get_reservation_slots(
        restaurant_id=restaurant_id,
        date_str=date,
        config=config,
        operating_hours=config.get("operating_hours", {}),
        db=db,
        restaurant_timezone=restaurant.get("timezone", "America/Chicago"),
        restaurant=restaurant,
    )
    return {"date": date, "slots": slots}


# ============================================================
# AUTO-LEARNING ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/learning/stats")
async def get_learning_stats(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get auto-learning statistics for a restaurant."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    if not get_plan_features(restaurant.get("plan", "STARTER"))["auto_learning"]:
        return {"total_calls_processed": 0, "aliases_learned": 0, "calls_flagged": 0, "last_processed_at": None}
    learning_service = get_learning_service(db)
    stats = await learning_service.get_learning_stats(restaurant_id)
    return stats


@api_router.get("/restaurants/{restaurant_id}/learning/flagged-calls")
async def get_flagged_calls(
    restaurant_id: str,
    limit: int = Query(10, ge=1, le=50),
    include_reviewed: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get calls flagged for owner review (low quality scores)."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    if not get_plan_features(restaurant.get("plan", "STARTER"))["auto_learning"]:
        return {"flagged_calls": [], "count": 0}
    learning_service = get_learning_service(db)
    calls = await learning_service.get_flagged_calls(
        restaurant_id, limit, include_reviewed
    )
    return {"flagged_calls": calls, "count": len(calls)}


@api_router.get("/restaurants/{restaurant_id}/learning/aliases")
async def get_learned_aliases(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all auto-learned menu aliases."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    if not get_plan_features(restaurant.get("plan", "STARTER"))["auto_learning"]:
        return {"aliases": [], "count": 0}
    learning_service = get_learning_service(db)
    aliases = await learning_service.get_learned_aliases(restaurant_id)
    return {"aliases": aliases, "count": len(aliases)}


@api_router.get("/restaurants/{restaurant_id}/learning/suggestions")
async def get_pending_suggestions(
    restaurant_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get pending suggestions (aliases not yet applied, rules to review)."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    if not get_plan_features(restaurant.get("plan", "STARTER"))["auto_learning"]:
        return {"menu_suggestions": [], "rule_suggestions": []}
    learning_service = get_learning_service(db)
    suggestions = await learning_service.get_pending_suggestions(restaurant_id)
    return suggestions


class CallReviewAction(BaseModel):
    action: str  # "correct", "incorrect", "ignore"
    notes: Optional[str] = None


@api_router.post("/learning/flagged-calls/{call_id}/review")
async def review_flagged_call(
    call_id: str,
    review: CallReviewAction,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Mark a flagged call as reviewed."""
    # Verify access to the call's restaurant
    flagged = await db.flagged_calls.find_one({"call_id": call_id})
    if not flagged:
        raise HTTPException(status_code=404, detail="Flagged call not found")
    
    await ensure_restaurant_access(flagged["restaurant_id"], user)
    
    learning_service = get_learning_service(db)
    await learning_service.mark_call_reviewed(
        call_id, review.action, review.notes
    )
    return {"message": "Call marked as reviewed", "action": review.action}


@api_router.post("/restaurants/{restaurant_id}/learning/apply-alias")
async def manually_apply_alias(
    restaurant_id: str,
    alias: str = Query(..., description="The alias term (e.g., 'coke')"),
    target: str = Query(..., description="The target menu item name"),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Manually apply a menu alias (owner override)."""
    await ensure_restaurant_access(restaurant_id, user)
    
    # Find the target menu item
    menu_item = await db.menu_items.find_one({
        "restaurant_id": restaurant_id,
        "name": {"$regex": f"^{target}$", "$options": "i"}
    })
    
    if menu_item:
        await db.menu_items.update_one(
            {"_id": menu_item["_id"]},
            {"$addToSet": {"aliases": alias.lower()}}
        )
        return {"success": True, "message": f"Alias '{alias}' added to '{menu_item['name']}'"}
    else:
        # Store as global alias
        await db.menu_aliases.update_one(
            {"restaurant_id": restaurant_id, "alias": alias.lower()},
            {"$set": {"target": target, "manual": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
        return {"success": True, "message": f"Global alias '{alias}' → '{target}' created"}


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
# POS INTEGRATION ENDPOINTS
# ============================================================
class POSCredentials(BaseModel):
    pos_type: str  # "clover", "square", or "toast"
    clover_api_token: Optional[str] = None
    clover_merchant_id: Optional[str] = None
    square_access_token: Optional[str] = None
    square_location_id: Optional[str] = None
    toast_client_id: Optional[str] = None
    toast_client_secret: Optional[str] = None
    toast_restaurant_guid: Optional[str] = None

@api_router.post("/restaurants/{restaurant_id}/pos/credentials")
@limiter.limit(LIMIT_POS_CREDENTIALS)
async def save_pos_credentials(request: Request, restaurant_id: str, data: POSCredentials, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    coll = get_business_collection(business_type)
    
    update = {"pos_type": data.pos_type}
    
    # Encrypt credentials before storage
    if data.clover_api_token:
        from encryption_utils import encrypt_value
        update["clover_api_token"] = encrypt_value(data.clover_api_token)
    if data.clover_merchant_id:
        from encryption_utils import encrypt_value
        update["clover_merchant_id"] = encrypt_value(data.clover_merchant_id)
    if data.square_access_token:
        from encryption_utils import encrypt_value
        update["square_access_token"] = encrypt_value(data.square_access_token)
    if data.square_location_id:
        from encryption_utils import encrypt_value
        update["square_location_id"] = encrypt_value(data.square_location_id)
    if data.toast_client_id:
        from encryption_utils import encrypt_value
        update["toast_client_id"] = encrypt_value(data.toast_client_id)
    if data.toast_client_secret:
        from encryption_utils import encrypt_value
        update["toast_client_secret"] = encrypt_value(data.toast_client_secret)
    if data.toast_restaurant_guid:
        from encryption_utils import encrypt_value
        update["toast_restaurant_guid"] = encrypt_value(data.toast_restaurant_guid)
    
    await coll.update_one({"id": restaurant_id}, {"$set": update})
    
    # Clear cached tokens when credentials change
    clear_toast_token_cache(restaurant_id)
    
    return {"success": True}

# ============================================================
# POS SYNC ENDPOINT
# ============================================================
@api_router.post("/restaurants/{restaurant_id}/pos/sync")
@limiter.limit(LIMIT_MENU_BULK)
async def pos_sync_menu(request: Request, restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    coll = get_business_collection(business_type)
    restaurant = await coll.find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    # Decrypt POS credentials before use
    try:
        from encryption_utils import decrypt_sensitive_fields, ENCRYPTED_CREDENTIAL_FIELDS
        restaurant = decrypt_sensitive_fields(restaurant, ENCRYPTED_CREDENTIAL_FIELDS)
    except Exception:
        pass
    
    pos_type = restaurant.get("pos_type", "")
    
    # Route to correct POS sync function
    if pos_type == "toast":
        result = await sync_menu_from_toast(restaurant_id, db, restaurant)
    else:
        result = await sync_menu_from_pos(restaurant_id, restaurant, db)
    
    if result.get("success"):
        await coll.update_one(
            {"id": restaurant_id},
            {"$set": {"last_pos_sync": datetime.now(timezone.utc).isoformat()}}
        )
    return result

# ============================================================
# POS TEST CONNECTION ENDPOINT
# ============================================================
@api_router.post("/restaurants/{restaurant_id}/pos/test")
@limiter.limit(LIMIT_POS_CREDENTIALS)
async def test_pos_connection(request: Request, restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Test POS connection with current credentials."""
    await ensure_restaurant_access(restaurant_id, user)
    membership = await db.memberships.find_one({"restaurant_id": restaurant_id, "user_id": user["id"]}, {"_id": 0})
    business_type = membership.get("business_type", "restaurant") if membership else "restaurant"
    coll = get_business_collection(business_type)
    restaurant = await coll.find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    pos_type = restaurant.get("pos_type", "")
    
    if pos_type == "toast":
        from encryption_utils import decrypt_value
        result = await test_toast_connection(
            client_id=decrypt_value(restaurant.get("toast_client_id", "")),
            client_secret=decrypt_value(restaurant.get("toast_client_secret", "")),
            restaurant_guid=decrypt_value(restaurant.get("toast_restaurant_guid", "")),
            env=restaurant.get("pos_env", "sandbox"),
        )
        return result
    elif pos_type == "clover":
        # Placeholder for Clover test
        return {"success": True, "message": "Clover connection test not yet implemented"}
    elif pos_type == "square":
        # Placeholder for Square test
        return {"success": True, "message": "Square connection test not yet implemented"}
    else:
        return {"success": False, "error": "No POS type configured"}

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
            import telnyx_service
            voice_app_id = telnyx_service._get_voice_app_id()
            messaging_profile_id = telnyx_service._get_messaging_profile_id()

            if not (os.environ.get("TELNYX_API_KEY") and voice_app_id):
                logger.warning("Telnyx auto-provision skipped — TELNYX_API_KEY or voice app ID not configured")
            else:
                available = await telnyx_service.search_available_numbers(country_code="US", limit=5)
                if not available:
                    logger.warning("No available Telnyx numbers found during onboarding")
                else:
                    target_number = available[0]["phone_number"]
                    order = await telnyx_service.create_number_order(
                        phone_numbers=[target_number],
                        connection_id=voice_app_id,
                        messaging_profile_id=messaging_profile_id,
                        customer_reference=data.restaurant_id,
                    )
                    order_id = order.get("id")
                    if order_id:
                        await db.phone_number_orders.insert_one({
                            "order_id": order_id,
                            "restaurant_id": data.restaurant_id,
                            "phone_number": target_number,
                            "status": order.get("status", "pending"),
                            "operation": "onboarding_auto_provision",
                            "created_by": user.get("id"),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "completed_at": None,
                            "phone_number_id": None,
                            "error": None,
                        })
                        try:
                            final_order = await telnyx_service.wait_for_order_completion(order_id, timeout_seconds=30)
                            final_status = (final_order.get("status") or "").lower()
                            pn_list = final_order.get("phone_numbers") or []
                            pn_entry = next(
                                (p for p in pn_list if p.get("phone_number") == target_number),
                                pn_list[0] if pn_list else {},
                            )
                            phone_number_id = pn_entry.get("id")
                            await db.phone_number_orders.update_one(
                                {"order_id": order_id},
                                {"$set": {
                                    "status": final_status,
                                    "completed_at": datetime.now(timezone.utc).isoformat(),
                                    "phone_number_id": phone_number_id,
                                    "error": None if final_status == "success" else f"Final status: {final_status}",
                                }},
                            )
                            if final_status == "success" and phone_number_id:
                                update_fields["phone_number"] = target_number
                                update_fields["phone_number_id"] = phone_number_id
                                logger.info(f"Auto-provisioned Telnyx number {target_number} for restaurant {data.restaurant_id}")
                            else:
                                logger.warning(f"Telnyx onboarding order {order_id} ended with status '{final_status}' — restaurant left without number")
                        except TimeoutError:
                            await db.phone_number_orders.update_one(
                                {"order_id": order_id},
                                {"$set": {"status": "timeout", "error": "Order did not complete within 30s"}},
                            )
                            logger.warning(f"Telnyx onboarding order {order_id} did not complete in 30s — restaurant left without number, will be retried via /api/telnyx/numbers/provision")
        except Exception as e:
            logger.warning(f"Could not auto-provision Telnyx number during onboarding: {e}")

    result = await _biz_coll.update_one({"id": data.restaurant_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = await _biz_coll.find_one({"id": data.restaurant_id}, {"_id": 0})
    return strip_sensitive_fields(restaurant)
# ============================================================
# DEMO/SIMULATION ENDPOINTS

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
        # Get reservation settings if enabled
        reservations_enabled = restaurant.get("reservations_enabled", config.get("reservations_enabled", False))
        reservation_settings = None
        available_slots = None
        
        if reservations_enabled:
            reservation_settings = {
                "max_party_size": config.get("reservation_max_party_size", 8),
                "advance_booking_days": config.get("reservation_advance_booking_days", 30),
            }
            # Get next 7 days of available slots
            try:
                from reservation_service import get_reservation_slots
                from datetime import date, timedelta
                import pytz
                tz = pytz.timezone(restaurant.get("timezone", "America/Chicago"))
                local_today = datetime.now(tz).date()
                all_slots = []
                for day_offset in range(7):
                    d = local_today + timedelta(days=day_offset)
                    day_slots = await get_reservation_slots(
                        restaurant_id=restaurant_id,
                        date_str=d.isoformat(),
                        config=config,
                        operating_hours=config.get("operating_hours", {}),
                        db=db,
                        restaurant_timezone=restaurant.get("timezone", "America/Chicago"),
                        restaurant=restaurant,
                    )
                    for s in day_slots:
                        s["date"] = d.isoformat()
                        s["day_label"] = d.strftime("%A %b %d")
                    all_slots.extend(day_slots)
                available_slots = all_slots
            except Exception as e:
                logger.warning(f"Could not get reservation slots: {e}")
        
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
            delivery_fee=restaurant.get("delivery_fee", 0),
            delivery_zip_codes=restaurant.get("delivery_zip_codes", []),
            delivery_radius_miles=restaurant.get("delivery_radius_miles", 5.0),
            delivery_eta_offset_minutes=restaurant.get("delivery_eta_offset_minutes", 15),
            restaurant_timezone=restaurant.get("timezone", "UTC"),
            restaurant_address=restaurant.get("address"),
            reservations_enabled=reservations_enabled,
            reservation_settings=reservation_settings,
            available_reservation_slots=available_slots,
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
    restaurant_id: str = "",
    stripe_account_id: Optional[str] = None,
) -> Optional[str]:
    """
    Create a Stripe Checkout session for order prepayment.
    - If stripe_account_id is set (Stripe Connect): payment goes to restaurant's account,
      Duuutah AI keeps 1% as application_fee_amount automatically.
    - If not connected: returns None (prepayment disabled for this restaurant).
    """
    if not stripe.api_key:
        logger.warning("Stripe payment link skipped — STRIPE_SECRET_KEY not set")
        return None
    if order_total_cents <= 0:
        return None
    if not stripe_account_id:
        logger.info(f"[{call_sid}] Stripe prepayment skipped — restaurant not connected to Stripe Connect")
        return None
    try:
        # 1% convenience fee kept by Duuutah AI (minimum 1 cent)
        application_fee_cents = max(1, round(order_total_cents * 0.01))
        success_url = os.environ.get("PAYMENT_SUCCESS_URL", "https://duuutah.com/payment-success")
        checkout_session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": order_total_cents,
                        "product_data": {"name": f"Order — {restaurant_name}"},
                    },
                    "quantity": 1,
                },
            ],
            payment_intent_data={
                "application_fee_amount": application_fee_cents,
                "transfer_data": {"destination": stripe_account_id},
            },
            metadata={
                "type": "order_payment",
                "order_id": call_sid,
                "restaurant_id": restaurant_id,
                "restaurant_name": restaurant_name,
            },
            success_url=f"{success_url}?order={call_sid}",
            cancel_url=f"{success_url}?cancelled=true",
        )
        logger.info(f"[{call_sid}] Stripe payment link created → {checkout_session.url} (acct: {stripe_account_id}, fee: {application_fee_cents}¢)")
        return checkout_session.url
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
            plan="PRO",
            billing_status="active",
            monthly_call_count=0,
            owner_name="Bella Owner",
            owner_email="owner@bellacucina.example",
            business_phone="+15552345678",
            billing_email="billing@bellacucina.example",
            status="active",
            onboarding_step=7,
        )
        await db.restaurants.insert_one(demo_restaurant.model_dump())  # demo is always restaurant type

        config = RestaurantConfig(
            restaurant_id="demo-restaurant-001",
            persona="warm and friendly Italian-American",
            voice_id="21m00Tcm4TlvDq8ikWAM",
            escalation_phone_number="+15553456789",
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
# TELNYX NUMBER PROVISIONING ENDPOINTS
# ============================================================

@api_router.get("/telnyx/numbers/status")
async def telnyx_numbers_status(
    restaurant_id: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Provisioning readiness + the restaurant's current number."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    import telnyx_service
    voice_app_id = telnyx_service._get_voice_app_id()
    messaging_profile_id = telnyx_service._get_messaging_profile_id()
    return {
        "configured": bool(os.environ.get("TELNYX_API_KEY") and voice_app_id),
        "voice_app_configured": bool(voice_app_id),
        "messaging_profile_configured": bool(messaging_profile_id),
        "phone_number": restaurant.get("phone_number"),
        "phone_number_id": restaurant.get("phone_number_id"),
    }


@api_router.get("/telnyx/numbers/search")
async def telnyx_numbers_search(
    country_code: str = Query("US"),
    area_code: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Search Telnyx for available numbers. Returns up to `limit` matches."""
    import telnyx_service
    try:
        numbers = await telnyx_service.search_available_numbers(
            country_code=country_code, area_code=area_code, limit=limit,
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"[Telnyx Search] {e.response.status_code}: {e.response.text[:300]}")
        raise HTTPException(status_code=502, detail=f"Telnyx search failed ({e.response.status_code})")
    except Exception as e:
        logger.error(f"[Telnyx Search] Unexpected: {e}")
        raise HTTPException(status_code=502, detail="Telnyx number search failed")

    return {
        "available": [
            {
                "phone_number": n.get("phone_number"),
                "vanity_format": n.get("vanity_format"),
                "region": (n.get("region_information") or [{}])[0].get("region_name"),
                "monthly_cost_usd": (n.get("cost_information") or {}).get("monthly_cost"),
                "features": [f.get("name") for f in (n.get("features") or [])],
            }
            for n in numbers
        ],
        "count": len(numbers),
    }


@api_router.post("/telnyx/numbers/provision")
async def telnyx_provision_number(
    data: TelnyxProvisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Buy a Telnyx number and assign to a restaurant (voice + messaging).

    Flow:
      1. Resolve target number (data.phone_number or first match in area)
      2. Create order with auto-assignment to voice app + messaging profile
      3. Persist order audit record (status=pending)
      4. Poll order until success/failure (30s timeout)
      5. On success: write phone_number + phone_number_id to restaurant doc
    """
    restaurant = await ensure_restaurant_access(data.restaurant_id, user)
    import telnyx_service

    voice_app_id = telnyx_service._get_voice_app_id()
    messaging_profile_id = telnyx_service._get_messaging_profile_id()
    if not voice_app_id:
        raise HTTPException(status_code=400, detail="TELNYX_VOICE_APP_ID env var not configured")

    # Refuse double-provision (force-release first if you truly want a swap)
    existing = restaurant.get("phone_number")
    if existing and (not data.phone_number or data.phone_number != existing):
        raise HTTPException(
            status_code=409,
            detail=f"Restaurant already has phone_number {existing}. Release it before provisioning a new one.",
        )

    # Resolve target number
    target_number = data.phone_number
    if not target_number:
        try:
            available = await telnyx_service.search_available_numbers(
                country_code="US", area_code=data.area_code, limit=5,
            )
        except Exception as e:
            logger.error(f"[Telnyx Provision] Search failed: {e}")
            raise HTTPException(status_code=502, detail="Telnyx number search failed")
        if not available:
            raise HTTPException(status_code=404, detail="No available Telnyx numbers found")
        target_number = available[0]["phone_number"]

    # Submit order
    try:
        order = await telnyx_service.create_number_order(
            phone_numbers=[target_number],
            connection_id=voice_app_id,
            messaging_profile_id=messaging_profile_id,
            customer_reference=data.restaurant_id,
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"[Telnyx Provision] Order creation failed: {e.response.status_code} {e.response.text[:300]}")
        raise HTTPException(status_code=502, detail=f"Number order creation failed: {e.response.text[:300]}")

    order_id = order.get("id")
    if not order_id:
        raise HTTPException(status_code=502, detail="Telnyx did not return an order ID")

    # Audit record (pending)
    await db.phone_number_orders.insert_one({
        "order_id": order_id,
        "restaurant_id": data.restaurant_id,
        "phone_number": target_number,
        "status": order.get("status", "pending"),
        "operation": "provision",
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "phone_number_id": None,
        "error": None,
    })

    # Poll for completion
    try:
        final_order = await telnyx_service.wait_for_order_completion(order_id, timeout_seconds=30)
    except TimeoutError as e:
        await db.phone_number_orders.update_one(
            {"order_id": order_id},
            {"$set": {"status": "timeout", "error": str(e)}},
        )
        raise HTTPException(
            status_code=504,
            detail=f"Order {order_id} did not complete in time. Poll status via GET /api/telnyx/numbers/order/{order_id}",
        )

    final_status = (final_order.get("status") or "").lower()
    pn_list = final_order.get("phone_numbers") or []
    pn_entry = next((p for p in pn_list if p.get("phone_number") == target_number), pn_list[0] if pn_list else {})
    phone_number_id = pn_entry.get("id")

    await db.phone_number_orders.update_one(
        {"order_id": order_id},
        {"$set": {
            "status": final_status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "phone_number_id": phone_number_id,
            "error": None if final_status == "success" else f"Final status: {final_status}",
        }},
    )

    if final_status != "success":
        raise HTTPException(status_code=502, detail=f"Telnyx order ended with status '{final_status}'")

    # Update restaurant across all business-type collections
    for _coll in (db.restaurants, db.clinics, db.salons, db.home_services, db.legal):
        await _coll.update_one(
            {"id": data.restaurant_id},
            {"$set": {"phone_number": target_number, "phone_number_id": phone_number_id}},
        )

    logger.info(f"[Telnyx Provision] {data.restaurant_id} -> {target_number} (id={phone_number_id})")
    return {
        "phone_number": target_number,
        "phone_number_id": phone_number_id,
        "order_id": order_id,
        "status": final_status,
    }


@api_router.post("/telnyx/numbers/assign-existing")
async def telnyx_assign_existing_number(
    data: TelnyxAssignNumberRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Bind an already-owned Telnyx number to a restaurant."""
    restaurant = await ensure_restaurant_access(data.restaurant_id, user)
    import telnyx_service

    voice_app_id = telnyx_service._get_voice_app_id()
    messaging_profile_id = telnyx_service._get_messaging_profile_id()

    try:
        matches = await telnyx_service.list_phone_numbers(phone_number=data.phone_number)
    except Exception as e:
        logger.error(f"[Telnyx Assign] Lookup failed: {e}")
        raise HTTPException(status_code=502, detail="Telnyx number lookup failed")
    if not matches:
        raise HTTPException(status_code=404, detail=f"Number {data.phone_number} is not owned by this Telnyx account")

    phone_number_id = matches[0].get("id")
    try:
        await telnyx_service.update_phone_number(
            phone_number_id,
            connection_id=voice_app_id,
            messaging_profile_id=messaging_profile_id,
            customer_reference=data.restaurant_id,
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"[Telnyx Assign] Update failed: {e.response.status_code} {e.response.text[:300]}")
        raise HTTPException(status_code=502, detail=f"Number update failed: {e.response.text[:300]}")

    await db.phone_number_orders.insert_one({
        "order_id": None,
        "restaurant_id": data.restaurant_id,
        "phone_number": data.phone_number,
        "status": "success",
        "operation": "assign",
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "phone_number_id": phone_number_id,
        "error": None,
    })

    for _coll in (db.restaurants, db.clinics, db.salons, db.home_services, db.legal):
        await _coll.update_one(
            {"id": data.restaurant_id},
            {"$set": {"phone_number": data.phone_number, "phone_number_id": phone_number_id}},
        )

    logger.info(f"[Telnyx Assign] {data.restaurant_id} -> {data.phone_number} (id={phone_number_id})")
    return {"phone_number": data.phone_number, "phone_number_id": phone_number_id, "status": "success"}


@api_router.post("/telnyx/numbers/release")
async def telnyx_release_number(
    data: TelnyxReleaseRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Release the restaurant's Telnyx number. Irreversible."""
    restaurant = await ensure_restaurant_access(data.restaurant_id, user)
    import telnyx_service

    phone_number_id = data.phone_number_id or restaurant.get("phone_number_id")
    if not phone_number_id:
        raise HTTPException(status_code=404, detail="No phone_number_id on file for this restaurant")

    released = await telnyx_service.release_phone_number(phone_number_id)
    if not released:
        raise HTTPException(status_code=502, detail=f"Telnyx release failed for {phone_number_id}")

    for _coll in (db.restaurants, db.clinics, db.salons, db.home_services, db.legal):
        await _coll.update_one(
            {"id": data.restaurant_id},
            {"$unset": {"phone_number_id": "", "phone_number": ""}},
        )

    await db.phone_number_orders.insert_one({
        "order_id": None,
        "restaurant_id": data.restaurant_id,
        "phone_number": restaurant.get("phone_number"),
        "status": "success",
        "operation": "release",
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "phone_number_id": phone_number_id,
        "error": None,
    })

    logger.info(f"[Telnyx Release] {data.restaurant_id} released {phone_number_id}")
    return {"released": True, "phone_number_id": phone_number_id}


@api_router.get("/telnyx/numbers/order/{order_id}")
async def telnyx_get_order(
    order_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Check status of a number order (for orders that didn't complete synchronously)."""
    import telnyx_service
    try:
        order = await telnyx_service.get_number_order(order_id)
    except Exception as e:
        logger.error(f"[Telnyx Order Status] {e}")
        raise HTTPException(status_code=502, detail="Telnyx order lookup failed")
    record = await db.phone_number_orders.find_one({"order_id": order_id}, {"_id": 0})
    return {"telnyx": order, "audit": record}


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


async def _prefetch_call_session_data(
    *,
    called_number: str,
    caller_number: str,
    call_sid: str,
) -> Optional[dict]:
    """Pre-fetch all session data for an incoming call.

    Returns the dict to upsert into active_calls (with the system_prompt baked in),
    or None if the called number isn't associated with an active restaurant.
    """
    import asyncio as _asyncio

    _lookup_filter = {"phone_number": called_number}
    _phone_results = await _asyncio.gather(
        db.restaurants.find_one(_lookup_filter, {"_id": 0}),
        db.clinics.find_one(_lookup_filter, {"_id": 0}),
        db.salons.find_one(_lookup_filter, {"_id": 0}),
        db.home_services.find_one(_lookup_filter, {"_id": 0}),
        db.legal.find_one(_lookup_filter, {"_id": 0}),
    )
    restaurant = next((r for r in _phone_results if r), None)
    if not restaurant or not restaurant.get("is_active"):
        return None

    restaurant_id = restaurant["id"]
    business_type = restaurant.get("business_type", "restaurant")
    plan_features = get_plan_features(restaurant.get("plan", "STARTER"))

    if plan_features["customer_recognition"]:
        config, menu_items, customer_profile = await _asyncio.gather(
            get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0}),
            db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(500),
            db.customer_profiles.find_one({"phone_number": caller_number, "restaurant_id": restaurant_id}, {"_id": 0}),
        )
        logger.info(f"[{call_sid}] CRM lookup: caller={caller_number}, profile={customer_profile}")
    else:
        config, menu_items = await _asyncio.gather(
            get_config_collection(business_type).find_one({"restaurant_id": restaurant_id}, {"_id": 0}),
            db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(500),
        )
        customer_profile = None
        logger.info(f"[{call_sid}] CRM skipped (plan: {restaurant.get('plan', 'STARTER')})")

    # Enrich menu items with resolved modifier groups
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

    business_type = config.get("business_type", "restaurant") if config else "restaurant"

    services = []
    if business_type in ("clinic", "salon", "home_services", "legal"):
        services = await db.services.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

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
            logger.info(f"[{call_sid}] Availability pre-fetched for {len(cached_availability)} days")
        except Exception as _e:
            logger.warning(f"[{call_sid}] Availability pre-fetch failed (non-fatal): {_e}")

    from gemini_service import get_system_prompt

    reservations_enabled = restaurant.get("reservations_enabled", config.get("reservations_enabled", False) if config else False)
    reservation_settings = None
    available_reservation_slots = None

    if reservations_enabled and business_type == "restaurant":
        reservation_settings = {
            "max_party_size": config.get("reservation_max_party_size", 8) if config else 8,
            "advance_booking_days": config.get("reservation_advance_booking_days", 30) if config else 30,
        }
        try:
            from reservation_service import get_reservation_slots
            from datetime import date, timedelta
            import pytz
            tz = pytz.timezone(restaurant.get("timezone", "America/Chicago"))
            local_today = datetime.now(tz).date()
            all_slots = []
            for day_offset in range(7):
                d = local_today + timedelta(days=day_offset)
                day_slots = await get_reservation_slots(
                    restaurant_id=restaurant_id,
                    date_str=d.isoformat(),
                    config=config or {},
                    operating_hours=config.get("operating_hours", {}) if config else {},
                    db=db,
                    restaurant_timezone=restaurant.get("timezone", "America/Chicago"),
                    restaurant=restaurant,
                )
                for s in day_slots:
                    s["date"] = d.isoformat()
                    s["day_label"] = d.strftime("%A %b %d")
                all_slots.extend(day_slots)
            available_reservation_slots = all_slots
            logger.info(f"[{call_sid}] Reservation slots pre-fetched: {len(available_reservation_slots)} slots (7 days)")
        except Exception as e:
            logger.warning(f"[{call_sid}] Reservation slots pre-fetch failed: {e}")

    prompt_kwargs = dict(
        business_type=business_type,
        customer_profile=customer_profile,
        plan=restaurant.get("plan", "STARTER"),
        restaurant_name=restaurant.get("name", "the restaurant"),
        cuisine_type=restaurant.get("cuisine_type", ""),
        persona=config.get("persona", "friendly") if config else "friendly",
        business_rules=config.get("business_rules", []) if config else [],
        escalation_rules=config.get("escalation_rules", []) if config else [],
        menu_items=menu_items,
        disclosure_text=config.get("disclosure_text", "Hi! I'm an AI assistant. How can I help you today?") if config else "Hi! I'm an AI assistant. How can I help you today?",
        upsell_enabled=config.get("upsell_enabled", True) if config else True,
        offers_delivery=restaurant.get("offers_delivery", True),
        offers_reservations=restaurant.get("offers_reservations", True),
        delivery_enabled=restaurant.get("delivery_enabled", config.get("delivery_enabled", True) if config else True),
        delivery_minimum=config.get("delivery_minimum", 1500) if config else 1500,
        delivery_fee=restaurant.get("delivery_fee", 0),
        delivery_zip_codes=restaurant.get("delivery_zip_codes", []),
        delivery_radius_miles=restaurant.get("delivery_radius_miles", 5.0),
        delivery_eta_offset_minutes=restaurant.get("delivery_eta_offset_minutes", 15),
        avg_prep_time_minutes=restaurant.get("avg_prep_time_minutes", 20),
        escalation_phone=config.get("escalation_phone_number") if config else None,
        operating_hours=config.get("operating_hours") if config else None,
        restaurant_timezone=restaurant.get("timezone", "UTC"),
        restaurant_address=restaurant.get("address"),
        services=services,
        cached_availability=cached_availability,
        reservations_enabled=reservations_enabled,
        reservation_settings=reservation_settings,
        available_reservation_slots=available_reservation_slots,
    )
    # Build the English variant eagerly (fast path for English callers).
    # The WS handler rebuilds with prompt_kwargs if the caller picked a
    # different language at the IVR.
    system_prompt = get_system_prompt(**prompt_kwargs)

    return {
        "call_sid": call_sid,
        "restaurant_id": restaurant_id,
        "caller_number": caller_number,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "system_prompt": system_prompt,
        "prompt_kwargs": prompt_kwargs,
        "restaurant": restaurant,
        "config": config or {},
        "menu_items": menu_items,
        "services": services,
    }


def _decode_client_state(encoded: Optional[str]) -> Dict[str, Any]:
    """Decode a Telnyx client_state base64-JSON blob. Returns {} on missing/invalid."""
    if not encoded:
        return {}
    try:
        import base64 as _b64
        import json as _json
        return _json.loads(_b64.b64decode(encoded))
    except Exception as e:
        logger.warning(f"[Telnyx] client_state decode failed: {e}")
        return {}


def _encode_client_state(state: Dict[str, Any]) -> str:
    """Base64-JSON encode a dict for Telnyx client_state."""
    import base64 as _b64
    import json as _json
    return _b64.b64encode(_json.dumps(state, separators=(",", ":")).encode()).decode()


def _compute_language_routing(active_call_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide language routing for this inbound call.

    Returns a dict with two keys:
        ivr_state — JSON-serializable, to be base64'd as Telnyx client_state.
                    Always includes: needs_ivr (bool), default_lang (str).
                    If needs_ivr: also includes digit_to_lang (Dict[str,str]).
        lang      — The default language to store on active_calls.lang. Will
                    be overwritten by the call.gather.ended handler if IVR fires.

    Routing rules:
      - Plan != PRO OR multilingual_enabled False  →  no IVR, lang=primary
      - Only one supported language                →  no IVR, lang=primary
      - Otherwise                                  →  IVR, default=primary
        (Language is NEVER persisted across calls. Phones are often shared
         between family members who may speak different languages — every
         call gets the language menu.)
    """
    from language_prompts import is_supported

    restaurant = active_call_data.get("restaurant", {}) or {}
    config = active_call_data.get("config", {}) or {}

    plan = (restaurant.get("plan") or "STARTER").upper()
    multilingual_enabled = bool(config.get("multilingual_enabled", False)) and plan == "PRO"

    primary = (config.get("primary_language") or "en").lower()
    if not is_supported(primary):
        primary = "en"

    additional = [
        c.lower() for c in (config.get("additional_languages") or [])
        if is_supported(c.lower()) and c.lower() != primary
    ]
    supported = [primary] + additional

    if not multilingual_enabled or len(supported) < 2:
        return {"ivr_state": {"needs_ivr": False, "default_lang": primary}, "lang": primary}

    # Build digit map. "1" → primary, "2" → first additional, etc. Capped at 9.
    supported_to_offer = supported[:9]
    digit_to_lang = {str(i + 1): code for i, code in enumerate(supported_to_offer)}

    return {
        "ivr_state": {
            "needs_ivr": True,
            "digit_to_lang": digit_to_lang,
            "default_lang": primary,
        },
        "lang": primary,
    }


def _build_ivr_speak_payload(digit_to_lang: Dict[str, str]) -> str:
    """
    Build the TTS payload string for the language-selection IVR.

    Example for {"1": "en", "2": "te", "3": "hi"}:
        "For English, press 1. For Telugu, press 2. For Hindi, press 3."

    All segments use the Latin name of each language so Telnyx's single English
    TTS voice can read them clearly. Native speakers recognize their language's
    own name even when read by an English voice. For a future polish pass,
    swap to gather_using_audio with pre-recorded native-speaker MP3s.
    """
    from language_prompts import LANGUAGE_NAMES
    parts = []
    for digit, lang in digit_to_lang.items():
        name = (LANGUAGE_NAMES.get(lang) or {}).get("latin", lang.upper())
        parts.append(f"For {name}, press {digit}.")
    return " ".join(parts)


@api_router.post("/telnyx/incoming")
async def telnyx_incoming_call(request: Request):
    """Telnyx Call Control webhook — full event flow:
    call.initiated     -> prefetch + compute IVR routing + answer with client_state
    call.answered      -> if needs_ivr: gather_using_speak; else: start_streaming
    call.gather.ended  -> map digit → lang, persist preference, start_streaming
    streaming.* / call.hangup -> log
    """
    import json
    import telnyx_service

    raw_body = await request.body()

    # Signature verification (skip on localhost only)
    backend_url = get_backend_public_url()
    if "localhost" not in backend_url and "127.0.0.1" not in backend_url:
        sig = request.headers.get("telnyx-signature-ed25519", "")
        ts = request.headers.get("telnyx-timestamp", "")
        if not telnyx_service.verify_webhook_signature(raw_body, sig, ts):
            logger.warning(f"Rejected forged Telnyx webhook from {request.client.host if request.client else 'unknown'}")
            return Response(status_code=403, content="Forbidden")

    try:
        payload = json.loads(raw_body)
    except Exception as e:
        logger.error(f"[Telnyx] Webhook parse error: {e}")
        return Response(status_code=400)

    data = payload.get("data", {})
    event_type = data.get("event_type", "")
    event_payload = data.get("payload", {})
    call_control_id = event_payload.get("call_control_id", "")

    logger.info(f"[Telnyx webhook] event={event_type} call_control_id={call_control_id}")

    if event_type == "call.initiated":
        from_number = event_payload.get("from", "")
        to_number = event_payload.get("to", "")
        direction = event_payload.get("direction", "")
        if direction != "incoming":
            return Response(status_code=200)
        logger.info(f"[Telnyx] incoming call: {from_number} -> {to_number}")

        active_call_data = await _prefetch_call_session_data(
            called_number=to_number,
            caller_number=from_number,
            call_sid=call_control_id,
        )
        if not active_call_data:
            logger.warning(f"[Telnyx] Inactive number called: {to_number}, hanging up")
            await telnyx_service.hang_up_call(call_control_id)
            return Response(status_code=200)

        routing = _compute_language_routing(active_call_data)
        active_call_data["lang"] = routing["lang"]

        await db.active_calls.update_one(
            {"call_sid": call_control_id},
            {"$set": active_call_data},
            upsert=True,
        )

        encoded_state = _encode_client_state(routing["ivr_state"])
        logger.info(
            f"[Telnyx] {call_control_id} routing: needs_ivr={routing['ivr_state'].get('needs_ivr')} "
            f"default_lang={routing['lang']}"
        )
        await telnyx_service.answer_call(call_control_id, client_state=encoded_state)

    elif event_type == "call.answered":
        host = request.headers.get("host", "ringai-v2.onrender.com")
        scheme = "wss" if request.url.scheme == "https" else "ws"
        ws_url = f"{scheme}://{host}/api/telnyx/media-stream"

        ivr_state = _decode_client_state(event_payload.get("client_state"))
        if ivr_state.get("needs_ivr"):
            digit_to_lang = ivr_state.get("digit_to_lang", {})
            speak_payload = _build_ivr_speak_payload(digit_to_lang)
            # Re-encode the same state so call.gather.ended can read digit_to_lang
            encoded_state = _encode_client_state(ivr_state)
            await telnyx_service.gather_using_speak(
                call_control_id=call_control_id,
                payload=speak_payload,
                valid_digits="".join(digit_to_lang.keys()) or "0123456789",
                minimum_digits=1,
                maximum_digits=1,
                inter_digit_timeout_secs=6,
                timeout_millis=10000,
                client_state=encoded_state,
            )
        else:
            await telnyx_service.start_streaming(call_control_id, ws_url)

    elif event_type == "call.gather.ended":
        ivr_state = _decode_client_state(event_payload.get("client_state"))
        digits = event_payload.get("digits", "") or ""
        digit_to_lang = ivr_state.get("digit_to_lang", {})
        default_lang = ivr_state.get("default_lang", "en")
        chosen_lang = digit_to_lang.get(digits, default_lang)
        logger.info(
            f"[Telnyx] {call_control_id} IVR complete: digits={digits!r} -> lang={chosen_lang}"
        )

        # Update active_calls with the chosen language (WS handler reads this)
        await db.active_calls.update_one(
            {"call_sid": call_control_id},
            {"$set": {"lang": chosen_lang}},
        )

        host = request.headers.get("host", "ringai-v2.onrender.com")
        scheme = "wss" if request.url.scheme == "https" else "ws"
        ws_url = f"{scheme}://{host}/api/telnyx/media-stream"
        await telnyx_service.start_streaming(call_control_id, ws_url)

    elif event_type == "call.bridged":
        # Fires when Telnyx has connected the customer-human audio bridge
        # after a /actions/transfer. We can now safely release our side —
        # auto_hang_up=False on the serializer means cancelling the pipeline
        # won't kill the A-leg (which is the bridge anchor).
        session = get_call_session(call_control_id)
        if session is not None and getattr(session, "_transfer_in_progress", False):
            logger.info(f"[Telnyx] call.bridged for {call_control_id} — releasing pipeline")
            await session._handle_transfer_bridged()
        else:
            # Bridge for a call we don't have a session for — likely a
            # process restart between transfer init and bridge complete.
            # The bridge itself is fine; we just can't do post-bridge cleanup.
            logger.info(f"[Telnyx] call.bridged for {call_control_id} (no session in registry)")

    elif event_type == "call.hangup":
        # If the A-leg of a transfer-in-progress call hangs up before the
        # bridge succeeds, the transfer is effectively cancelled (customer
        # gave up, or B-leg timed out and Telnyx cleaned up the A-leg too).
        # Trigger the timeout path so the fallback watchdog is cancelled
        # and the pipeline is released.
        session = get_call_session(call_control_id)
        if (
            session is not None
            and getattr(session, "_transfer_in_progress", False)
            and not getattr(session, "_bridge_succeeded", False)
        ):
            logger.info(
                f"[Telnyx] call.hangup for {call_control_id} during transfer — "
                f"treating as transfer timeout"
            )
            await session._handle_transfer_timeout()
        else:
            logger.info(f"[Telnyx] Call ended: {call_control_id}")

    elif event_type in ("streaming.started", "streaming.stopped", "streaming.failed"):
        logger.info(f"[Telnyx] {event_type}: {event_payload}")

    return Response(status_code=200)


@api_router.post("/telnyx/sms-inbound")
async def telnyx_sms_status(request: Request):
    """Telnyx SMS delivery status webhook. Updates db.sms_messages with delivery state and cost."""
    import json
    import telnyx_service

    raw_body = await request.body()

    backend_url = get_backend_public_url()
    if "localhost" not in backend_url and "127.0.0.1" not in backend_url:
        sig = request.headers.get("telnyx-signature-ed25519", "")
        ts = request.headers.get("telnyx-timestamp", "")
        if not telnyx_service.verify_webhook_signature(raw_body, sig, ts):
            logger.warning(f"Rejected forged Telnyx SMS webhook from {request.client.host if request.client else 'unknown'}")
            return Response(status_code=403, content="Forbidden")

    try:
        payload = json.loads(raw_body)
    except Exception as e:
        logger.error(f"[Telnyx SMS webhook] parse error: {e}")
        return Response(status_code=400)

    data = payload.get("data", {})
    event_type = data.get("event_type", "")
    event_payload = data.get("payload", {})
    message_id = event_payload.get("id")

    if not message_id:
        logger.warning(f"[Telnyx SMS webhook] missing message id; event_type={event_type}")
        return Response(status_code=200)

    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

    recipients = event_payload.get("to", [])
    if recipients:
        recipient_status = recipients[0].get("status")
        if recipient_status == "delivered":
            update["status"] = "delivered"
        elif recipient_status in ("delivery_failed", "sending_failed"):
            update["status"] = "failed"
            errors = event_payload.get("errors", [])
            if errors:
                update["error_code"] = str(errors[0].get("code", ""))
                update["error_message"] = errors[0].get("title", "")
        elif recipient_status == "delivery_unconfirmed":
            update["status"] = "delivery_unconfirmed"

    cost = event_payload.get("cost") or {}
    amount_str = cost.get("amount")
    if amount_str:
        try:
            update["cost_cents"] = int(round(float(amount_str) * 100))
        except (TypeError, ValueError):
            pass

    result = await db.sms_messages.update_one(
        {"message_id": message_id},
        {"$set": update},
        upsert=False,
    )
    logger.info(f"[Telnyx SMS webhook] {event_type} for {message_id}: matched={result.matched_count} status={update.get('status')}")
    return Response(status_code=200)


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
            "total_voice_cost_cents": {"$sum": "$cost_voice_cents"},
            "total_sms_cost_cents": {"$sum": "$cost_sms_cents"},
            "total_gemini_cost_cents": {"$sum": "$cost_gemini_extract_cents"},
            "total_revenue_cents": {"$sum": "$order_total"},
            "total_duration_seconds": {"$sum": "$duration_seconds_actual"},
            "total_sms_count": {"$sum": "$sms_count"},
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

@app.websocket("/api/telnyx/media-stream")
async def telnyx_media_stream(websocket: WebSocket):
    """Full Pipecat-integrated WebSocket for Telnyx media streams.

    Parses Telnyx's start-message format (call_control_id, to, from),
    pre-fetches restaurant + menu + customer context, builds the system prompt,
    and hands the WebSocket off to create_call_pipeline.
    """
    await websocket.accept()
    register_active_websocket(websocket)

    try:
        # Read messages until we get the start event with call_control_id.
        # Telnyx sends:
        #   {"version":"...","event":"connected"}                                       (control)
        #   {"start": {"call_control_id":"...","to":"...","from":"...",...}}            (start)
        #   {"stream_id":"...","event":"media","media":{"payload":"<base64>",...}}      (audio)
        stream_id = ""
        call_control_id = ""
        while not call_control_id:
            msg = await websocket.receive_json()
            if "start" in msg and isinstance(msg["start"], dict):
                start_data = msg["start"]
                call_control_id = start_data.get("call_control_id", "")
                stream_id = msg.get("stream_id", "") or start_data.get("stream_id", "")
            elif msg.get("event") == "connected":
                continue
            else:
                break

        logger.info(f"[Telnyx WS] Stream started: call_control_id={call_control_id} stream_id={stream_id}")

        # All data pre-fetched during POST /telnyx/incoming — just read it
        call_sid = call_control_id
        active_call = await db.active_calls.find_one({"call_sid": call_sid}, {"_id": 0})
        if not active_call:
            logger.error(f"No active call found for SID {call_sid}")
            await websocket.close()
            return

        restaurant_id = active_call["restaurant_id"]
        lang = (active_call.get("lang") or "en").lower()

        # English path: use the pre-built prompt from call.initiated (fast path).
        # Non-English: rebuild with lang baked in. Build is pure string composition
        # — no LLM calls — typically 50-200ms. The build_system_prompt function
        # weaves language guidance into the prompt at the right places instead of
        # appending a directive at the end (which used to override the menu via
        # Gemini's recency bias).
        if lang == "en":
            system_prompt = active_call.get("system_prompt", "")
        else:
            from gemini_service import get_system_prompt
            prompt_kwargs = active_call.get("prompt_kwargs", {})
            system_prompt = get_system_prompt(lang=lang, **prompt_kwargs)

        restaurant = active_call.get("restaurant", {})
        config = active_call.get("config", {})
        menu_items = active_call.get("menu_items", [])

        # Decrypt POS credentials
        try:
            from encryption_utils import decrypt_sensitive_fields, ENCRYPTED_CREDENTIAL_FIELDS
            restaurant = decrypt_sensitive_fields(restaurant, ENCRYPTED_CREDENTIAL_FIELDS)
        except Exception:
            pass

        services = active_call.get("services", [])
        session = CallSession(
            call_sid=call_sid,
            restaurant_id=restaurant_id,
            caller_number=active_call.get("caller_number", ""),
            restaurant=restaurant,
            config=config or {},
            menu_items=menu_items,
            services=services,
            lang=lang,
            restaurant_phone_number=restaurant.get("phone_number"),
        )
        session.is_open = calculate_is_open(
            operating_hours=config.get("operating_hours") if config else None,
            restaurant_timezone=restaurant.get("timezone", "UTC"),
        )
        if not session.is_open:
            logger.info(f"[{call_sid}] Restaurant is CLOSED — order dispatch blocked")

        # Register session so webhook handlers (call.bridged etc.) can reach it
        register_call_session(call_sid, session)

        async def on_call_complete(call_sid, restaurant_id, transcript, session=None):
            """Save full call record including extracted order and quality eval."""
            try:
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

                analysis = await analyse_call_transcript(transcript, order_data, menu_items)

                call = CallRecord(
                    restaurant_id=restaurant_id,
                    call_sid=call_sid,
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

                # Monthly call count + overage billing
                try:
                    for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
                        await _coll.update_one(
                            {"id": restaurant_id},
                            {"$inc": {"monthly_call_count": 1}}
                        )
                    _new_count = restaurant.get("monthly_call_count", 0) + 1
                    _call_limit = restaurant.get("monthly_call_limit", 500)
                    _cust_id = restaurant.get("stripe_customer_id")
                    if restaurant.get("billing_status") == "active" and _cust_id and _new_count > _call_limit:
                        _plan = restaurant.get("plan", "STARTER")
                        _overage_cents = get_plan_features(_plan)["overage_per_call_cents"]
                        stripe.InvoiceItem.create(
                            customer=_cust_id,
                            amount=_overage_cents,
                            currency="usd",
                            description=f"Overage call #{_new_count - _call_limit} ({_plan} plan)",
                        )
                        logger.info(f"[{call_sid}] Overage billed: call #{_new_count} (limit: {_call_limit}, {_overage_cents}¢)")
                except Exception as e:
                    logger.warning(f"[{call_sid}] Overage billing failed (non-critical): {e}")

                # CRM: upsert customer profile (PRO only)
                customer_name = None
                if session and session.order and session.order.customer_name:
                    customer_name = session.order.customer_name
                _plan_features = get_plan_features(restaurant.get("plan", "STARTER"))
                if _plan_features["customer_recognition"] and (caller_number := active_call.get("caller_number")):
                    _profile_update = {
                        "phone_number": caller_number,
                        "restaurant_id": restaurant_id,
                        "last_call_at": datetime.now(timezone.utc).isoformat(),
                    }
                    _consent = None
                    if session and session.order:
                        _consent = session.order.save_name_consent
                    if _consent is True and customer_name:
                        _profile_update["last_name"] = customer_name
                        _profile_update["name_consent"] = True
                    elif _consent is False:
                        _profile_update["name_consent"] = False
                        _profile_update["last_name"] = None
                    elif customer_name:
                        existing_profile = await db.customer_profiles.find_one(
                            {"phone_number": caller_number, "restaurant_id": restaurant_id},
                            {"_id": 0, "name_consent": 1}
                        )
                        if existing_profile and existing_profile.get("name_consent") is True:
                            _profile_update["last_name"] = customer_name
                    if order_data:
                        _profile_update["last_order"] = order_data
                    await db.customer_profiles.update_one(
                        {"phone_number": caller_number, "restaurant_id": restaurant_id},
                        {"$set": _profile_update, "$inc": {"visit_count": 1}},
                        upsert=True,
                    )
                    logger.info(f"[{call_sid}] Customer profile upserted for {caller_number}")

                # WebSocket notifications
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

                # SMS confirmation
                sms_enabled = config.get("sms_enabled", True) if config else True
                sms_payment_enabled = config.get("sms_payment_enabled", False) if config else False

                if sms_enabled and session and session.order.items:
                    payment_link = None
                    if sms_payment_enabled and order_total > 0:
                        _stripe_account_id = restaurant.get("stripe_account_id")
                        payment_link = await create_stripe_payment_link(
                            order_total_cents=order_total,
                            restaurant_name=restaurant.get("name", "the restaurant"),
                            call_sid=call_sid,
                            restaurant_id=restaurant_id,
                            stripe_account_id=_stripe_account_id,
                        )
                    await send_order_sms(
                        caller_number=active_call.get("caller_number", ""),
                        order=session.order,
                        restaurant_name=restaurant.get("name", "the restaurant"),
                        prep_time_minutes=restaurant.get("avg_prep_time_minutes", 20),
                        payment_link=payment_link,
                        restaurant=restaurant,
                        config=config,
                    )
                    if session:
                        session._sms_count += 1

                # Auto-learning (PRO only, non-blocking)
                try:
                    if analysis and session and session.business_type == "restaurant" and _plan_features.get("auto_learning"):
                        learning_service = get_learning_service(db)
                        learning_result = await learning_service.process_call_analysis(
                            restaurant_id=restaurant_id,
                            call_id=call_sid,
                            analysis=analysis,
                            order_completed=bool(order_data and order_data.get("items")),
                            order_total=order_total,
                        )
                        logger.info(f"[{call_sid}] Learning: aliases={len(learning_result.get('aliases_learned', []))}, flagged={learning_result.get('flagged_for_review')}")
                except Exception as e:
                    logger.warning(f"[{call_sid}] Auto-learning failed (non-critical): {e}")
            except Exception as e:
                logger.error(f"[{call_sid}] on_call_complete error: {e}", exc_info=True)

            # ── Post-call reservation fallback (restaurants only) ────────────
            # Final safety net only. Primary reservation dispatch now runs
            # earlier, in the same teardown-protected sequence as the order
            # (CallSession._ensure_reservation_booked, from _handle_order_confirmed
            # and the disconnect handler). This tail runs after the slow
            # analyse_call_transcript above and races teardown, so it must not be
            # the only dispatch path — by the time it runs the reservation is
            # usually already booked (no-op).
            try:
                if session is not None:
                    await session._ensure_reservation_booked()
            except Exception as e:
                logger.error(f"[{call_sid}] Post-call reservation fallback error: {e}", exc_info=True)

        if is_pipeline_available():
            await create_call_pipeline(
                websocket=websocket,
                system_prompt=system_prompt,
                restaurant_id=restaurant_id,
                call_sid=call_sid,
                stream_sid=stream_id,
                on_call_complete=on_call_complete,
                session=session,
                voice=config.get("voice_id") if config else None,
            )
        else:
            logger.warning("Pipecat pipeline not available — closing WebSocket")
            await websocket.close()

    except Exception as e:
        logger.error(f"[Telnyx WS] error: {e}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        unregister_active_websocket(websocket)
        if call_control_id:
            unregister_call_session(call_control_id)

# ============================================================
# BILLING / INTEGRATIONS
# ============================================================

@api_router.post("/billing/create-checkout-session")
async def create_checkout_session(payload: BillingCheckoutRequest, user: Dict[str, Any] = Depends(get_current_user)):
    restaurant = await ensure_restaurant_access(payload.restaurant_id, user)

    if not stripe.api_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured")

    # Resolve plan -> price ID
    plan_name = (payload.plan or "starter").upper()
    if plan_name not in PLAN_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan_name}. Valid plans: {', '.join(PLAN_CONFIG.keys())}")

    price_env_key = PLAN_CONFIG[plan_name]["price_env"]
    price_id = payload.price_id or os.environ.get(price_env_key) or os.environ.get("STRIPE_DEFAULT_PRICE_ID")
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Stripe price not configured for {plan_name}. Set {price_env_key} env var.")

    frontend_url = get_frontend_url()

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

    is_onboarding = payload.source == "onboarding"
    success_path = "/dashboard?billing=success" if is_onboarding else "/billing?billing=success"
    cancel_path = "/onboarding?billing=cancelled" if is_onboarding else "/billing?billing=cancelled"

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{frontend_url}{success_path}",
        cancel_url=f"{frontend_url}{cancel_path}",
        metadata={"restaurant_id": restaurant["id"], "plan": plan_name},
        subscription_data={"trial_period_days": 7},
    )

    return {"checkout_url": session.url}


class DisconnectStripeRequest(BaseModel):
    restaurant_id: str


class BillingPortalRequest(BaseModel):
    restaurant_id: str


@api_router.post("/billing/portal")
async def create_billing_portal(payload: BillingPortalRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """Create a Stripe Customer Portal session for managing subscriptions."""
    restaurant = await ensure_restaurant_access(payload.restaurant_id, user)

    if not stripe.api_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured")

    customer_id = restaurant.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No active subscription. Please choose a plan first.")

    frontend_url = get_frontend_url()
    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{frontend_url}/billing",
    )

    return {"portal_url": portal_session.url}


@api_router.get("/billing/invoices")
async def list_invoices(restaurant_id: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Return recent Stripe invoices for the restaurant."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    customer_id = restaurant.get("stripe_customer_id")
    if not customer_id:
        return {"invoices": []}
    try:
        invoices = stripe.Invoice.list(customer=customer_id, limit=12)
        return {"invoices": [
            {
                "id": inv.id,
                "date": inv.created,
                "amount": inv.amount_paid,
                "status": inv.status,
                "pdf": inv.invoice_pdf,
                "description": inv.lines.data[0].description if inv.lines.data else "",
            }
            for inv in invoices.auto_paging_iter()
            if inv.status in ("paid", "open", "uncollectible")
        ][:12]}
    except Exception as e:
        logger.warning(f"[Billing] Invoice list failed: {e}")
        return {"invoices": []}


@api_router.get("/restaurants/{restaurant_id}/plan-features")
async def get_plan_features_endpoint(restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Return the plan config for the authenticated restaurant."""
    restaurant = await ensure_restaurant_access(payload.restaurant_id, user)
    plan = restaurant.get("plan", "STARTER")
    return {"plan": plan, "features": get_plan_features(plan)}


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
    all_collections = [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]

    if event_type == "checkout.session.completed":
        checkout_mode = data.get("mode")
        meta = data.get("metadata", {})

        if checkout_mode == "payment" and meta.get("type") == "order_payment":
            # --- ORDER PREPAYMENT ---
            order_id = meta.get("order_id")
            rest_id = meta.get("restaurant_id")
            if order_id:
                await db.call_records.update_one(
                    {"call_sid": order_id, "payment_status": {"$ne": "refunded"}},
                    {"$set": {
                        "payment_status": "paid",
                        "paid_at": datetime.now(timezone.utc).isoformat(),
                        "stripe_payment_id": data.get("payment_intent", ""),
                    }}
                )
                logger.info(f"[Stripe] Order {order_id} marked as paid")
                # Notify restaurant via WebSocket
                try:
                    from websocket_notifications import notify_new_order
                    await notify_new_order(
                        restaurant_id=rest_id,
                        order_id=order_id,
                        total=data.get("amount_total", 0),
                    )
                except Exception as e:
                    logger.warning(f"[Stripe] WebSocket notify failed: {e}")
                # Send payment confirmation SMS
                try:
                    caller = await db.call_records.find_one({"call_sid": order_id}, {"caller_number": 1, "_id": 0})
                    if caller and caller.get("caller_number"):
                        amount_str = f"${data.get('amount_total', 0) / 100:.2f}"
                        rest_name = meta.get("restaurant_name", "the restaurant")
                        sms_body = f"Payment of {amount_str} received for your order at {rest_name}. Thank you!"
                        import telnyx_service
                        sms_result = await telnyx_service.send_sms(
                            to=caller["caller_number"],
                            body=sms_body,
                            idempotency_key=f"payment_received:{order_id}",
                            metadata={
                                "purpose": "payment_confirmation",
                                "order_id": order_id,
                                "restaurant_id": rest_id,
                                "amount_cents": data.get("amount_total", 0),
                            },
                        )
                        if sms_result.success:
                            logger.info(f"[Stripe] Payment confirmation SMS sent for {order_id} (id={sms_result.message_id})")
                        else:
                            logger.warning(f"[Stripe] Payment SMS failed for {order_id}: {sms_result.error_code}: {sms_result.error_message}")
                except Exception as e:
                    logger.warning(f"[Stripe] Payment SMS failed: {e}")

        elif checkout_mode == "subscription":
            # --- SUBSCRIPTION CHECKOUT (with 7-day trial) ---
            restaurant_id = meta.get("restaurant_id")
            subscription_id = data.get("subscription")
            customer_id = data.get("customer")
            plan_name = meta.get("plan", "STARTER")
            plan_features = get_plan_features(plan_name)
            trial_ends_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            if restaurant_id:
                for _coll in all_collections:
                    await _coll.update_one(
                        {"id": restaurant_id},
                        {"$set": {
                            "stripe_customer_id": customer_id,
                            "stripe_subscription_id": subscription_id,
                            "billing_status": "trialing",
                            "plan": plan_name,
                            "monthly_call_limit": plan_features["monthly_call_limit"],
                            "subscription_started_at": datetime.now(timezone.utc).isoformat(),
                            "trial_ends_at": trial_ends_at,
                            "is_active": True,
                            "status": "active",
                            "onboarding_step": 7,
                            "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
                        }}
                    )
                logger.info(f"[Stripe] Trial started: restaurant={restaurant_id}, plan={plan_name}, trial_ends={trial_ends_at}")

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        subscription_id = data.get("id")
        customer_id = data.get("customer")
        status = data.get("status")
        # Resolve plan from the subscription's price ID
        price_to_plan = get_price_id_to_plan_map()
        items = data.get("items", {}).get("data", [])
        resolved_plan = None
        if items:
            sub_price_id = items[0].get("price", {}).get("id", "")
            resolved_plan = price_to_plan.get(sub_price_id)
        update_fields = {
            "stripe_subscription_id": subscription_id,
            "billing_status": status,
        }
        if resolved_plan:
            update_fields["plan"] = resolved_plan
            update_fields["monthly_call_limit"] = get_plan_features(resolved_plan)["monthly_call_limit"]
        for _coll in all_collections:
            await _coll.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": update_fields}
            )
        logger.info(f"[Stripe] Subscription {event_type}: customer={customer_id}, status={status}, plan={resolved_plan}")

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        # Check if within 7-day free cancellation window
        for _coll in all_collections:
            rest = await _coll.find_one({"stripe_customer_id": customer_id}, {"subscription_started_at": 1, "_id": 0})
            if rest and rest.get("subscription_started_at"):
                started = datetime.fromisoformat(rest["subscription_started_at"].replace("Z", "+00:00"))
                days_active = (datetime.now(timezone.utc) - started).days
                cancel_note = "free_cancellation" if days_active <= 7 else "standard_cancellation"
                logger.info(f"[Stripe] Subscription canceled: customer={customer_id}, days_active={days_active}, {cancel_note}")
            await _coll.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {"billing_status": "canceled"}}
            )

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        for _coll in all_collections:
            await _coll.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {"billing_status": "past_due"}}
            )
        logger.warning(f"[Stripe] Payment failed for customer {customer_id}")

    elif event_type == "invoice.paid":
        customer_id = data.get("customer")
        for _coll in all_collections:
            await _coll.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {"billing_status": "active", "monthly_call_count": 0}}
            )
        logger.info(f"[Stripe] Invoice paid for customer {customer_id} — call count reset")

    return JSONResponse({"received": True})


@api_router.get("/integrations/square/connect")
async def square_connect(restaurant_id: str = Query(...), user: Dict[str, Any] = Depends(get_current_user)):
    await ensure_restaurant_access(restaurant_id, user)
    application_id = os.environ.get("SQUARE_APPLICATION_ID", "")
    redirect_uri = os.environ.get("SQUARE_REDIRECT_URI", "")
    if not application_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="Square credentials are not configured")
    state = await issue_oauth_state(
        restaurant_id=restaurant_id,
        user_id=user["id"],
        provider="square",
    )
    connect_url = (
        "https://connect.squareup.com/oauth2/authorize"
        f"?client_id={application_id}&scope=ITEMS_READ+ORDERS_READ+PAYMENTS_READ"
        f"&session=false&state={state}&redirect_uri={redirect_uri}"
    )
    return {"connect_url": connect_url}


@api_router.get("/integrations/square/callback")
async def square_callback(code: Optional[str] = None, state: Optional[str] = None):
    if not code:
        raise HTTPException(status_code=400, detail="Missing Square authorization code")

    record = await consume_oauth_state(state=state, provider="square")
    restaurant_id = record["restaurant_id"]

    await db.integrations.update_one(
        {"provider": "square", "restaurant_id": restaurant_id},
        {"$set": {
            "provider": "square",
            "restaurant_id": restaurant_id,
            "status": "connected",
            "auth_code": code,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    for _coll in [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]:
        await _coll.update_one({"id": restaurant_id}, {"$set": {"square_connected": True}})
    return {"connected": True, "restaurant_id": restaurant_id}


# ─────────────────────────────────────────────────────────────
# STRIPE CONNECT — Restaurant onboarding (order prepayment)
# ─────────────────────────────────────────────────────────────

@api_router.get("/integrations/stripe/connect")
async def stripe_connect(
    restaurant_id: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a Stripe Connect Express OAuth URL for the restaurant owner."""
    await ensure_restaurant_access(restaurant_id, user)
    client_id = os.environ.get("STRIPE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=400, detail="Stripe Connect is not configured — set STRIPE_CLIENT_ID on Render")
    frontend_url = get_frontend_url()
    redirect_uri = os.environ.get(
        "STRIPE_CONNECT_REDIRECT_URI",
        f"{frontend_url}/api/integrations/stripe/callback"
    )
    state = await issue_oauth_state(
        restaurant_id=restaurant_id,
        user_id=user["id"],
        provider="stripe_connect",
    )
    connect_url = (
        "https://connect.stripe.com/oauth/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&scope=read_write"
        f"&state={state}"
        f"&redirect_uri={redirect_uri}"
        f"&stripe_user[business_type]=company"
    )
    return {"connect_url": connect_url}


@api_router.get("/integrations/stripe/callback")
async def stripe_connect_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Stripe redirects here after restaurant owner completes Connect onboarding.
    Exchanges the OAuth code for a stripe_account_id and saves to DB.

    The `state` is an opaque single-use token previously issued by
    /integrations/stripe/connect and bound to the requesting user + tenant.
    """
    frontend_url = get_frontend_url()
    from starlette.responses import RedirectResponse

    if error or not code:
        logger.warning(f"[Stripe Connect] Callback error: {error}")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?stripe_error=true",
            status_code=302,
        )

    try:
        record = await consume_oauth_state(state=state, provider="stripe_connect")
    except HTTPException:
        logger.warning("[Stripe Connect] Callback rejected: invalid or expired state")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?stripe_error=true",
            status_code=302,
        )
    restaurant_id = record["restaurant_id"]

    try:
        response = stripe.OAuth.token(grant_type="authorization_code", code=code)
        stripe_account_id = response.get("stripe_user_id")
        if not stripe_account_id:
            raise ValueError("No stripe_user_id in response")

        # Save to all business collections
        all_collections = [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]
        for _coll in all_collections:
            await _coll.update_one(
                {"id": restaurant_id},
                {"$set": {
                    "stripe_account_id": stripe_account_id,
                    "stripe_connect_status": "active",
                    "stripe_connect_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
        logger.info(f"[Stripe Connect] Restaurant {restaurant_id} connected")
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?stripe_connected=true",
            status_code=302,
        )
    except Exception as e:
        logger.error(f"[Stripe Connect] Callback failed: {e}", exc_info=True)
        return RedirectResponse(
            url=f"{frontend_url}/dashboard/integrations?stripe_error=true",
            status_code=302,
        )


@api_router.post("/integrations/stripe/disconnect")
async def stripe_connect_disconnect(
    payload: DisconnectStripeRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Disconnect Stripe Connect for a restaurant."""
    restaurant = await ensure_restaurant_access(payload.restaurant_id, user)
    stripe_account_id = restaurant.get("stripe_account_id")
    if stripe_account_id:
        try:
            stripe.OAuth.deauthorize(
                client_id=os.environ.get("STRIPE_CLIENT_ID", ""),
                stripe_user_id=stripe_account_id,
            )
        except Exception as e:
            logger.warning(f"[Stripe Connect] Deauthorize failed (non-critical): {e}")

    all_collections = [db.restaurants, db.clinics, db.salons, db.home_services, db.legal]
    for _coll in all_collections:
        await _coll.update_one(
            {"id": payload.restaurant_id},
            {"$set": {
                "stripe_account_id": None,
                "stripe_connect_status": "disconnected",
            }},
        )
    logger.info(f"[Stripe Connect] Restaurant {payload.restaurant_id} disconnected")
    return {"disconnected": True}


@api_router.get("/integrations/stripe/status")
async def stripe_connect_status(
    restaurant_id: str = Query(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Return Stripe Connect status for a restaurant."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    return {
        "connected": restaurant.get("stripe_connect_status") == "active",
        "stripe_account_id": restaurant.get("stripe_account_id"),
        "status": restaurant.get("stripe_connect_status") or "not_connected",
    }
# ─────────────────────────────────────────────────────────────
# STRIPE REFUND — Order refund via Stripe Connect
# ─────────────────────────────────────────────────────────────

@api_router.post("/restaurants/{restaurant_id}/orders/{call_sid}/refund")
async def refund_order(
    restaurant_id: str,
    call_sid: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Refund a prepaid order via Stripe Connect (direct charge)."""
    restaurant = await ensure_restaurant_access(restaurant_id, user)
    stripe_account_id = restaurant.get("stripe_account_id")
    if not stripe_account_id:
        raise HTTPException(status_code=400, detail="Restaurant is not connected to Stripe")

    call = await db.call_records.find_one(
        {"call_sid": call_sid, "restaurant_id": restaurant_id},
        {"_id": 0},
    )
    if not call:
        raise HTTPException(status_code=404, detail="Order not found")

    payment_status = call.get("payment_status")
    if payment_status == "refunded":
        raise HTTPException(status_code=400, detail="Order has already been refunded")
    if payment_status != "paid":
        raise HTTPException(status_code=400, detail="Order has not been paid — cannot refund")

    stripe_payment_id = call.get("stripe_payment_id")
    if not stripe_payment_id:
        raise HTTPException(status_code=400, detail="No Stripe payment ID found for this order")

    try:
        refund = stripe.Refund.create(
            payment_intent=stripe_payment_id,
            reverse_transfer=True,
            refund_application_fee=True,
        )
    except Exception as e:
        logger.error(f"[Stripe Refund] Error for {call_sid}: {e}")
        raise HTTPException(status_code=400, detail=f"Refund failed: {str(e)}")

    await db.call_records.update_one(
        {"call_sid": call_sid},
        {"$set": {
            "payment_status": "refunded",
            "refunded_at": datetime.now(timezone.utc).isoformat(),
            "stripe_refund_id": refund.id,
        }},
    )
    logger.info(f"[Stripe Refund] Order {call_sid} refunded → {refund.id}")

    # Send refund confirmation SMS (non-blocking)
    try:
        caller_number = call.get("caller_number")
        if caller_number:
            order_total = call.get("order_total", 0)
            amount_str = f"${order_total / 100:.2f}"
            rest_name = restaurant.get("name", "the restaurant")
            sms_body = (
                f"Your payment of {amount_str} for your order at {rest_name} has been refunded. "
                f"It may take 5-10 business days to appear on your statement."
            )
            import telnyx_service
            sms_result = await telnyx_service.send_sms(
                to=caller_number,
                body=sms_body,
                idempotency_key=f"refund:{call_sid}:{refund.id}",
                metadata={
                    "purpose": "refund_confirmation",
                    "call_sid": call_sid,
                    "restaurant_id": restaurant_id,
                    "refund_id": refund.id,
                    "amount_cents": order_total,
                },
            )
            if sms_result.success:
                logger.info(f"[Stripe Refund] Refund SMS sent for {call_sid} (id={sms_result.message_id})")
            else:
                logger.warning(f"[Stripe Refund] Refund SMS failed for {call_sid}: {sms_result.error_code}: {sms_result.error_message}")
    except Exception as e:
        logger.warning(f"[Stripe Refund] SMS failed (non-critical): {e}")

    return {"refunded": True, "refund_id": refund.id, "amount": call.get("order_total", 0)}


@api_router.post("/webhooks/square")
async def square_webhook(request: Request):
    """Square webhook handler with HMAC-SHA256 signature verification + idempotency.

    Verification: Square signs each webhook with HMAC-SHA256 over
    f"{notification_url}{body}" using the merchant's webhook signature key.
    The signature arrives in the X-Square-Hmacsha256-Signature header.

    Idempotency: Square retries failed deliveries. We dedupe on event_id,
    storing seen ids in the webhook_events collection with a 7-day TTL.

    If SQUARE_WEBHOOK_SIGNATURE_KEY is not configured, the endpoint returns
    503 — refusing to process unsigned traffic is safer than accepting it.
    """
    signature_key = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "").strip()
    if not signature_key:
        logger.warning("square_webhook called but SQUARE_WEBHOOK_SIGNATURE_KEY is not configured")
        raise HTTPException(
            status_code=503,
            detail="Square webhook handler is not configured. Set SQUARE_WEBHOOK_SIGNATURE_KEY.",
        )

    body = await request.body()
    provided_sig = request.headers.get("X-Square-Hmacsha256-Signature", "")
    if not provided_sig:
        raise HTTPException(status_code=401, detail="Missing X-Square-Hmacsha256-Signature header")

    # Reconstruct the notification URL from the request rather than trusting an env var.
    notification_url = str(request.url)
    signed_payload = (notification_url + body.decode("utf-8")).encode("utf-8")
    expected_sig = base64.b64encode(
        hmac.new(signature_key.encode("utf-8"), signed_payload, hashlib.sha256).digest()
    ).decode("utf-8")

    if not hmac.compare_digest(expected_sig, provided_sig):
        logger.warning("square_webhook signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid Square signature")

    try:
        event = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = event.get("event_id") or event.get("id")
    event_type = event.get("type", "")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event_id in payload")

    existing = await db.webhook_events.find_one({"provider": "square", "event_id": event_id})
    if existing:
        return JSONResponse({"received": True, "deduped": True})

    if event_type == "oauth.authorization.revoked":
        merchant_id = (event.get("data") or {}).get("object", {}).get("merchant_id") or event.get("merchant_id")
        if merchant_id:
            await db.integrations.update_many(
                {"provider": "square", "merchant_id": merchant_id},
                {"$set": {"status": "disconnected", "disconnected_at": datetime.now(timezone.utc).isoformat()}},
            )
            logger.info(f"square_webhook: marked merchant {merchant_id} as disconnected")
    else:
        logger.info(f"square_webhook: received unhandled event type {event_type}")

    await db.webhook_events.insert_one({
        "provider": "square",
        "event_id": event_id,
        "event_type": event_type,
        "received_at": datetime.now(timezone.utc),
    })

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
        "telnyx": {
            "available": bool(os.environ.get("TELNYX_API_KEY")),
            "phone_number": os.environ.get("TELNYX_PHONE_NUMBER"),
            "status": test_mode.get("integrations", {}).get("telnyx", {}).get("status", "unknown"),
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
    
    # Feed analysis to auto-learning service
    try:
        learning_service = get_learning_service(db)
        order_completed = call.get("order_json") is not None
        order_total = call.get("order_json", {}).get("total", 0) if order_completed else 0
        
        learning_result = await learning_service.process_call_analysis(
            restaurant_id=call.get("restaurant_id", ""),
            call_id=call_id,
            analysis=analysis,
            order_completed=order_completed,
            order_total=order_total,
        )
        analysis["learning_actions"] = learning_result
    except Exception as e:
        logger.warning(f"Auto-learning processing failed: {e}")
    
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
        offers_delivery=restaurant.get("offers_delivery", True),
        offers_reservations=restaurant.get("offers_reservations", True),
        delivery_enabled=restaurant.get("delivery_enabled", config.get("delivery_enabled", True) if config else True),
        delivery_minimum=config.get("delivery_minimum", 1500),
        delivery_fee=restaurant.get("delivery_fee", 0),
        delivery_zip_codes=restaurant.get("delivery_zip_codes", []),
        delivery_radius_miles=restaurant.get("delivery_radius_miles", 5.0),
        delivery_eta_offset_minutes=restaurant.get("delivery_eta_offset_minutes", 15),
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
    
    # Feed to auto-learning
    try:
        learning_service = get_learning_service(db)
        await learning_service.process_call_analysis(
            restaurant_id=restaurant_id,
            call_id=f"test_{uuid.uuid4().hex[:8]}",
            analysis=analysis,
            order_completed=order_json is not None,
            order_total=total,
        )
    except Exception as e:
        logger.warning(f"Auto-learning failed for test call: {e}")

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
CF_BYPASS_PREFIXES = ["/api/telnyx", "/api/call", "/health", "/api/integrations/stripe/callback", "/api/calendar/google/callback", "/api/integrations/square/callback", "/api/webhooks/stripe"]

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
# INCLUDE ROUTER (CORS already added at startup for correct middleware order)
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
async def _ensure_webhook_idempotency_index():
    """Create TTL indexes for short-lived security collections.

    webhook_events — Square retries failed deliveries; we dedupe on event_id.
        Index expires entries 7 days after receipt to bound storage growth.
    oauth_states — OAuth CSRF tokens issued by /integrations/{square,stripe}/connect.
        Each document carries its own `expires_at`, so the index uses
        expireAfterSeconds=0 to remove documents once that timestamp passes.
    """
    try:
        await db.webhook_events.create_index("received_at", expireAfterSeconds=7 * 24 * 60 * 60)
        await db.oauth_states.create_index("expires_at", expireAfterSeconds=0)
        logger.info("Security TTL indexes ensured (webhook_events, oauth_states)")
    except Exception as e:
        logger.warning(f"Could not create security TTL indexes: {e}")


@app.on_event("startup")
async def _register_telnyx_sms_persister():
    """Wire telnyx_service's persistence callback to MongoDB."""
    import telnyx_service

    async def _persist(record: Dict[str, Any]) -> None:
        await db.sms_messages.insert_one(record)

    telnyx_service.set_sms_persister(_persist)
    logger.info("Telnyx SMS persister registered (writes to db.sms_messages)")


@app.on_event("startup")
async def startup_scheduler():
    """Start background scheduler on app startup."""
    try:
        from scheduler_service import start_scheduler
        start_scheduler(db)
        logger.info("Background scheduler started")
    except Exception as e:
        logger.warning(f"Could not start scheduler: {e}")


# Zombie-call sweeper config
ZOMBIE_SWEEPER_INTERVAL_SECS = int(os.environ.get("ZOMBIE_SWEEPER_INTERVAL_SECS", "60"))
ZOMBIE_CALL_MAX_AGE_SECS = int(os.environ.get("ZOMBIE_CALL_MAX_AGE_SECS", "600"))  # 10 min
_zombie_sweeper_task: Optional[asyncio.Task] = None


async def _zombie_call_sweeper() -> None:
    """Backstop for hangup paths that we missed in code.

    With auto_hang_up=False on TelnyxFrameSerializer, every legitimate
    hangup path must explicitly call telnyx_service.hang_up_call. If we
    ever miss one (bug, exception, process crash mid-call), the Telnyx
    leg stays alive and we keep billing for empty audio time. This task
    periodically scans active_calls for entries older than 10 minutes
    and force-hangs-up via Telnyx as a final safety net.

    If this ever fires in production, treat it as a bug to investigate —
    the sweeper is not the primary mechanism for anything.
    """
    import telnyx_service
    from datetime import datetime, timezone, timedelta
    logger.info(
        f"Zombie-call sweeper started (interval={ZOMBIE_SWEEPER_INTERVAL_SECS}s, "
        f"max_age={ZOMBIE_CALL_MAX_AGE_SECS}s)"
    )
    while not _shutdown_requested:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ZOMBIE_CALL_MAX_AGE_SECS)).isoformat()
            zombies = await db.active_calls.find(
                {"started_at": {"$lt": cutoff}}, {"call_sid": 1}
            ).to_list(50)
            for doc in zombies:
                call_sid = doc.get("call_sid")
                if not call_sid:
                    continue
                logger.warning(
                    f"[zombie sweeper] Active call {call_sid} older than "
                    f"{ZOMBIE_CALL_MAX_AGE_SECS}s — force hangup. "
                    f"(Indicates a missed hangup path; investigate.)"
                )
                try:
                    await telnyx_service.hang_up_call(call_sid)
                except Exception as e:
                    logger.error(f"[zombie sweeper] Telnyx hangup for {call_sid} failed: {e}")
                try:
                    await db.active_calls.delete_one({"call_sid": call_sid})
                except Exception as e:
                    logger.error(f"[zombie sweeper] active_calls cleanup for {call_sid} failed: {e}")
        except Exception as e:
            logger.error(f"[zombie sweeper] iteration failed (continuing): {e}", exc_info=True)
        try:
            await asyncio.sleep(ZOMBIE_SWEEPER_INTERVAL_SECS)
        except asyncio.CancelledError:
            break
    logger.info("Zombie-call sweeper stopped")


@app.on_event("startup")
async def _start_zombie_sweeper():
    """Spawn the zombie-call sweeper background task on app startup."""
    global _zombie_sweeper_task
    _zombie_sweeper_task = asyncio.create_task(_zombie_call_sweeper())


@app.on_event("shutdown")
async def shutdown_db_client():
    """Clean up on shutdown."""
    try:
        from scheduler_service import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    if _zombie_sweeper_task is not None and not _zombie_sweeper_task.done():
        _zombie_sweeper_task.cancel()
    client.close()