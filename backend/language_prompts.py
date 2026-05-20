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
        "═══════════════════════════════════════\n"
        "LANGUAGE: TELUGU (తెలుగు)\n"
        "═══════════════════════════════════════\n"
        "Conduct this ENTIRE conversation in Telugu from the very first word.\n"
        "Use natural, colloquial Telugu — not stiff word-for-word translations.\n"
        "Keep menu item names, customer names, and street addresses in their\n"
        "original Latin form. Apply ALL order protocol steps, menu rules,\n"
        "escalation rules, and edge-case handling from the sections below —\n"
        "just say them in Telugu.\n"
        "When confirming an order, say it clearly in Telugu, e.g.\n"
        "'మీ ఆర్డర్ కన్ఫర్మ్ అయిపోయింది.'\n"
        "If the customer EXPLICITLY asks mid-call to switch languages, comply.\n"
        "Otherwise do NOT switch languages.\n"
        "When you need to transfer the call, still say the literal token\n"
        "ESCALATE_TO_HUMAN in English after your Telugu sentence — it is a\n"
        "backend trigger, not for the customer.\n"
        "\n"
    ),
    triggers={
        "order_confirmed": [
            "ఆర్డర్ కన్ఫర్మ్",
            "ఆర్డర్ ఖరారు",
            "ఆర్డర్ ప్లేస్ అయింది",
            "your order is confirmed",
        ],
        "appointment_confirmed": [
            "అపాయింట్‌మెంట్ కన్ఫర్మ్",
            "అపాయింట్మెంట్ ఖరారు",
        ],
        "reservation_confirmed": [
            "టేబుల్ రిజర్వ్",
            "టేబుల్ బుక్",
            "రిజర్వేషన్ కన్ఫర్మ్",
        ],
        "sending_menu_sms": [
            "మెనూ టెక్స్ట్",
            "మెనూ పంపిస్తాను",
        ],
        "call_ending": [
            "ధన్యవాదాలు",
            "మంచి రోజు",
        ],
    },
)

_HI = LanguagePromptBundle(
    directive=(
        "═══════════════════════════════════════\n"
        "LANGUAGE: HINDI (हिंदी)\n"
        "═══════════════════════════════════════\n"
        "Conduct this ENTIRE conversation in Hindi from the very first word.\n"
        "Use natural, colloquial Hindi — not stiff word-for-word translations.\n"
        "Keep menu item names, customer names, and street addresses in their\n"
        "original Latin form. Apply ALL order protocol steps, menu rules,\n"
        "escalation rules, and edge-case handling from the sections below —\n"
        "just say them in Hindi.\n"
        "When confirming an order, say it clearly in Hindi, e.g.\n"
        "'आपका ऑर्डर कन्फर्म हो गया है.'\n"
        "If the customer EXPLICITLY asks mid-call to switch languages, comply.\n"
        "Otherwise do NOT switch languages.\n"
        "When you need to transfer the call, still say the literal token\n"
        "ESCALATE_TO_HUMAN in English after your Hindi sentence — it is a\n"
        "backend trigger, not for the customer.\n"
        "\n"
    ),
    triggers={
        "order_confirmed": [
            "ऑर्डर कन्फर्म",
            "ऑर्डर पक्का",
            "ऑर्डर हो गया",
            "your order is confirmed",
        ],
        "appointment_confirmed": [
            "अपॉइंटमेंट कन्फर्म",
            "अपॉइंटमेंट पक्का",
        ],
        "reservation_confirmed": [
            "टेबल रिज़र्व",
            "टेबल बुक",
            "रिज़र्वेशन कन्फर्म",
        ],
        "sending_menu_sms": [
            "मेन्यू टेक्स्ट",
            "मेन्यू भेज",
        ],
        "call_ending": [
            "धन्यवाद",
            "अच्छा दिन",
        ],
    },
)

_ES = LanguagePromptBundle(
    directive=(
        "═══════════════════════════════════════\n"
        "LANGUAGE: SPANISH (Español)\n"
        "═══════════════════════════════════════\n"
        "Conduct this ENTIRE conversation in Spanish from the very first word.\n"
        "Use natural, colloquial Spanish — adapt formality to the customer.\n"
        "Keep menu item names, customer names, and street addresses in their\n"
        "original form. Apply ALL order protocol steps, menu rules, escalation\n"
        "rules, and edge-case handling from the sections below — just say them\n"
        "in Spanish.\n"
        "When confirming an order, say it clearly in Spanish, e.g.\n"
        "'Su pedido está confirmado.'\n"
        "If the customer EXPLICITLY asks mid-call to switch languages, comply.\n"
        "Otherwise do NOT switch languages.\n"
        "When you need to transfer the call, still say the literal token\n"
        "ESCALATE_TO_HUMAN in English after your Spanish sentence — it is a\n"
        "backend trigger, not for the customer.\n"
        "\n"
    ),
    triggers={
        "order_confirmed": [
            "pedido está confirmado",
            "pedido confirmado",
            "orden confirmada",
            "your order is confirmed",
        ],
        "appointment_confirmed": [
            "cita está confirmada",
            "cita confirmada",
        ],
        "reservation_confirmed": [
            "mesa está reservada",
            "reserva confirmada",
            "reservación confirmada",
        ],
        "sending_menu_sms": [
            "le mando el menú por mensaje",
            "le envío el menú por texto",
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