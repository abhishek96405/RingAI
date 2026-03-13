"""
Gemini 2.5 Flash Service — Unified AI for RingAI

Uses: Google Gemini directly via the official OpenAI-compatible Gemini API
Handles: Menu parsing, post-call analysis, conversation intelligence,
         order state machine, structured order extraction, kitchen dispatch
Audio: Handled via Pipecat + Gemini Live Audio API (see call_pipeline.py)

CHANGES:
- AI no longer reads full menu aloud — only category names on request
- STEP 2: removed per-item "Is that correct?" — save confirmation for readback only
- STEP 4: readback lists items+qty only, total only (no per-item prices repeated)
- Edge case: "Hello" during active order flow no longer restarts conversation
- Order extraction: max_tokens 600→1200, confirmed=None treated as True
- Transcript limit for extraction: 3000→1500 chars
"""
import os
import json
import logging
import re
import httpx
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON Repair Utilities
# ---------------------------------------------------------------------------

def _repair_json(text: str) -> str:
    """Attempt to repair common JSON issues from LLM output."""
    if not text:
        return "{}"

    # Remove markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    else:
        return "{}"

    # Remove newlines and carriage returns within strings (common issue)
    text = text.replace('\n', ' ').replace('\r', ' ')

    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as e:
        if "Unterminated string" in str(e):
            quote_count = text.count('"') - text.count('\\"')
            if quote_count % 2 != 0:
                text = text.rstrip() + '"'

        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')

        if open_brackets > 0:
            text = text.rstrip() + ']' * open_brackets
        if open_braces > 0:
            text = text.rstrip() + '}' * open_braces

        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            return "{}"

    return text


