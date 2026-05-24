"""
Tests for language-aware signal handling and mid-call language switching.

``CallSession.add_transcript_entry`` consults
:func:`language_prompts.signals_for` to detect language-specific phrases
(e.g. Telugu "మీ ఆర్డర్ confirm అయింది") in addition to the English keyword
list in :func:`gemini_service.detect_call_signals`. We pin:

- The two signal sources are OR-merged, not AND-merged.
- A session can flip ``lang`` mid-call and the next add_transcript_entry
  uses the new language's phrase set.
- Language-specific ESCALATE phrases trigger the same escalation path.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from gemini_service import OrderItem, OrderState

pytestmark = pytest.mark.voice


def test_session_starts_with_caller_default_language(make_call_session):
    sess = make_call_session(lang="te")
    assert sess.lang == "te"


def test_session_lang_can_flip_mid_call(make_call_session):
    sess = make_call_session(lang="en")
    sess.lang = "te"
    assert sess.lang == "te"


# ---------------------------------------------------------------------------
# signals_for and detect_call_signals are OR-merged.
# Patch language_prompts.signals_for to return synthetic signals so we can
# verify the merge without relying on real Telugu phrase data.
# ---------------------------------------------------------------------------


async def test_language_phrase_signal_or_merged_with_english(
    make_call_session, stub_kitchen_dispatch
):
    sess = make_call_session(lang="te")
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMING, "test")

    # Only the language-specific signal returns True for order_confirmed.
    with patch("language_prompts.signals_for", return_value={"order_confirmed": True}):
        sess.add_transcript_entry("ai", "మీ ఆర్డర్ confirm అయింది")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert sess._order_confirmed_handled is True


async def test_english_signal_still_fires_when_language_returns_nothing(
    make_call_session, stub_kitchen_dispatch
):
    """Even when the language-specific source returns nothing, the English
    detector still triggers escalation/confirmation as expected."""
    sess = make_call_session(lang="en")
    sess.order.items.append(
        OrderItem(
            name="Pizza",
            menu_item_id="m_pizza",
            category="P",
            unit_price=1499,
            quantity=1,
        )
    )
    sess.order.transition(OrderState.CONFIRMING, "test")

    with patch("language_prompts.signals_for", return_value={}):
        sess.add_transcript_entry("ai", "Your order is confirmed.")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert sess._order_confirmed_handled is True


async def test_neither_source_returns_signal_no_state_change(make_call_session):
    sess = make_call_session(lang="te")
    assert sess.order.state == OrderState.GREETING

    with patch("language_prompts.signals_for", return_value={"order_confirmed": False}):
        sess.add_transcript_entry("ai", "casual chitchat with no signal phrases")
    await asyncio.sleep(0)
    assert sess.order.state == OrderState.GREETING


# ---------------------------------------------------------------------------
# Mid-call language flip — the next signal lookup uses the new language code.
# ---------------------------------------------------------------------------


async def test_mid_call_language_flip_updates_signal_source(
    make_call_session, monkeypatch
):
    sess = make_call_session(lang="en")

    seen_langs: list = []

    def fake_signals_for(lang, text):
        seen_langs.append(lang)
        return {}

    monkeypatch.setattr("language_prompts.signals_for", fake_signals_for)

    sess.add_transcript_entry("ai", "Hello")
    sess.lang = "te"
    sess.add_transcript_entry("ai", "నమస్తే")
    sess.lang = "hi"
    sess.add_transcript_entry("ai", "नमस्ते")

    assert seen_langs == ["en", "te", "hi"]


# ---------------------------------------------------------------------------
# Escalation phrase in a non-English language also routes through the
# escalation pipeline (signals_for returns escalate_to_human: True).
# ---------------------------------------------------------------------------


async def test_language_escalation_signal_triggers_escalation_path(
    make_call_session, monkeypatch
):
    sess = make_call_session(lang="te")
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = type("T", (), {"cancel": lambda self: None})()

    async def fake_schedule_hangup(reason=""):
        sess._hangup_scheduled = True
        sess._escalation_reason = reason

    sess._schedule_hangup = fake_schedule_hangup

    with patch(
        "language_prompts.signals_for", return_value={"escalate_to_human": True}
    ):
        sess.add_transcript_entry("ai", "మానవ స్థాయికి ఎస్కలేట్ చేస్తున్నాము")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert sess._escalated is True
    assert sess.order.state == OrderState.ESCALATED
