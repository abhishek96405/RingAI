"""
language_prompts.py — Per-language signal trigger phrases.

The per-language conversational guidance for the AI lives in
gemini_service._build_language_section. This module is the single source
of truth for:
  1. The phrase triggers used by signals_for() to detect events like
     ORDER_CONFIRMED in any language, without an LLM classifier.
  2. LANGUAGE_NAMES — display strings used by the IVR menu.

Adding a language: fill in the triggers, register the bundle in
LANGUAGE_PROMPTS, and add a row to LANGUAGE_NAMES. No other code changes
are required here (you also need to extend _build_language_section in
gemini_service.py for the AI's conversational style).
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class LanguagePromptBundle:
    triggers: Dict[str, List[str]] = field(default_factory=dict)


_EN = LanguagePromptBundle(
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