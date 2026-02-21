from fastapi import FastAPI, APIRouter, HTTPException, Query, Request, WebSocket
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
import random
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'ringai_db')]

# Gemini + Pipeline imports
from gemini_service import (
    is_gemini_available, parse_menu_text, analyse_call_transcript,
    get_conversation_response, build_system_prompt,
)
from call_pipeline import (
    is_pipeline_available, create_call_pipeline,
    generate_twiml_stream_response, provision_phone_number,
    validate_twilio_request,
)

# Create the main app
app = FastAPI(title="RingAI API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# PYDANTIC MODELS
# ============================================================

class RestaurantBase(BaseModel):
    name: str
    cuisine_type: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: str = "America/Chicago"
    address: Optional[str] = None

class RestaurantCreate(RestaurantBase):
    pass

class RestaurantUpdate(BaseModel):
    name: Optional[str] = None
    cuisine_type: Optional[str] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None

class Restaurant(RestaurantBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_active: bool = False
    plan: str = "STARTER"
    monthly_call_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class RestaurantConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    persona: str = "friendly"
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    business_rules: List[str] = []
    few_shot_examples: List[Dict] = []
    escalation_rules: List[str] = []
    upsell_enabled: bool = True
    disclosure_text: str = "Hi! I'm an AI assistant. How can I help you today?"
    delivery_enabled: bool = True
    delivery_minimum: int = 1500
    operating_hours: Dict[str, Any] = {}

class RestaurantConfigUpdate(BaseModel):
    persona: Optional[str] = None
    voice_id: Optional[str] = None
    business_rules: Optional[List[str]] = None
    escalation_rules: Optional[List[str]] = None
    upsell_enabled: Optional[bool] = None
    disclosure_text: Optional[str] = None
    delivery_enabled: Optional[bool] = None
    delivery_minimum: Optional[int] = None
    operating_hours: Optional[Dict[str, Any]] = None

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
    modifiers: List[MenuItemModifier] = []
    allergens: List[str] = []
    image_url: Optional[str] = None

class MenuItemCreate(MenuItemBase):
    pass

class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[int] = None
    available: Optional[bool] = None
    modifiers: Optional[List[MenuItemModifier]] = None
    allergens: Optional[List[str]] = None

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
# ROOT ENDPOINT
# ============================================================

@api_router.get("/")
async def root():
    return {"message": "RingAI API v1.0", "status": "operational"}

# ============================================================
# RESTAURANT ENDPOINTS
# ============================================================

@api_router.post("/restaurants", response_model=Restaurant)
async def create_restaurant(data: RestaurantCreate):
    restaurant = Restaurant(**data.model_dump())
    doc = restaurant.model_dump()
    await db.restaurants.insert_one(doc)
    return restaurant

@api_router.get("/restaurants")
async def list_restaurants():
    restaurants = await db.restaurants.find({}, {"_id": 0}).to_list(100)
    return restaurants

@api_router.get("/restaurants/{restaurant_id}")
async def get_restaurant(restaurant_id: str):
    restaurant = await db.restaurants.find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant

@api_router.put("/restaurants/{restaurant_id}")
async def update_restaurant(restaurant_id: str, data: RestaurantUpdate):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db.restaurants.update_one({"id": restaurant_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = await db.restaurants.find_one({"id": restaurant_id}, {"_id": 0})
    return restaurant

# ============================================================
# RESTAURANT CONFIG ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/config")
async def get_restaurant_config(restaurant_id: str):
    config = await db.restaurant_configs.find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    if not config:
        # Return default config
        default_config = RestaurantConfig(restaurant_id=restaurant_id)
        return default_config.model_dump()
    return config

@api_router.put("/restaurants/{restaurant_id}/config")
async def update_restaurant_config(restaurant_id: str, data: RestaurantConfigUpdate):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    existing = await db.restaurant_configs.find_one({"restaurant_id": restaurant_id})
    if existing:
        await db.restaurant_configs.update_one({"restaurant_id": restaurant_id}, {"$set": update_data})
    else:
        config = RestaurantConfig(restaurant_id=restaurant_id, **update_data)
        await db.restaurant_configs.insert_one(config.model_dump())
    config = await db.restaurant_configs.find_one({"restaurant_id": restaurant_id}, {"_id": 0})
    return config

# ============================================================
# MENU ITEM ENDPOINTS
# ============================================================

@api_router.post("/restaurants/{restaurant_id}/menu", response_model=MenuItem)
async def create_menu_item(restaurant_id: str, data: MenuItemCreate):
    item = MenuItem(restaurant_id=restaurant_id, **data.model_dump())
    await db.menu_items.insert_one(item.model_dump())
    return item

@api_router.get("/restaurants/{restaurant_id}/menu")
async def list_menu_items(restaurant_id: str, category: Optional[str] = None):
    query = {"restaurant_id": restaurant_id}
    if category:
        query["category"] = category
    items = await db.menu_items.find(query, {"_id": 0}).to_list(500)
    return items

@api_router.put("/menu/{item_id}")
async def update_menu_item(item_id: str, data: MenuItemUpdate):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if isinstance(update_data.get('modifiers'), list):
        update_data['modifiers'] = [m.model_dump() if hasattr(m, 'model_dump') else m for m in update_data['modifiers']]
    result = await db.menu_items.update_one({"id": item_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")
    item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    return item

@api_router.delete("/menu/{item_id}")
async def delete_menu_item(item_id: str):
    result = await db.menu_items.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return {"message": "Menu item deleted"}

@api_router.patch("/menu/{item_id}/toggle")
async def toggle_menu_item_availability(item_id: str):
    item = await db.menu_items.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    new_availability = not item.get("available", True)
    await db.menu_items.update_one({"id": item_id}, {"$set": {"available": new_availability}})
    return {"id": item_id, "available": new_availability}

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
):
    query = {"restaurant_id": restaurant_id}
    if status and status != "ALL":
        query["status"] = status
    if search:
        query["$or"] = [
            {"caller_number": {"$regex": search, "$options": "i"}},
            {"caller_name": {"$regex": search, "$options": "i"}},
        ]
    total = await db.call_records.count_documents(query)
    calls = await db.call_records.find(query, {"_id": 0}).sort("started_at", -1).skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"calls": calls, "total": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit}

@api_router.get("/calls/{call_id}")
async def get_call(call_id: str):
    call = await db.call_records.find_one({"id": call_id}, {"_id": 0})
    if not call:
        raise HTTPException(status_code=404, detail="Call record not found")
    return call

# ============================================================
# ANALYTICS / DASHBOARD ENDPOINTS
# ============================================================

@api_router.get("/restaurants/{restaurant_id}/analytics/summary")
async def get_analytics_summary(restaurant_id: str):
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

    # Daily call data for chart (last 7 days)
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

    # Hourly distribution
    hourly = [0] * 24
    for c in all_calls:
        try:
            h = int(c.get("started_at", "")[11:13])
            hourly[h] += 1
        except (ValueError, IndexError):
            pass
    hourly_data = [{"hour": f"{h:02d}:00", "calls": hourly[h]} for h in range(24)]

    # Top items from orders
    item_counts = {}
    for c in all_calls:
        order = c.get("order_json")
        if order and isinstance(order, dict):
            for item in order.get("items", []):
                name = item.get("name", "Unknown")
                item_counts[name] = item_counts.get(name, 0) + item.get("quantity", 1)
    top_items = sorted([{"name": k, "count": v} for k, v in item_counts.items()], key=lambda x: -x["count"])[:10]

    # Recent calls
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
        "daily_call_data": daily_data,
        "hourly_distribution": hourly_data,
        "top_items": top_items,
        "recent_calls": recent_calls,
    }

# ============================================================
# ONBOARDING ENDPOINTS
# ============================================================

@api_router.post("/onboarding/menu/parse")
async def parse_menu(data: OnboardingMenuParse):
    """Parse menu text using Gemini 2.5 Flash (falls back to basic parser if key not set)"""
    result = await parse_menu_text(data.menu_text)
    return result

@api_router.post("/onboarding/menu/confirm")
async def confirm_menu(restaurant_id: str = Query(...), items: List[Dict[str, Any]] = []):
    """Save parsed menu items to DB"""
    # Delete old menu items
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
async def activate_restaurant(data: OnboardingActivate):
    """Activate restaurant and assign phone number"""
    result = await db.restaurants.update_one(
        {"id": data.restaurant_id},
        {"$set": {"is_active": True, "phone_number": f"+1555{random.randint(1000000,9999999)}"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = await db.restaurants.find_one({"id": data.restaurant_id}, {"_id": 0})
    return restaurant

# ============================================================
# DEMO/SIMULATION ENDPOINTS
# ============================================================

@api_router.post("/demo/simulate-call")
async def simulate_call(restaurant_id: str = Query(...)):
    """Simulate a complete AI phone call for demo purposes"""
    restaurant = await db.restaurants.find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    menu_items = await db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

    # Generate realistic call data
    caller_names = ["Sarah Mitchell", "James Wilson", "Maria Garcia", "David Kim", "Emma Johnson", "Robert Chen", "Lisa Park", "Michael Brown", "Jennifer Lee", "Chris Taylor"]
    caller = random.choice(caller_names)
    phone = f"+1{random.randint(200,999)}{random.randint(1000000,9999999)}"

    # Pick random items for order
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
    quality = random.randint(78, 99)
    is_escalated = random.random() < 0.08
    status = "ESCALATED" if is_escalated else "COMPLETED"

    # Build realistic transcript
    restaurant_name = restaurant.get("name", "the restaurant")
    item_names = [i["name"] for i in items_for_order]
    transcript = [
        {"role": "ai", "text": f"Hi! I'm an AI assistant for {restaurant_name}. How can I help you today?", "timestamp": "00:00"},
        {"role": "customer", "text": f"Hi, I'd like to place an order for pickup.", "timestamp": "00:03"},
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
        {"role": "ai", "text": "Let me read back your order: " + ", ".join([str(i["quantity"]) + "x " + i["name"] for i in items_for_order]) + f". Your total is ${total/100:.2f}. Is that correct?", "timestamp": "00:25"},
        {"role": "customer", "text": "Yes, that's right.", "timestamp": "00:30"},
        {"role": "ai", "text": f"Your order has been placed! It'll be ready for pickup in about 20 minutes. Thank you for calling {restaurant_name}!", "timestamp": "00:33"},
    ])

    analysis = {
        "quality_score": quality,
        "order_accuracy": "accurate",
        "issues": random.sample(["Minor pause before confirming order", "Could have offered drinks", "Slight delay in greeting"], random.randint(0, 1)),
        "highlights": random.sample(["Clear order readback", "Friendly tone", "Efficient flow", "Natural conversation", "Proper greeting"], random.randint(2, 4)),
        "menu_suggestions": [],
        "rule_suggestions": [],
        "summary": f"Successful {len(items_for_order)}-item pickup order from {caller}. Call handled smoothly with clear confirmation."
    }

    now = datetime.now(timezone.utc)
    start_offset = random.randint(0, 3600 * 4)  # Within last 4 hours
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
        order_json={"items": items_for_order, "total": total, "type": random.choice(["pickup", "pickup", "delivery"]), "special_instructions": ""},
        pos_order_id=f"POS-{random.randint(10000,99999)}" if not is_escalated else None,
        quality_score=quality,
        analysis_json=analysis,
        claude_tokens_used=random.randint(800, 2500),
        order_total=total,
    )

    await db.call_records.insert_one(call.model_dump())
    return call.model_dump()

@api_router.post("/demo/seed")
async def seed_demo_data(restaurant_id: str = Query(...)):
    """Generate seed data for a restaurant demo"""
    restaurant = await db.restaurants.find_one({"id": restaurant_id}, {"_id": 0})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # Generate 30-50 historical calls across the last 7 days
    num_calls = random.randint(30, 50)
    now = datetime.now(timezone.utc)

    for _ in range(num_calls):
        # Random time in last 7 days
        offset = random.randint(0, 7 * 24 * 3600)
        call_time = now - timedelta(seconds=offset)
        # Only during business hours (10am - 10pm)
        hour = call_time.hour
        if hour < 10 or hour > 22:
            call_time = call_time.replace(hour=random.randint(10, 22))

        # Simulate call
        await simulate_call_internal(restaurant_id, call_time)

    return {"message": f"Generated {num_calls} demo calls", "restaurant_id": restaurant_id}


async def simulate_call_internal(restaurant_id: str, call_time: datetime):
    """Internal function to create a simulated call at a specific time"""
    menu_items = await db.menu_items.find({"restaurant_id": restaurant_id, "available": True}, {"_id": 0}).to_list(100)

    caller_names = ["Sarah Mitchell", "James Wilson", "Maria Garcia", "David Kim", "Emma Johnson",
                    "Robert Chen", "Lisa Park", "Michael Brown", "Jennifer Lee", "Chris Taylor",
                    "Ana Rodriguez", "Tom Harris", "Priya Patel", "Kevin O'Brien", "Sophie Turner"]
    caller = random.choice(caller_names)
    phone = f"+1{random.randint(200,999)}{random.randint(1000000,9999999)}"

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
        items_for_order.append({"name": item.get("name", "Item"), "quantity": qty, "price": item.get("price", 999), "modifiers": [], "subtotal": subtotal})

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
        "summary": f"{'Successful' if status == 'COMPLETED' else 'Escalated'} call from {caller}. {len(items_for_order)} items ordered."
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
            {"role": "ai", "text": f"Your total is ${total/100:.2f}. Order placed!", "timestamp": "00:15"},
        ],
        order_json={"items": items_for_order, "total": total, "type": random.choice(["pickup", "delivery"])},
        pos_order_id=f"POS-{random.randint(10000,99999)}",
        quality_score=quality,
        analysis_json=analysis,
        claude_tokens_used=random.randint(600, 2200),
        order_total=total,
    )
    await db.call_records.insert_one(call.model_dump())

# ============================================================
# SEED INITIAL DEMO RESTAURANT
# ============================================================

@app.on_event("startup")
async def startup_seed():
    """Seed a demo restaurant if none exists"""
    count = await db.restaurants.count_documents({})
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
        )
        await db.restaurants.insert_one(demo_restaurant.model_dump())

        # Seed config
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

        # Seed menu
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
            {"name": "Chicken Parmesan", "category": "Entrees", "price": 2299, "description": "Breaded chicken with marinara & melted mozzarella", "allergens": ["gluten", "dairy", "eggs"], "available": True},
            {"name": "Grilled Salmon", "category": "Entrees", "price": 2699, "description": "Atlantic salmon with lemon caper sauce", "allergens": [], "available": True},
            {"name": "Veal Marsala", "category": "Entrees", "price": 2899, "description": "Veal medallions in marsala wine mushroom sauce", "allergens": ["dairy"], "available": True},
            {"name": "Eggplant Parmigiana", "category": "Entrees", "price": 1899, "description": "Layered eggplant with marinara & mozzarella", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Tiramisu", "category": "Desserts", "price": 1099, "description": "Classic Italian coffee-flavored dessert", "allergens": ["gluten", "dairy", "eggs"], "available": True},
            {"name": "Panna Cotta", "category": "Desserts", "price": 999, "description": "Vanilla cream with berry compote", "allergens": ["dairy"], "available": True},
            {"name": "Cannoli", "category": "Desserts", "price": 899, "description": "Crispy shells with sweet ricotta filling", "allergens": ["gluten", "dairy"], "available": True},
            {"name": "Espresso", "category": "Beverages", "price": 399, "description": "Double shot Italian espresso", "allergens": [], "available": True},
            {"name": "Italian Soda", "category": "Beverages", "price": 499, "description": "Sparkling water with choice of flavor", "allergens": [], "available": True},
            {"name": "House Red Wine (glass)", "category": "Beverages", "price": 1299, "description": "Chianti Classico", "allergens": [], "available": True},
            {"name": "House White Wine (glass)", "category": "Beverages", "price": 1199, "description": "Pinot Grigio", "allergens": [], "available": True},
        ]
        for item_data in menu_items_data:
            item = MenuItem(restaurant_id="demo-restaurant-001", **item_data)
            await db.menu_items.insert_one(item.model_dump())

        # Seed historical call data
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
# INCLUDE ROUTER & MIDDLEWARE
# ============================================================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