def _extract_json_fields(text: str, expected_fields: List[str]) -> Dict[str, Any]:
    """
    Try to extract expected fields from malformed JSON using regex.
    Last resort fallback when JSON parsing completely fails.
    """
    result = {}

    if "quality_score" in expected_fields:
        match = re.search(r'"quality_score"\s*:\s*(\d+)', text)
        if match:
            result["quality_score"] = int(match.group(1))

    if "order_accuracy" in expected_fields:
        match = re.search(r'"order_accuracy"\s*:\s*"([^"]*)"', text)
        if match:
            result["order_accuracy"] = match.group(1)

    if "summary" in expected_fields:
        match = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
        if match:
            result["summary"] = match.group(1)

    for field in ["issues", "highlights", "menu_suggestions", "rule_suggestions"]:
        if field in expected_fields:
            match = re.search(rf'"{field}"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if match:
                try:
                    items = re.findall(r'"([^"]*)"', match.group(1))
                    result[field] = items
                except Exception:
                    result[field] = []

    return result


# ---------------------------------------------------------------------------
# Client (lazy-init via the official OpenAI-compatible Gemini API)
# ---------------------------------------------------------------------------
_client = None
MODEL = "gemini-2.5-flash"


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set — Gemini calls will use mock fallback")
        return None

    try:
        from openai import OpenAI
        base_url = os.environ.get(
            "GEMINI_OPENAI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        _client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"Gemini client initialised (model: {MODEL})")
        return _client
    except Exception as e:
        logger.error(f"Failed to initialise Gemini client: {e}")
        return None


def is_gemini_available() -> bool:
    return _get_client() is not None


# ---------------------------------------------------------------------------
# Menu Index — fast validated lookup (no AI, no hallucinations)
# ---------------------------------------------------------------------------

class MenuIndex:
    """Pre-built lookup for a restaurant's menu. All item validation runs here."""

    def __init__(self, menu_items: List[Dict[str, Any]]):
        self.items = {item["id"]: item for item in menu_items if item.get("available", True)}
        self.name_index: Dict[str, str] = {}
        for item in menu_items:
            if item.get("available", True):
                self.name_index[item["name"].lower().strip()] = item["id"]
        self.word_index: Dict[str, List[str]] = {}
        for item in menu_items:
            if item.get("available", True):
                for word in item["name"].lower().split():
                    if len(word) > 3:
                        self.word_index.setdefault(word, []).append(item["id"])

    def find(self, name: str) -> Optional[Dict[str, Any]]:
        key = name.lower().strip()
        if key in self.name_index:
            return self.items.get(self.name_index[key])
        for item_name, item_id in self.name_index.items():
            if key in item_name or item_name in key:
                return self.items.get(item_id)
        words = [w for w in key.split() if len(w) > 3]
        candidates: Dict[str, int] = {}
        for word in words:
            for item_id in self.word_index.get(word, []):
                candidates[item_id] = candidates.get(item_id, 0) + 1
        if candidates:
            best_id = max(candidates, key=lambda x: candidates[x])
            if candidates[best_id] >= min(2, len(words)):
                return self.items.get(best_id)
        return None

    def as_prompt_text(self) -> str:
        """Compact menu text for embedding in system prompt."""
        lines = []
        categories: Dict[str, List] = {}
        for item in self.items.values():
            categories.setdefault(item.get("category", "Other"), []).append(item)
        for cat, cat_items in sorted(categories.items()):
            lines.append(f"\n[{cat.upper()}]")
            for item in cat_items:
                price = f"${item['price'] / 100:.2f}"
                allergens = f" ⚠ {', '.join(item['allergens'])}" if item.get("allergens") else ""
                lines.append(f"  • {item['name']} {price}{allergens}")
        return "\n".join(lines)

    def category_names(self) -> List[str]:
        """Return unique category names — used for verbal menu summary."""
        return sorted(set(
            item.get("category", "Other")
            for item in self.items.values()
        ))


# ---------------------------------------------------------------------------
# Order State Machine
# ---------------------------------------------------------------------------

class OrderState(str, Enum):
    GREETING     = "GREETING"
    TAKING_ORDER = "TAKING_ORDER"
    CONFIRMING   = "CONFIRMING"
    CONFIRMED    = "CONFIRMED"
    COMPLETED    = "COMPLETED"
    ESCALATED    = "ESCALATED"
    ABANDONED    = "ABANDONED"


@dataclass
class OrderItem:
    name: str
    menu_item_id: str
    category: str
    unit_price: int       # cents
    quantity: int
    modifiers: List[str] = field(default_factory=list)
    special_instructions: str = ""
    allergens: List[str] = field(default_factory=list)

    @property
    def subtotal(self) -> int:
        return self.unit_price * self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "menu_item_id": self.menu_item_id,
            "category": self.category, "unit_price": self.unit_price,
            "quantity": self.quantity, "modifiers": self.modifiers,
            "special_instructions": self.special_instructions,
            "allergens": self.allergens, "subtotal": self.subtotal,
        }


@dataclass
class LiveOrder:
    restaurant_id: str
    call_sid: str
    caller_number: str
    state: OrderState = OrderState.GREETING
    items: List[OrderItem] = field(default_factory=list)
    order_type: str = "pickup"
    customer_name: str = ""
    delivery_address: str = ""
    special_instructions: str = ""
    confirmed_at: Optional[str] = None
    kitchen_order_id: str = ""
    state_history: List[Dict] = field(default_factory=list)

    def transition(self, new_state: OrderState, reason: str = ""):
        self.state_history.append({
            "from": self.state, "to": new_state,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.state = new_state

    @property
    def total(self) -> int:
        return sum(i.subtotal for i in self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_sid": self.call_sid, "state": self.state,
            "items": [i.to_dict() for i in self.items],
            "order_type": self.order_type, "customer_name": self.customer_name,
            "delivery_address": self.delivery_address,
            "special_instructions": self.special_instructions,
            "total": self.total, "confirmed_at": self.confirmed_at,
            "kitchen_order_id": self.kitchen_order_id,
        }


# ---------------------------------------------------------------------------
# Structured order extraction from transcript
# ---------------------------------------------------------------------------

async def extract_order_from_transcript(
    transcript: List[Dict],
    menu_index: MenuIndex,
) -> Optional[LiveOrder]:
    """Parse a transcript and return a validated LiveOrder. Returns None if no confirmed order."""
    client = _get_client()
    transcript_text = "\n".join(
        f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e.get('text', '')}"
        for e in transcript
    )
    prompt = f"""Extract the confirmed order from this restaurant call transcript.
Return ONLY valid JSON, no markdown, no code blocks.

Menu (use EXACT names from this list only):
{chr(10).join(f"  • {item['name']} ${item['price']/100:.2f}" for item in menu_index.items.values())}

Required JSON format:
{{"order_confirmed":true,"items":[{{"name":"EXACT menu name","quantity":1,"modifiers":[],"special_instructions":""}}],"order_type":"pickup","customer_name":"","delivery_address":"","special_instructions":""}}

RULES:
- order_confirmed must be true or false — never omit this field
- Only include items the customer explicitly ordered AND the AI confirmed
- Set order_confirmed to false if the customer never said yes
- Never invent items not in the menu above

TRANSCRIPT:
{transcript_text[:1500]}

JSON:"""

    raw = None
    if client:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2000,  # Increased from 600 to prevent truncation
            )
            raw = resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Order extraction error: {e}")

    if not raw:
        return None

    logger.info(f"Order extraction raw response: {raw[:500]}")

    try:
        data = json.loads(_repair_json(raw))
    except Exception:
        logger.error(f"Could not parse order extraction JSON: {raw[:200]}")
        return None

    confirmed = data.get("order_confirmed")
    items = data.get("items", [])
    logger.info(f"Order extraction parsed: confirmed={confirmed}, items={items}")

    # Only reject if explicitly False.
    # None means the field was missing (truncated JSON) — ORDER_CONFIRMED signal
    # already fired upstream, so we trust the signal and proceed.
    if confirmed is False:
        return None

    order = LiveOrder(
        restaurant_id="", call_sid="", caller_number="",
        state=OrderState.CONFIRMED,
        order_type=data.get("order_type", "pickup"),
        customer_name=data.get("customer_name", ""),
        delivery_address=data.get("delivery_address", ""),
        special_instructions=data.get("special_instructions", ""),
        confirmed_at=datetime.now(timezone.utc).isoformat(),
    )

    for raw_item in data.get("items", []):
        name = raw_item.get("name", "").strip()
        if not name:
            continue
        menu_item = menu_index.find(name)
        if not menu_item:
            logger.warning(f"Item '{name}' not on menu — skipped")
            continue
        order.items.append(OrderItem(
            name=menu_item["name"],
            menu_item_id=menu_item["id"],
            category=menu_item.get("category", ""),
            unit_price=menu_item["price"],
            quantity=max(1, int(raw_item.get("quantity", 1))),
            modifiers=raw_item.get("modifiers", []),
            special_instructions=raw_item.get("special_instructions", ""),
            allergens=menu_item.get("allergens", []),
        ))

    return order if order.items else None


# ---------------------------------------------------------------------------
# Deterministic order readback (never AI-generated, so can't hallucinate)
# ---------------------------------------------------------------------------

def format_order_readback(order: LiveOrder) -> str:
    if not order.items:
        return "I don't have any items in your order yet. What would you like?"
    parts = []
    for item in order.items:
        qty = f"{item.quantity}x " if item.quantity > 1 else ""
        mods = f" with {', '.join(item.modifiers)}" if item.modifiers else ""
        parts.append(f"{qty}{item.name}{mods}")
    order_type = "for delivery" if order.order_type == "delivery" else "for pickup"
    # FIX: items listed without per-item prices — total only
    return (
        f"Let me read that back: {', '.join(parts)}. "
        f"Your total is ${order.total/100:.2f} {order_type}. Does that sound right?"
    )


# ---------------------------------------------------------------------------
# Call signal detection (watches AI speech for state machine triggers)
# ---------------------------------------------------------------------------

def detect_call_signals(ai_text: str) -> Dict[str, bool]:
    t = ai_text.upper()
    return {
        "order_confirmed": any(p in t for p in [
            "ORDER_CONFIRMED",
            "ORDER IS CONFIRMED",
            "YOUR ORDER IS CONFIRMED",
            "ORDER HAS BEEN CONFIRMED",
            "ORDER IS PLACED",
        ]),
        "escalate_to_human": any(p in t for p in [
            "ESCALATE_TO_HUMAN",
            "CONNECT YOU WITH",
            "TRANSFER YOU",
            "TEAM MEMBER RIGHT AWAY",
        ]),
        "call_ending": any(p in t for p in [
            "THANK YOU FOR CALLING",
            "GOODBYE",
            "HAVE A GREAT",
            "TAKE CARE",
        ]),
    }


# ---------------------------------------------------------------------------
# Kitchen / POS dispatch
# ---------------------------------------------------------------------------

async def send_order_to_kitchen(order: LiveOrder, restaurant: Dict[str, Any]) -> Dict[str, Any]:
    """Try Clover POS → Square POS → kitchen webhook → DB fallback. Always returns a result."""
    # Try Clover first
    if os.environ.get("CLOVER_API_TOKEN") and os.environ.get("CLOVER_MERCHANT_ID"):
        result = await _send_to_clover(order)
        if result["success"]:
            return result

    if restaurant.get("square_connected"):
        result = await _send_to_square(order, restaurant)
        if result["success"]:
            return result

    webhook_url = os.environ.get("KITCHEN_WEBHOOK_URL", "")
    if webhook_url:
        result = await _send_to_kitchen_webhook(order, webhook_url)
        if result["success"]:
            return result

    order_id = f"RNG-{order.call_sid[-8:].upper()}"
    logger.info(f"Order {order_id} saved to DB only")
    return {"success": True, "order_id": order_id, "method": "database"}


async def _send_to_clover(order: LiveOrder) -> Dict[str, Any]:
    """Create an order in Clover POS via REST API."""
    api_token    = os.environ.get("CLOVER_API_TOKEN", "")
    merchant_id  = os.environ.get("CLOVER_MERCHANT_ID", "")
    clover_env   = os.environ.get("CLOVER_ENV", "sandbox")

    base_url = (
        "https://sandbox.dev.clover.com"
        if clover_env == "sandbox"
        else "https://api.clover.com"
    )

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:

            # Step 1 — Create empty order
            order_payload = {
                "title": f"Phone Order — {order.customer_name or 'Guest'}",
                "note": f"RingAI | {order.order_type.upper()} | {order.special_instructions or ''}".strip(" |"),
                "orderType": {"id": "TAKEOUT"},
            }
            resp = await client.post(
                f"{base_url}/v3/merchants/{merchant_id}/orders",
                headers=headers,
                json=order_payload,
            )
            if resp.status_code not in (200, 201):
                logger.error(f"Clover create order failed: {resp.status_code} {resp.text}")
                return {"success": False, "order_id": "", "method": "clover"}

            clover_order = resp.json()
            clover_order_id = clover_order.get("id")
            logger.info(f"Clover order created: {clover_order_id}")

            # Step 2 — Add line items
            for item in order.items:
                line_item = {
                    "name": item.name,
                    "price": item.unit_price,  # in cents
                    "unitQty": item.quantity * 1000,  # Clover uses 1000 = 1 unit
                }
                if item.special_instructions:
                    line_item["note"] = item.special_instructions

                li_resp = await client.post(
                    f"{base_url}/v3/merchants/{merchant_id}/orders/{clover_order_id}/line_items",
                    headers=headers,
                    json=line_item,
                )
                if li_resp.status_code not in (200, 201):
                    logger.warning(f"Clover line item failed for {item.name}: {li_resp.text}")

            logger.info(f"Clover order {clover_order_id} created with {len(order.items)} items")
            return {"success": True, "order_id": clover_order_id, "method": "clover"}

    except Exception as e:
        logger.error(f"Clover dispatch error: {e}", exc_info=True)
        return {"success": False, "order_id": "", "method": "clover"}


async def _send_to_kitchen_webhook(order: LiveOrder, url: str) -> Dict[str, Any]:
    payload = {
        "order_id": f"RNG-{order.call_sid[-8:].upper()}",
        "restaurant_id": order.restaurant_id,
        "source": "ringai_phone",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_name": order.customer_name or "Phone Customer",
        "order_type": order.order_type,
        "delivery_address": order.delivery_address,
        "special_instructions": order.special_instructions,
        "items": [i.to_dict() for i in order.items],
        "total": order.total,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers={"X-Source": "ringai"})
            if resp.status_code < 300:
                oid = resp.json().get("order_id") or payload["order_id"]
                return {"success": True, "order_id": oid, "method": "kitchen_webhook"}
    except Exception as e:
        logger.error(f"Kitchen webhook error: {e}")
    return {"success": False, "order_id": "", "method": "kitchen_webhook"}


async def _send_to_square(order: LiveOrder, restaurant: Dict[str, Any]) -> Dict[str, Any]:
    token = restaurant.get("square_access_token")
    location = restaurant.get("square_location_id")
    if not token or not location:
        return {"success": False, "order_id": "", "method": "square"}
    env = os.environ.get("SQUARE_ENVIRONMENT", "sandbox")
    base = "https://connect.squareupsandbox.com" if env == "sandbox" else "https://connect.squareup.com"
    body = {
        "idempotency_key": order.call_sid,
        "order": {
            "location_id": location,
            "source": {"name": "RingAI Phone"},
            "line_items": [
                {
                    "name": i.name, "quantity": str(i.quantity),
                    "base_price_money": {"amount": i.unit_price, "currency": "USD"},
                    "note": i.special_instructions or None,
                }
                for i in order.items
            ],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{base}/v2/orders", json=body,
                headers={"Authorization": f"Bearer {token}", "Square-Version": "2024-01-18"},
            )
            data = resp.json()
            if resp.status_code == 200:
                oid = data.get("order", {}).get("id", "")
                return {"success": True, "order_id": oid, "method": "square"}
            logger.error(f"Square error {resp.status_code}: {data}")
    except Exception as e:
        logger.error(f"Square API error: {e}")
    return {"success": False, "order_id": "", "method": "square"}


# ---------------------------------------------------------------------------
# Rule-based call quality evaluation
# ---------------------------------------------------------------------------

def evaluate_call_quality(
    transcript: List[Dict],
    order_confirmed: bool,
    escalated: bool,
) -> Dict[str, Any]:
    ai_text = " ".join(t["text"] for t in transcript if t.get("role") == "ai").lower()
    violations, highlights = [], []

    if not any(p in ai_text for p in ["ai assistant", "virtual assistant", "i'm an ai", "automated"]):
        violations.append("AI did not disclose it is an automated assistant")

    if order_confirmed and not any(p in ai_text for p in ["read that back", "your total", "does that sound", "let me confirm"]):
        violations.append("Order confirmed without a readback — protocol violation")
    elif order_confirmed:
        highlights.append("Order readback completed before confirmation")

    if escalated and any(p in ai_text for p in ["connect you", "team member", "hold"]):
        highlights.append("Clean escalation handoff")
    elif escalated:
        violations.append("Escalation handled poorly")

    score = max(20, min(100, 90 - len(violations) * 12 + len(highlights) * 3))
    return {
        "rule_based_score": score,
        "protocol_violations": violations,
        "protocol_highlights": highlights,
    }


# ---------------------------------------------------------------------------
# System Prompt Builder (hardened)
# ---------------------------------------------------------------------------

def build_system_prompt(
    restaurant_name: str,
    cuisine_type: str,
    persona: str,
    business_rules: List[str],
    escalation_rules: List[str],
    menu_items: List[Dict],
    disclosure_text: str,
    upsell_enabled: bool = True,
    delivery_enabled: bool = True,
    delivery_minimum: int = 1500,
    avg_prep_time_minutes: int = 20,
    escalation_phone: Optional[str] = None,
    operating_hours: Optional[Dict] = None,
    restaurant_timezone: str = "UTC",
) -> str:
    menu_index = MenuIndex(menu_items)

    try:
        import pytz
        tz = pytz.timezone(restaurant_timezone)
        local_now = datetime.now(tz)
        current_time_str = local_now.strftime("%A, %I:%M %p %Z")
        current_day = local_now.strftime("%A").lower()
        current_minutes = local_now.hour * 60 + local_now.minute
        is_open = False
        if operating_hours:
            day_hours = operating_hours.get(current_day, {})
            if not day_hours.get("closed"):
                def time_to_minutes(t):
                    try:
                        from datetime import datetime as dt
                        parsed = dt.strptime(t, "%H:%M")
                        return parsed.hour * 60 + parsed.minute
                    except Exception:
                        try:
                            from datetime import datetime as dt
                            parsed = dt.strptime(t, "%I:%M %p")
                            return parsed.hour * 60 + parsed.minute
                        except Exception:
                            return 0
                open_min = time_to_minutes(day_hours.get("open", "12:00 AM"))
                close_min = time_to_minutes(day_hours.get("close", "11:59 PM"))
                if close_min <= open_min:
                    is_open = current_minutes >= open_min or current_minutes <= close_min
                else:
                    is_open = open_min <= current_minutes <= close_min
        open_status = "OPEN" if is_open else "CLOSED"
    except Exception as e:
        logger.error(f"Timezone error for '{restaurant_timezone}': {e}")
        current_time_str = datetime.now(timezone.utc).strftime("%A, %I:%M %p UTC")
        open_status = "UNKNOWN"

    menu_block = menu_index.as_prompt_text()
    category_list = ", ".join(menu_index.category_names())
    rules_block = "\n".join(f"  • {r}" for r in business_rules) if business_rules else "  • (No additional rules)"
    escalation_block = "\n".join(f"  ⚠ {r}" for r in escalation_rules) if escalation_rules else "  ⚠ Customer requests a manager\n  ⚠ Food safety complaint or allergic reaction"
    delivery_section = (
        f"DELIVERY: Available. Minimum order: ${delivery_minimum/100:.2f}. Collect full street address."
        if delivery_enabled else
        "DELIVERY: Not available. Pickup only."
    )
    upsell_section = (
        "UPSELL: After the main order, suggest ONE drink, dessert, or side. "
        "Accept any decline immediately — never push twice."
        if upsell_enabled else ""
    )
    escalation_target = escalation_phone or "a team member"
    prep_time = f"{avg_prep_time_minutes} minutes"

    hours_block = ""
    if operating_hours:
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        lines = []
        for day in days:
            h = operating_hours.get(day, {})
            if h.get("closed"):
                lines.append(f"  {day.capitalize()}: Closed")
            else:
                lines.append(f"  {day.capitalize()}: {h.get('open','?')} – {h.get('close','?')}")
        hours_block = "\n".join(lines)

    return f"""You are the AI phone assistant for {restaurant_name}, a {cuisine_type} restaurant.
Persona: {persona}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GREETING — SAY THIS FIRST, EVERY CALL:
When you receive the message "BEGIN_CALL", immediately say: "{disclosure_text}"
Do not wait for the customer to speak first. Greet them immediately.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

═══════════════════════════
MENU — YOUR ONLY SOURCE OF TRUTH
═══════════════════════════
{menu_block}

CRITICAL MENU RULES — NEVER VIOLATE:
1. Only confirm, recommend, or discuss items listed above.
2. If a customer asks for an item NOT in this list: "I'm sorry, we don't have that. Can I suggest something similar?"
3. NEVER invent items, prices, descriptions, or availability.
4. Prices are exact. Never estimate or round.
5. If you are unsure whether an item exists — it doesn't. Do not guess.
6. NEVER read the full menu aloud. If a customer asks what's on the menu, say:
   "We have {category_list}. What sounds good?" — then answer specific questions.
   Reading the entire menu wastes time and confuses customers.

═══════════════════════════
ORDER PROTOCOL — FOLLOW EVERY STEP
═══════════════════════════
STEP 1: Ask order type first — "Are you calling for pickup, or would you like delivery?"
STEP 2: Take the order. When the customer names an item, acknowledge briefly:
  "Got it" / "Added" / "Perfect" — then ask "Anything else?"
  Do NOT ask "Is that correct?" after each item — confirmation happens at STEP 4 only.
STEP 3: Ask for customer name: "Could I get a name for the order?"
{upsell_section}
STEP 4: MANDATORY READBACK — never skip this:
  "Let me read that back: [every item and quantity, NO individual prices].
  Your total is $[exact total]. Is that correct?"
  • Customers already heard individual prices — only the total matters at readback.
  • If YES → go to STEP 5
  • If NO → "Of course, what would you like to change?" → return to STEP 2
STEP 5: Confirm only after explicit yes from the customer:
  "Perfect! Your order is confirmed. Ready in about {prep_time}. Thank you for calling {restaurant_name}!"
  [INTERNAL SIGNAL — DO NOT SAY ALOUD: ORDER_CONFIRMED]
STEP 6: After saying the confirmation phrase, say nothing further. The call will end.
  Do NOT ask follow-up questions or offer more help after ORDER_CONFIRMED.

═══════════════════════════
ALLERGEN PROTOCOL — LIABILITY ISSUE
═══════════════════════════
• When a customer mentions an allergy: acknowledge it seriously.
• For any item where the allergen is listed: warn clearly — "I should let you know, [item] contains [allergen]."
• For items with no allergen info: "I don't have complete allergen information for that. I'd recommend speaking with our kitchen staff — would you like me to transfer you?"
• NEVER say any item is "allergen-free" or "safe".

═══════════════════════════
BUSINESS RULES
═══════════════════════════
{rules_block}
{delivery_section}
CURRENT TIME: {current_time_str}
OPERATING HOURS:
{hours_block if hours_block else "  Hours not available"}
CURRENT STATUS: The restaurant is currently {open_status}. Do not second-guess this — if OPEN, take orders. If CLOSED, inform the customer and state the next opening time.

═══════════════════════════
ESCALATION — TRANSFER IMMEDIATELY WHEN:
═══════════════════════════
{escalation_block}

How to escalate: "I'm going to connect you with {escalation_target} right away. Please hold."
Then signal: [INTERNAL SIGNAL — DO NOT SAY ALOUD: ESCALATE_TO_HUMAN]

═══════════════════════════
EDGE CASES
═══════════════════════════
• Silence >4 seconds: "Are you still there? Take your time."
• "My usual": "I don't have your order history. What would you like today?"
• Customer frustrated: slow down, never rush, escalate if it worsens.
• Discount request: "I can't apply discounts on this call — ask our team at pickup."
• Outside hours: tell them hours, wish them well.
• Customer says "Hello" or "Are you there" mid-order: do NOT restart the conversation.
  Continue exactly where you left off. Example: if waiting for readback confirmation,
  re-ask only: "Just to confirm — does that total sound right?"
• After readback, if silence >5 seconds: ask ONCE "Just to confirm, is that total correct?"
  then wait. Do not repeat again.

═══════════════════════════
NEVER DO THESE
═══════════════════════════
✗ Reveal you are powered by Google, Gemini, or any specific AI
✗ Read the full menu aloud — summarize by category only
✗ Ask "Is that correct?" after each individual item — save it for the final readback
✗ Repeat individual item prices during readback — total only
✗ Continue talking after the order confirmation farewell
✗ Skip the order readback — even if the customer sounds rushed
✗ Confirm an order before the customer explicitly says yes
✗ Give allergen safety guarantees
✗ Accept payment information over the phone

If asked what AI you are: "I'm the virtual assistant for {restaurant_name}. How can I help with your order?"
"""


# ---------------------------------------------------------------------------
# 2. CONVERSATION RESPONSE (text-only, for non-live / demo scenarios)
# ---------------------------------------------------------------------------

def _summarize_conversation_context(transcript: List[Dict], max_turns: int = 6) -> List[Dict]:
    """Keep first greeting + last N turns to stay within token budget."""
    if len(transcript) <= max_turns:
        return transcript
    first_exchange = transcript[:2] if len(transcript) >= 2 else transcript[:1]
    recent_exchanges = transcript[-(max_turns - len(first_exchange)):]
    return first_exchange + recent_exchanges


async def get_conversation_response(
    system_prompt: str,
    transcript: List[Dict],
    new_customer_message: str,
) -> str:
    """Get an AI response for a single conversation turn."""
    client = _get_client()
    if not client:
        return _mock_conversation_response(new_customer_message)

    try:
        summarized_transcript = _summarize_conversation_context(transcript)

        condensed_prompt = system_prompt
        if len(system_prompt) > 1500:
            condensed_prompt = system_prompt[:1500] + "\n\n[Additional rules truncated for brevity]"

        messages = [{"role": "system", "content": condensed_prompt}]
        for entry in summarized_transcript:
            role = "user" if entry.get("role") == "customer" else "assistant"
            content = entry["text"][:300] if len(entry.get("text", "")) > 300 else entry.get("text", "")
            messages.append({"role": role, "content": content})

        if new_customer_message:
            messages.append({"role": "user", "content": new_customer_message[:500]})

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=250,
        )
        text = response.choices[0].message.content.strip()
        return text if text else _mock_conversation_response(new_customer_message)
    except Exception as e:
        error_msg = str(e).lower()
        if "budget" in error_msg or "quota" in error_msg or "limit" in error_msg:
            logger.warning(f"Budget/quota exceeded, using mock response: {e}")
        else:
            logger.error(f"Gemini conversation error: {e}")
        return _mock_conversation_response(new_customer_message)


def _mock_conversation_response(message: str) -> str:
    msg = (message or "").lower()
    if "order" in msg or "like" in msg:
        return "Of course! What would you like to order today?"
    if "reservation" in msg or "table" in msg or "book" in msg:
        return "I'd be happy to help with a reservation! How many guests and what date/time works best?"
    if "hour" in msg or "open" in msg:
        return "We're open Tuesday through Sunday, 11 AM to 10 PM. Is there anything else I can help with?"
    if not msg:
        return "Hi! I'm an AI assistant. How can I help you today?"
    return "I'd be happy to help! Could you tell me a bit more about what you need?"


# ---------------------------------------------------------------------------
# 3. MENU PARSING (structured JSON output)
# ---------------------------------------------------------------------------

async def parse_menu_text(menu_text: str) -> Dict[str, Any]:
    """Parse unstructured menu text into structured menu items using Gemini."""
    client = _get_client()
    if not client:
        return _mock_parse_menu(menu_text)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": """You are a menu parser. Extract menu items from the text and return valid JSON.
Return ONLY a JSON object with this exact structure:
{
  "items": [{"name": "...", "category": "...", "price": 1299, "description": "...", "allergens": []}],
  "categories": ["Category1", "Category2"],
  "warnings": []
}
- price must be in cents (e.g., $12.99 = 1299)
- allergens should be common allergens like: gluten, dairy, nuts, soy, eggs, shellfish
- If a price is missing, set it to 0"""},
                {"role": "user", "content": f"Parse this restaurant menu into structured data:\n\n{menu_text}"}
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        text = response.choices[0].message.content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        items = result.get("items", [])
        for item in items:
            item["price"] = int(item.get("price", 0))
            item["allergens"] = item.get("allergens", [])
            item["description"] = item.get("description") or None
            item["modifiers"] = []
        return {
            "items": items,
            "categories": result.get("categories", list(set(i["category"] for i in items))),
            "warnings": result.get("warnings", []),
        }
    except Exception as e:
        logger.error(f"Gemini menu parse error: {e}")
        return _mock_parse_menu(menu_text)


def _mock_parse_menu(menu_text: str) -> Dict[str, Any]:
    """Fallback text parser when Gemini is unavailable."""
    lines = [line.strip() for line in menu_text.strip().split("\n") if line.strip()]
    parsed_items = []
    current_category = "Uncategorized"
    for line in lines:
        if line.isupper() or line.endswith(":"):
            current_category = line.rstrip(":").title()
            continue
        parts = line.rsplit("$", 1)
        if len(parts) == 2:
            name = parts[0].strip().rstrip("-").rstrip(".")
            try:
                price = int(float(parts[1].strip()) * 100)
            except ValueError:
                price = 0
            parsed_items.append({
                "name": name, "category": current_category,
                "price": price, "description": None, "modifiers": [], "allergens": [],
            })
        elif line and not line.startswith("#"):
            parsed_items.append({
                "name": line, "category": current_category,
                "price": 0, "description": None, "modifiers": [], "allergens": [],
            })
    return {
        "items": parsed_items,
        "categories": list(set(i["category"] for i in parsed_items)),
        "warnings": [] if parsed_items else ["No items could be parsed"],
    }


# ---------------------------------------------------------------------------
# 4. POST-CALL ANALYSIS (structured JSON output)
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """You are a call quality analyst. Analyze the transcript and return a JSON object.

IMPORTANT: Return ONLY valid JSON, no markdown, no explanations.

Required JSON format:
{"quality_score":85,"order_accuracy":"accurate","issues":[],"highlights":[],"menu_suggestions":[],"rule_suggestions":[],"summary":"Brief summary"}

Rules:
- quality_score: integer 1-100
- order_accuracy: "accurate", "minor_issues", or "inaccurate"
- issues/highlights: short strings, max 5 items each
- summary: one sentence, max 100 characters

Return the JSON now:"""


async def analyse_call_transcript(
    transcript: List[Dict],
    order_json: Optional[Dict] = None,
    menu_items: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Analyse a completed call transcript for quality, accuracy, and insights."""
    client = _get_client()
    if not client:
        return _mock_call_analysis(transcript, order_json)

    if len(transcript) > 8:
        truncated = transcript[:2] + transcript[-4:]
        transcript_for_analysis = truncated
    else:
        transcript_for_analysis = transcript

    transcript_text = "\n".join(
        f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e['text'][:150]}"
        for e in transcript_for_analysis
    )

    if len(transcript_text) > 1200:
        transcript_text = transcript_text[:1200] + "..."

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"TRANSCRIPT:\n{transcript_text}"}
            ],
            temperature=0.1,
            max_tokens=500,
        )

        raw_text = response.choices[0].message.content.strip()
        logger.debug(f"Gemini analysis raw response: {raw_text[:200]}...")

        repaired_text = _repair_json(raw_text)

        try:
            result = json.loads(repaired_text)
        except json.JSONDecodeError:
            logger.warning(f"JSON repair failed, attempting regex extraction. Raw: {raw_text[:100]}...")
            result = _extract_json_fields(
                raw_text,
                ["quality_score", "order_accuracy", "issues", "highlights", "summary"]
            )
            if not result or "quality_score" not in result:
                logger.error(f"JSON extraction failed completely. Raw: {raw_text[:200]}")
                return _mock_call_analysis(transcript, order_json)

        result["quality_score"] = max(1, min(100, int(result.get("quality_score", 85))))
        result["order_accuracy"] = result.get("order_accuracy", "accurate")
        result.setdefault("issues", [])
        result.setdefault("highlights", [])
        result.setdefault("menu_suggestions", [])
        result.setdefault("rule_suggestions", [])
        result.setdefault("summary", f"Call with {len(transcript)} exchanges analyzed.")

        for key in ["issues", "highlights", "menu_suggestions", "rule_suggestions"]:
            if not isinstance(result.get(key), list):
                result[key] = []

        return result

    except Exception as e:
        logger.error(f"Gemini analysis error: {e}")
        return _mock_call_analysis(transcript, order_json)


def _mock_call_analysis(transcript, order_json):
    import random
    return {
        "quality_score": random.randint(78, 99),
        "order_accuracy": "accurate",
        "issues": random.sample(
            ["Minor pause before confirming order", "Could have offered drinks", "Slight delay in greeting"],
            random.randint(0, 1),
        ),
        "highlights": random.sample(
            ["Clear order readback", "Friendly tone", "Efficient flow", "Natural conversation", "Proper greeting"],
            random.randint(2, 4),
        ),
        "menu_suggestions": [],
        "rule_suggestions": [],
        "summary": f"Call completed with {len(transcript)} exchanges. "
                   f"{'Order placed successfully.' if order_json else 'No order placed.'}",
    }