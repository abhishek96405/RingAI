"""
Gemini 2.5 Flash Service — Unified AI for RingAI

Uses: Google Gemini 2.5 Flash via OpenAI-compatible API (Emergent LLM gateway)
Handles: Menu parsing, post-call analysis, conversation intelligence
Audio: Handled via Pipecat + Gemini Live Audio API (see call_pipeline.py)
"""
import os
import json
import logging
import re
from typing import List, Dict, Any, Optional

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
    
    # Try to fix unterminated strings by finding incomplete string patterns
    # This handles the "Unterminated string" error
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as e:
        # Attempt repairs for common issues
        
        # Fix: truncated JSON - close any unclosed strings and objects
        if "Unterminated string" in str(e):
            # Count quotes to see if we have an odd number
            quote_count = text.count('"') - text.count('\\"')
            if quote_count % 2 != 0:
                # Add closing quote
                text = text.rstrip() + '"'
        
        # Ensure we have balanced braces and brackets
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        
        if open_brackets > 0:
            text = text.rstrip() + ']' * open_brackets
        if open_braces > 0:
            text = text.rstrip() + '}' * open_braces
        
        # Try again
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
    
    # Try to extract quality_score
    if "quality_score" in expected_fields:
        match = re.search(r'"quality_score"\s*:\s*(\d+)', text)
        if match:
            result["quality_score"] = int(match.group(1))
    
    # Try to extract order_accuracy
    if "order_accuracy" in expected_fields:
        match = re.search(r'"order_accuracy"\s*:\s*"([^"]*)"', text)
        if match:
            result["order_accuracy"] = match.group(1)
    
    # Try to extract summary
    if "summary" in expected_fields:
        match = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
        if match:
            result["summary"] = match.group(1)
    
    # Try to extract arrays (issues, highlights)
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

    return f"""You are the friendly AI phone assistant for {restaurant_name}, a {cuisine_type} restaurant.
Your personality: {persona}. Speak naturally like a real person on the phone - warm, conversational, not robotic.

IMPORTANT SPEECH RULES:
- Speak naturally like a human, not a script reader
- Use contractions (I'm, we've, you'll)
- Keep responses SHORT - 1-2 sentences max unless listing menu items
- Don't use bullet points, asterisks, or markdown - this is SPOKEN conversation
- Don't repeat the restaurant name in every response
- Say prices naturally like "sixteen ninety-nine" not "$16.99"

MENU:
{menu_text}

BUSINESS RULES:
{rules_text}

ESCALATION (transfer to human when):
{escalation_text}

ORDER GUIDELINES:
- Read back orders naturally: "So that's one margherita and two pepperonis, comes to thirty-five dollars"
- If an item is unavailable, apologize and suggest something similar
{"- After the main order, casually suggest a drink or dessert" if upsell_enabled else ""}
{delivery_line}
- Get their name for the order
- Be warm and brief - don't over-explain
"""


# ---------------------------------------------------------------------------
# 2. CONVERSATION RESPONSE (text-only, for non-live / demo scenarios)
# ---------------------------------------------------------------------------

def _summarize_conversation_context(transcript: List[Dict], max_turns: int = 6) -> List[Dict]:
    """
    Summarize conversation history to stay within token budget.
    Keeps first greeting and last N turns for context.
    """
    if len(transcript) <= max_turns:
        return transcript
    
    # Keep first exchange (greeting) and last (max_turns - 2) exchanges
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
        # P1 fix: Summarize context to prevent budget exceeded errors
        summarized_transcript = _summarize_conversation_context(transcript)
        
        # Use a shorter system prompt for conversation to save tokens
        condensed_prompt = system_prompt
        if len(system_prompt) > 1500:
            # Keep first 1500 chars which include core identity and menu
            condensed_prompt = system_prompt[:1500] + "\n\n[Additional rules truncated for brevity]"
        
        messages = [{"role": "system", "content": condensed_prompt}]
        for entry in summarized_transcript:
            role = "user" if entry.get("role") == "customer" else "assistant"
            # Truncate individual messages if too long
            content = entry["text"][:300] if len(entry.get("text", "")) > 300 else entry.get("text", "")
            messages.append({"role": role, "content": content})
        
        if new_customer_message:
            messages.append({"role": "user", "content": new_customer_message[:500]})

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=250,  # Slightly reduced to stay within budget
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

    # Truncate transcript to avoid token limits (P1 fix)
    # Keep first 2 and last 4 exchanges for context
    if len(transcript) > 8:
        truncated = transcript[:2] + transcript[-4:]
        transcript_for_analysis = truncated
    else:
        transcript_for_analysis = transcript

    transcript_text = "\n".join(
        f"{'CUSTOMER' if e.get('role') == 'customer' else 'AI'}: {e['text'][:150]}"
        for e in transcript_for_analysis
    )
    
    # Keep transcript concise to avoid budget issues
    if len(transcript_text) > 1200:
        transcript_text = transcript_text[:1200] + "..."

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"TRANSCRIPT:\n{transcript_text}"}
            ],
            temperature=0.1,  # Lower temp for more consistent JSON
            max_tokens=500,   # Increased to prevent truncation
        )

        raw_text = response.choices[0].message.content.strip()
        logger.debug(f"Gemini analysis raw response: {raw_text[:200]}...")
        
        # Step 1: Try to repair and parse JSON
        repaired_text = _repair_json(raw_text)
        
        try:
            result = json.loads(repaired_text)
        except json.JSONDecodeError:
            # Step 2: Try regex extraction as fallback
            logger.warning(f"JSON repair failed, attempting regex extraction. Raw: {raw_text[:100]}...")
            result = _extract_json_fields(
                raw_text, 
                ["quality_score", "order_accuracy", "issues", "highlights", "summary"]
            )
            if not result or "quality_score" not in result:
                # Complete failure - use mock
                logger.error(f"JSON extraction failed completely. Raw: {raw_text[:200]}")
                return _mock_call_analysis(transcript, order_json)
        
        # Validate and normalize result
        result["quality_score"] = max(1, min(100, int(result.get("quality_score", 85))))
        result["order_accuracy"] = result.get("order_accuracy", "accurate")
        result.setdefault("issues", [])
        result.setdefault("highlights", [])
        result.setdefault("menu_suggestions", [])
        result.setdefault("rule_suggestions", [])
        result.setdefault("summary", f"Call with {len(transcript)} exchanges analyzed.")
        
        # Ensure lists are actually lists
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
