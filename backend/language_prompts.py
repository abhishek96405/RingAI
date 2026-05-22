"""
language_prompts.py — Per-language directives and signal trigger phrases.

This module is the single source of truth for:
  1. The short directive prepended to the system prompt so the AI converses
     in the chosen language (English directive is empty by design — English
     calls produce a byte-identical prompt to the pre-multilingual baseline).
  2. The phrase triggers used by signals_for() to detect events like
     ORDER_CONFIRMED in any language, without an LLM classifier.

Adding a language: write the directive, fill in the triggers, register it
in LANGUAGE_PROMPTS. No other code changes are required.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class LanguagePromptBundle:
    directive: str
    triggers: Dict[str, List[str]] = field(default_factory=dict)


_EN = LanguagePromptBundle(
    directive="",  # No directive — preserves byte-identical English prompt.
    triggers={
        "order_confirmed": [
            "your order is confirmed",
            "order is confirmed",
            "order has been placed",
            "got your order in",
        ],
        "appointment_confirmed": [
            "your appointment is confirmed",
            "appointment is confirmed",
        ],
        "reservation_confirmed": [
            "your reservation is confirmed",
            "table is reserved",
            "table is booked",
        ],
        "sending_menu_sms": [
            "i'll text you the menu",
            "texting you the menu",
        ],
        "call_ending": [
            "have a great day",
            "thanks for calling",
            "thank you for calling",
        ],
    },
)

_TE = LanguagePromptBundle(
    directive=(
        "\n\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "FINAL LANGUAGE OVERRIDE — HIGHEST PRIORITY (OVERRIDES ALL ABOVE)\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "\n"
        "This entire call is in TELUGU (తెలుగు). Every example phrase shown\n"
        "earlier in this prompt that is in English MUST be replaced with its\n"
        "natural Telugu equivalent. Speak as a native Telugu speaker — NOT as\n"
        "an English speaker patching Telugu words in.\n"
        "\n"
        "DO NOT MIX ENGLISH GREETINGS OR FILLER PHRASES. Specifically forbidden:\n"
        "  • 'Welcome back', 'Got it!', 'Perfect!', 'Sure!', 'Thanks for calling',\n"
        "    'Of course!', 'Alright!', 'Awesome!' — translate ALL of these.\n"
        "  • Do not start a sentence in English and switch to Telugu mid-sentence.\n"
        "  • Do not transliterate Telugu in Latin script ('Sare, oka Biryani') —\n"
        "    speak in proper Telugu script or English script, not romanized Telugu.\n"
        "\n"
        "NUMBERS — USE TELUGU NUMERALS, NOT ENGLISH TRANSLITERATIONS:\n"
        "  • 1 → 'ఒక' / 'ఒకటి' (NEVER 'వన్')\n"
        "  • 2 → 'రెండు' (NEVER 'టూ')\n"
        "  • 3 → 'మూడు' (NEVER 'త్రీ')\n"
        "  • 4 → 'నాలుగు', 5 → 'ఐదు' ... etc.\n"
        "  • Example: 'ఒక Chicken Biryani, రెండు Mango Lassi' — NOT 'వన్ Chicken Biryani'.\n"
        "\n"
        "PHRASE REPLACEMENTS (use the Telugu form on the right):\n"
        "  Greeting new customer        → 'నమస్తే! ఈరోజు ఏం ఆర్డర్ చేస్తారు?'\n"
        "  Greeting returning customer  → 'తిరిగి స్వాగతం, [Name]! ఏం తీసుకుంటారు?'\n"
        "  Acknowledging an item        → 'సరే, ఒక [Item].' or 'అలాగే!'\n"
        "  Anything else?               → 'ఇంకా ఏమైనా కావాలా?'\n"
        "  Read-back intro              → 'మీ ఆర్డర్ చదువుతాను —'\n"
        "  Does that sound right?       → 'అంతా సరిగా ఉందా?'\n"
        "  Order is confirmed           → 'మీ ఆర్డర్ కన్ఫర్మ్ అయింది.' (PAST tense)\n"
        "  Sending SMS                  → 'మీకు పికప్ టైం టెక్స్ట్ ద్వారా పంపిస్తాను.'\n"
        "  Thanks for calling           → '[Restaurant] కి కాల్ చేసినందుకు ధన్యవాదాలు!'\n"
        "  Unclear input                → 'మళ్ళీ చెప్పగలరా?' (NOT 'Can you repeat?')\n"
        "\n"
        "MENU & NAME RULES:\n"
        "  • Menu item names stay in Latin form: 'Chicken Biryani', 'Mango Lassi'.\n"
        "    Do NOT transliterate them into Telugu script.\n"
        "  • Customer names stay in their original Latin form: 'Abhishek'.\n"
        "  • Restaurant names stay in their original form with all letters intact:\n"
        "    say 'Bawarchii' (with both i's), 'Desi Chowrastha', etc. Do NOT shorten\n"
        "    or simplify restaurant names when speaking Telugu.\n"
        "  • Do NOT invent menu items. Stick strictly to the menu shown above.\n"
        "    If asked for something not on the menu, decline politely in Telugu.\n"
        "  • Apply ALL order protocol steps, menu rules, escalation rules, and\n"
        "    edge cases from the sections above — just say them in Telugu using\n"
        "    the replacements above as the style guide.\n"
        "\n"
        "When you need to transfer the call to a human, still say the literal\n"
        "token ESCALATE_TO_HUMAN in English at the end of your Telugu sentence.\n"
        "It is a backend signal, not for the customer.\n"
        "\n"
        "If the customer EXPLICITLY asks mid-call to switch languages, comply.\n"
        "Otherwise do NOT switch. Even if the customer's Telugu transcription\n"
        "comes through garbled, stay in Telugu and ask 'మళ్ళీ చెప్పగలరా?'\n"
        "\n"
        "REMEMBER: This entire conversation is in Telugu. The very first word\n"
        "of your greeting must be in Telugu. Speak naturally and warmly.\n"
    ),
    triggers={
        "order_confirmed": [
            # Code-mixed forms (what the AI actually says with commit 2's code-mixing prompt)
            "order confirm చేశాను",
            "order confirm అయింది",
            "order confirm అయిపోయింది",
            "order confirm అయ్యింది",
            "order place అయింది",
            "order place అయిపోయింది",
            "మీ order confirm",
            # Pure Telugu forms (preserved for safety)
            "ఆర్డర్ కన్ఫర్మ్ అయింది",
            "ఆర్డర్ కన్ఫర్మ్ అయిపోయింది",
            "ఆర్డర్ కన్ఫర్మ్ అయ్యింది",
            "ఆర్డర్ ఖరారు అయింది",
            "ఆర్డర్ ఖరారు అయిపోయింది",
            "ఆర్డర్ ప్లేస్ అయింది",
            "ఆర్డర్ ప్లేస్ అయిపోయింది",
            "ఆర్డర్ పూర్తి అయింది",
            # English fallback (covers any English emitted by the AI)
            "your order is confirmed",
            "your order is placed",
            "order is confirmed",
        ],
        "appointment_confirmed": [
            "అపాయింట్‌మెంట్ కన్ఫర్మ్ అయింది",
            "అపాయింట్మెంట్ ఖరారు అయింది",
            "అపాయింట్‌మెంట్ బుక్ అయింది",
        ],
        "reservation_confirmed": [
            "టేబుల్ రిజర్వ్ అయింది",
            "టేబుల్ బుక్ అయింది",
            "రిజర్వేషన్ కన్ఫర్మ్ అయింది",
        ],
        "sending_menu_sms": [
            "మెనూ టెక్స్ట్ చేస్తాను",
            "మెనూ టెక్స్ట్ పంపిస్తాను",
            "మెనూ పంపిస్తాను",
        ],
        "call_ending": [
            "thank you for calling",
            "thanks for calling",
            "ధన్యవాదాలు",
            "మంచి రోజు",
        ],
    },
)

_HI = LanguagePromptBundle(
    directive=(
        "\n\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "FINAL LANGUAGE OVERRIDE — HIGHEST PRIORITY (OVERRIDES ALL ABOVE)\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "\n"
        "This entire call is in HINDI (हिंदी). Every example phrase shown\n"
        "earlier in this prompt that is in English MUST be replaced with its\n"
        "natural Hindi equivalent. Speak as a native Hindi speaker.\n"
        "\n"
        "DO NOT MIX ENGLISH GREETINGS OR FILLER. Specifically forbidden:\n"
        "  • 'Welcome back', 'Got it!', 'Perfect!', 'Sure!', 'Thanks for calling',\n"
        "    'Of course!', 'Alright!', 'Awesome!' — translate ALL of these.\n"
        "  • Do not start a sentence in English and switch to Hindi mid-sentence.\n"
        "  • Do not write Hindi in romanized script ('Theek hai, ek Biryani') —\n"
        "    use Devanagari script properly.\n"
        "\n"
        "NUMBERS — USE HINDI NUMERALS, NOT ENGLISH TRANSLITERATIONS:\n"
        "  • 1 → 'एक' (NEVER 'वन्')\n"
        "  • 2 → 'दो' (NEVER 'टू')\n"
        "  • 3 → 'तीन' (NEVER 'थ्री')\n"
        "  • Example: 'एक Chicken Biryani, दो Mango Lassi' — NOT 'वन् Chicken Biryani'.\n"
        "\n"
        "PHRASE REPLACEMENTS (use the Hindi form on the right):\n"
        "  Greeting new customer        → 'नमस्ते! आज क्या ऑर्डर लेंगे?'\n"
        "  Greeting returning customer  → 'फिर से स्वागत है, [Name]! क्या लेंगे आज?'\n"
        "  Acknowledging an item        → 'ठीक है, एक [Item].' or 'अच्छा!'\n"
        "  Anything else?               → 'और कुछ चाहिए?'\n"
        "  Read-back intro              → 'मैं आपका ऑर्डर दोहराता हूँ —'\n"
        "  Does that sound right?       → 'क्या यह सही है?'\n"
        "  Order is confirmed           → 'आपका ऑर्डर कन्फर्म हो गया है।' (PAST tense)\n"
        "  Sending SMS                  → 'पिकअप टाइम मैं आपको टेक्स्ट कर दूँगा।'\n"
        "  Thanks for calling           → 'Bawarchii को कॉल करने के लिए धन्यवाद!'\n"
        "  Unclear input                → 'क्या आप दोबारा कह सकते हैं?'\n"
        "\n"
        "MENU & NAME RULES:\n"
        "  • Menu item names stay in Latin form: 'Chicken Biryani', 'Mango Lassi'.\n"
        "    Do NOT transliterate them into Devanagari script.\n"
        "  • Customer names stay in their original Latin form: 'Abhishek'.\n"
        "  • Restaurant names stay intact: 'Bawarchii' (with both i's), 'Desi\n"
        "    Chowrastha', etc. Do NOT shorten or simplify them.\n"
        "  • Do NOT invent menu items. Stick strictly to the menu shown above.\n"
        "  • Apply ALL order protocol steps, menu rules, escalation rules, and\n"
        "    edge cases from the sections above — just say them in Hindi.\n"
        "\n"
        "When you need to transfer the call, still say the literal token\n"
        "ESCALATE_TO_HUMAN in English at the end of your Hindi sentence.\n"
        "\n"
        "If the customer EXPLICITLY asks mid-call to switch languages, comply.\n"
        "Otherwise do NOT switch. If Hindi transcription comes through garbled,\n"
        "stay in Hindi and ask 'क्या आप दोबारा कह सकते हैं?'\n"
        "\n"
        "REMEMBER: This entire conversation is in Hindi. The very first word\n"
        "of your greeting must be in Hindi. Speak naturally and warmly.\n"
    ),
    triggers={
        "order_confirmed": [
            # Code-mixed forms
            "order confirm हो गया",
            "order confirm कर दिया",
            "order place हो गया",
            "आपका order confirm",
            # Pure Hindi forms
            "ऑर्डर कन्फर्म हो गया",
            "ऑर्डर कन्फर्म हो गई",
            "ऑर्डर पक्का हो गया",
            "ऑर्डर प्लेस हो गया",
            # English fallback
            "your order is confirmed",
            "your order is placed",
            "order is confirmed",
        ],
        "appointment_confirmed": [
            "अपॉइंटमेंट कन्फर्म हो गया",
            "अपॉइंटमेंट पक्का हो गया",
        ],
        "reservation_confirmed": [
            "टेबल रिज़र्व हो गई",
            "टेबल बुक हो गई",
            "रिज़र्वेशन कन्फर्म हो गया",
        ],
        "sending_menu_sms": [
            "मेन्यू टेक्स्ट कर दूँगा",
            "मेन्यू भेज दूँगा",
        ],
        "call_ending": [
            "thank you for calling",
            "thanks for calling",
            "धन्यवाद",
            "अच्छा दिन",
        ],
    },
)

_ES = LanguagePromptBundle(
    directive=(
        "\n\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "FINAL LANGUAGE OVERRIDE — HIGHEST PRIORITY (OVERRIDES ALL ABOVE)\n"
        "═══════════════════════════════════════════════════════════════════\n"
        "\n"
        "This entire call is in SPANISH (Español). Every example phrase shown\n"
        "earlier in this prompt that is in English MUST be replaced with its\n"
        "natural Spanish equivalent. Speak as a native Spanish speaker.\n"
        "\n"
        "DO NOT MIX ENGLISH GREETINGS OR FILLER. Specifically forbidden:\n"
        "  • 'Welcome back', 'Got it!', 'Perfect!', 'Sure!', 'Thanks for calling',\n"
        "    'Of course!', 'Alright!', 'Awesome!' — translate ALL of these.\n"
        "  • Do not start a sentence in English and switch to Spanish mid-sentence.\n"
        "\n"
        "PHRASE REPLACEMENTS (use the Spanish form on the right):\n"
        "  Greeting new customer        → '¡Hola! ¿Qué le puedo ofrecer hoy?'\n"
        "  Greeting returning customer  → '¡Bienvenido de nuevo, [Name]! ¿Qué desea?'\n"
        "  Acknowledging an item        → '¡Listo, un [Item]!' or '¡Claro!'\n"
        "  Anything else?               → '¿Algo más?'\n"
        "  Read-back intro              → 'Déjeme repetir su pedido —'\n"
        "  Does that sound right?       → '¿Está todo bien?'\n"
        "  Order is confirmed           → 'Su pedido está confirmado.' (use 'está')\n"
        "  Sending SMS                  → 'Le enviaré la hora de recogida por mensaje.'\n"
        "  Thanks for calling           → '¡Gracias por llamar a Bawarchii!'\n"
        "  Unclear input                → '¿Puede repetir, por favor?'\n"
        "\n"
        "MENU & NAME RULES:\n"
        "  • Menu item names stay in their English/Latin form: 'Chicken Biryani'.\n"
        "  • Customer names stay in their original form.\n"
        "  • Do NOT invent menu items. Stick to the menu shown above.\n"
        "  • Apply ALL order protocol steps, menu rules, and edge cases from\n"
        "    above — just say them in Spanish.\n"
        "\n"
        "When you need to transfer, still say the literal token ESCALATE_TO_HUMAN\n"
        "in English at the end of your Spanish sentence.\n"
        "\n"
        "If the customer EXPLICITLY asks mid-call to switch languages, comply.\n"
        "Otherwise do NOT switch. Adapt formality (tú vs usted) to the customer.\n"
        "\n"
        "REMEMBER: This entire conversation is in Spanish. The very first word\n"
        "of your greeting must be in Spanish. Speak naturally and warmly.\n"
    ),
    triggers={
        "order_confirmed": [
            "pedido está confirmado",
            "pedido ha sido confirmado",
            "pedido confirmado",
            "orden está confirmada",
            "orden confirmada",
            "your order is confirmed",
        ],
        "appointment_confirmed": [
            "cita está confirmada",
            "cita ha sido confirmada",
        ],
        "reservation_confirmed": [
            "mesa está reservada",
            "reserva está confirmada",
            "reservación confirmada",
        ],
        "sending_menu_sms": [
            "le envío el menú por mensaje",
            "le mando el menú por texto",
        ],
        "call_ending": [
            "que tenga un buen día",
            "gracias por llamar",
        ],
    },
)


LANGUAGE_PROMPTS: Dict[str, LanguagePromptBundle] = {
    "en": _EN,
    "te": _TE,
    "hi": _HI,
    "es": _ES,
}


# Human-readable name in the language itself + Latin transliteration (for IVR prompt).
LANGUAGE_NAMES: Dict[str, Dict[str, str]] = {
    "en": {"native": "English",  "latin": "English"},
    "te": {"native": "తెలుగు",    "latin": "Telugu"},
    "hi": {"native": "हिंदी",       "latin": "Hindi"},
    "es": {"native": "Español",  "latin": "Spanish"},
}


def is_supported(lang: str) -> bool:
    return lang in LANGUAGE_PROMPTS


_EMPTY_SIGNALS = {
    "order_confirmed":       False,
    "escalate_to_human":     False,
    "appointment_confirmed": False,
    "reservation_confirmed": False,
    "sending_menu_sms":      False,
    "call_ending":           False,
}


def signals_for(lang: str, text: str) -> Dict[str, bool]:
    """
    Detect AI-turn signals from text using the language's trigger phrase dict.

    ESCALATE_TO_HUMAN is a literal English token the prompt instructs the AI to
    emit regardless of conversation language, so it is always matched as a raw
    substring. Other signals match against language-specific natural-language
    phrases (case-insensitive substring match).
    """
    if not text or len(text.strip()) < 3:
        return dict(_EMPTY_SIGNALS)

    bundle = LANGUAGE_PROMPTS.get(lang) or LANGUAGE_PROMPTS["en"]
    text_lower = text.lower()

    return {
        "order_confirmed":       any(p.lower() in text_lower for p in bundle.triggers.get("order_confirmed", [])),
        "escalate_to_human":     "ESCALATE_TO_HUMAN" in text,
        "appointment_confirmed": any(p.lower() in text_lower for p in bundle.triggers.get("appointment_confirmed", [])),
        "reservation_confirmed": any(p.lower() in text_lower for p in bundle.triggers.get("reservation_confirmed", [])),
        "sending_menu_sms":      any(p.lower() in text_lower for p in bundle.triggers.get("sending_menu_sms", [])),
        "call_ending":           any(p.lower() in text_lower for p in bundle.triggers.get("call_ending", [])),
    }