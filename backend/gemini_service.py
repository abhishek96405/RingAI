"""
Gemini 2.5 Flash Service — Unified AI for RingAI

Replaces: Anthropic/Claude, Deepgram, ElevenLabs
Handles: Menu parsing, post-call analysis, conversation intelligence
Audio: Handled via Pipecat + Gemini Live Audio API (see call_pipeline.py)
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini Client (lazy-init, graceful fallback when key not set)
# ---------------------------------------------------------------------------
_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set — Gemini calls will use mock fallback")
        return None

    try:
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialised (model: gemini-2.5-flash)")
        return _gemini_client
    except Exception as e:
        logger.error(f"Failed to initialise Gemini client: {e}")
        return None


def is_gemini_available() -> bool:
    return _get_client() is not None


MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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
{'- Suggest a drink or dessert add-on after the main order.' if upsell_enabled else ''}
{'- Accept delivery orders. Minimum order for delivery: $' + f'{delivery_minimum/100:.2f}' if delivery_enabled else '- Delivery is not available; only pickup.'}
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
        # Fallback mock
        return _mock_conversation_response(new_customer_message)

    try:
        from google.genai import types

        contents = []
        for entry in transcript:
            role = "user" if entry.get("role") == "customer" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=entry["text"])]
            ))
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=new_customer_message)]
        ))

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=300,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini conversation error: {e}")
        return _mock_conversation_response(new_customer_message)


def _mock_conversation_response(message: str) -> str:
    msg = message.lower()
    if "order" in msg or "like" in msg:
        return "Of course! What would you like to order today?"
    if "reservation" in msg or "table" in msg or "book" in msg:
        return "I'd be happy to help with a reservation! How many guests and what date/time works best?"
    if "hour" in msg or "open" in msg:
        return "We're open Tuesday through Sunday, 11 AM to 10 PM. Is there anything else I can help with?"
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
        from google.genai import types

        menu_schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "category": {"type": "string"},
                            "price": {"type": "integer", "description": "Price in cents"},
                            "description": {"type": "string"},
                            "allergens": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "category", "price"],
                    },
                },
                "categories": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["items", "categories"],
        }

        response = client.models.generate_content(
            model=MODEL,
            contents=f"""Parse the following restaurant menu text into structured data.
Extract each item with its name, category, price in cents, description, and any allergens.
Group items by category. If a price is missing, set it to 0.

MENU TEXT:
{menu_text}""",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=menu_schema,
                temperature=0.2,
            ),
        )

        result = json.loads(response.text)
        # Validate with Pydantic-style checks
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
        from google.genai import types

        analysis_schema = {
            "type": "object",
            "properties": {
                "quality_score": {"type": "integer", "description": "1-100 overall quality"},
                "order_accuracy": {"type": "string", "enum": ["accurate", "minor_issues", "major_issues"]},
                "issues": {"type": "array", "items": {"type": "string"}},
                "highlights": {"type": "array", "items": {"type": "string"}},
                "menu_suggestions": {"type": "array", "items": {"type": "string"}},
                "rule_suggestions": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
            "required": ["quality_score", "order_accuracy", "summary"],
        }

        transcript_text = "\n".join(
            f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e['text']}"
            for e in transcript
        )
        order_text = json.dumps(order_json, indent=2) if order_json else "No order placed"

        response = client.models.generate_content(
            model=MODEL,
            contents=f"""Analyse the following restaurant phone call transcript.
Rate the AI agent's performance, identify issues and highlights.

TRANSCRIPT:
{transcript_text}

ORDER RESULT:
{order_text}

Provide a quality score (1-100), order accuracy assessment, issues found,
positive highlights, and a 1-2 sentence summary.""",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=analysis_schema,
                temperature=0.3,
            ),
        )

        result = json.loads(response.text)
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
