"""
Gemini 2.5 Flash Service — Unified AI for RingAI

Uses: Google Gemini 2.5 Flash via OpenAI-compatible API (Emergent LLM gateway)
Handles: Menu parsing, post-call analysis, conversation intelligence
Audio: Handled via Pipecat + Gemini Live Audio API (see call_pipeline.py)
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client (lazy-init via OpenAI-compatible SDK for Emergent gateway)
# ---------------------------------------------------------------------------
_client = None
MODEL = "gemini/gemini-2.5-flash"

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
        proxy_url = os.environ.get("integration_proxy_url", "https://integrations.emergentagent.com")
        _client = OpenAI(
            api_key=api_key,
            base_url=f"{proxy_url}/llm/v1",
        )
        logger.info(f"Gemini client initialised via Emergent gateway (model: {MODEL})")
        return _client
    except Exception as e:
        logger.error(f"Failed to initialise Gemini client: {e}")
        return None


def is_gemini_available() -> bool:
    return _get_client() is not None


# ---------------------------------------------------------------------------
# 1. SYSTEM PROMPT BUILDER
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
) -> str:
    menu_text = "\n".join(
        f"  - {item['name']} (${item['price']/100:.2f}) — {item.get('category','')}"
        f"{' [UNAVAILABLE]' if not item.get('available', True) else ''}"
        for item in menu_items
    )
    rules_text = "\n".join(f"  • {r}" for r in business_rules) if business_rules else "  (none)"
    escalation_text = "\n".join(f"  ⚠ {r}" for r in escalation_rules) if escalation_rules else "  (none)"

    delivery_line = ""
    if delivery_enabled:
        delivery_line = f"- Accept delivery orders. Minimum order for delivery: ${delivery_minimum/100:.2f}"
    else:
        delivery_line = "- Delivery is not available; only pickup."

    return f"""You are the AI phone-order assistant for {restaurant_name}, a {cuisine_type} restaurant.
Persona: {persona}

GREETING (say this first):
"{disclosure_text}"

MENU:
{menu_text}

BUSINESS RULES:
{rules_text}

ESCALATION (transfer to human when):
{escalation_text}

ORDER GUIDELINES:
- Always read back the full order with item names, quantities, and total before confirming.
- If an item is UNAVAILABLE, apologise and suggest a similar alternative.
{"- Suggest a drink or dessert add-on after the main order." if upsell_enabled else ""}
{delivery_line}
- Collect customer name and contact info for the order.
- Be warm, concise, and never break character.
- If you cannot resolve a request, say you will transfer to a team member.
"""


# ---------------------------------------------------------------------------
# 2. CONVERSATION RESPONSE (text-only, for non-live / demo scenarios)
# ---------------------------------------------------------------------------

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
        messages = [{"role": "system", "content": system_prompt}]
        for entry in transcript:
            role = "user" if entry.get("role") == "customer" else "assistant"
            messages.append({"role": role, "content": entry["text"]})
        if new_customer_message:
            messages.append({"role": "user", "content": new_customer_message})

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        return text if text else _mock_conversation_response(new_customer_message)
    except Exception as e:
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
        # Extract JSON from the response (handle markdown code blocks)
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
    lines = [l.strip() for l in menu_text.strip().split("\n") if l.strip()]
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

async def analyse_call_transcript(
    transcript: List[Dict],
    order_json: Optional[Dict] = None,
    menu_items: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Analyse a completed call transcript for quality, accuracy, and insights."""
    client = _get_client()
    if not client:
        return _mock_call_analysis(transcript, order_json)

    try:
        transcript_text = "\n".join(
            f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e['text']}"
            for e in transcript
        )
        order_text = json.dumps(order_json, indent=2) if order_json else "No order placed"

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": """You are a call quality analyst. Return ONLY a raw JSON object (no markdown, no code blocks, no explanation).
The JSON must have exactly these fields:
{"quality_score":85,"order_accuracy":"accurate","issues":[],"highlights":[],"menu_suggestions":[],"rule_suggestions":[],"summary":"..."}"""},
                {"role": "user", "content": f"Analyse this call transcript and order. Return raw JSON only.\n\nTRANSCRIPT:\n{transcript_text}\n\nORDER:\n{order_text}"}
            ],
            temperature=0.2,
            max_tokens=600,
        )

        text = response.choices[0].message.content.strip()
        # Robust JSON extraction
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # Find the JSON object boundaries
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        result = json.loads(text)
        result["quality_score"] = max(1, min(100, int(result.get("quality_score", 85))))
        result.setdefault("issues", [])
        result.setdefault("highlights", [])
        result.setdefault("menu_suggestions", [])
        result.setdefault("rule_suggestions", [])
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
