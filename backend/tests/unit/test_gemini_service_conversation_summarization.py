"""
Unit tests for backend/gemini_service.py — conversation context summarization.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _summarize_conversation_context
# ---------------------------------------------------------------------------

def test_summarize_short_transcript_returns_full():
    from gemini_service import _summarize_conversation_context
    transcript = [
        {"role": "customer", "text": "Hi"},
        {"role": "ai", "text": "Hello"},
        {"role": "customer", "text": "Order pizza"},
    ]
    out = _summarize_conversation_context(transcript, max_turns=6)
    assert out == transcript


def test_summarize_long_transcript_keeps_head_and_tail():
    from gemini_service import _summarize_conversation_context
    transcript = [
        {"role": "customer", "text": f"turn_{i}"} for i in range(20)
    ]
    out = _summarize_conversation_context(transcript, max_turns=6)
    assert len(out) == 6
    # First two entries preserved
    assert out[0]["text"] == "turn_0"
    assert out[1]["text"] == "turn_1"
    # Last four entries should be the recent ones
    assert out[-1]["text"] == "turn_19"


def test_summarize_with_max_turns_equals_len_returns_full():
    from gemini_service import _summarize_conversation_context
    transcript = [{"role": "x", "text": str(i)} for i in range(6)]
    out = _summarize_conversation_context(transcript, max_turns=6)
    assert len(out) == 6


def test_summarize_with_single_turn_transcript():
    from gemini_service import _summarize_conversation_context
    transcript = [{"role": "customer", "text": "Hi"}]
    out = _summarize_conversation_context(transcript, max_turns=6)
    assert out == transcript


# ---------------------------------------------------------------------------
# get_conversation_response — happy path & failure modes
# ---------------------------------------------------------------------------

def _patch_gemini(monkeypatch, content):
    async def _gen(**kwargs):
        return SimpleNamespace(text=content, usage_metadata=None)
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))
    monkeypatch.setattr("gemini_service._get_client", lambda: fake)


async def test_conversation_response_returns_text_when_client_works(monkeypatch):
    from gemini_service import get_conversation_response
    _patch_gemini(monkeypatch, "Here's your order — anything else?")

    out = await get_conversation_response(
        system_prompt="You are a helpful assistant.",
        transcript=[],
        new_customer_message="I want a pizza",
    )
    assert "anything else" in out.lower()


async def test_conversation_response_falls_back_to_mock_without_client(monkeypatch):
    from gemini_service import get_conversation_response
    monkeypatch.setattr("gemini_service._get_client", lambda: None)

    out = await get_conversation_response(
        system_prompt="You are a helpful assistant.",
        transcript=[],
        new_customer_message="I want a pizza",
    )
    # _mock_conversation_response returns something pizza-related from "order"/"like"
    assert isinstance(out, str) and len(out) > 0


async def test_conversation_response_truncates_long_system_prompt(monkeypatch):
    from gemini_service import get_conversation_response

    captured = {}

    async def _gen(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text="ok", usage_metadata=None)
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))

    monkeypatch.setattr("gemini_service._get_client", lambda: fake)

    long_prompt = "x" * 5000
    await get_conversation_response(
        system_prompt=long_prompt,
        transcript=[],
        new_customer_message="hi",
    )
    system_message = captured["config"].system_instruction  # condensed prompt now in system_instruction
    assert len(system_message) < len(long_prompt)
    assert "truncated" in system_message.lower()


async def test_conversation_response_includes_summarized_transcript(monkeypatch):
    from gemini_service import get_conversation_response

    captured = {}

    async def _gen(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text="ok", usage_metadata=None)
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))

    monkeypatch.setattr("gemini_service._get_client", lambda: fake)

    long_transcript = [
        {"role": "customer" if i % 2 == 0 else "ai", "text": f"turn_{i}"}
        for i in range(20)
    ]
    await get_conversation_response(
        system_prompt="sys",
        transcript=long_transcript,
        new_customer_message="now",
    )
    # contents = summarized transcript + new user (system_instruction is separate now)
    assert len(captured["contents"]) <= 7  # 6 summarized + 1 new


async def test_conversation_response_handles_budget_exceeded_gracefully(monkeypatch):
    """A 'budget exceeded' error from Gemini falls back to the mock response."""
    from gemini_service import get_conversation_response

    async def _gen(**kwargs):
        raise RuntimeError("Budget exceeded for project xyz")
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))

    monkeypatch.setattr("gemini_service._get_client", lambda: fake)

    out = await get_conversation_response(
        system_prompt="sys",
        transcript=[],
        new_customer_message="order pizza",
    )
    assert isinstance(out, str) and len(out) > 0


async def test_conversation_response_handles_generic_exception(monkeypatch):
    from gemini_service import get_conversation_response

    async def _gen(**kwargs):
        raise ConnectionError("connection refused")
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))

    monkeypatch.setattr("gemini_service._get_client", lambda: fake)

    out = await get_conversation_response(
        system_prompt="sys",
        transcript=[],
        new_customer_message="hi",
    )
    assert isinstance(out, str)


async def test_conversation_response_uses_mock_for_empty_response(monkeypatch):
    """If Gemini returns an empty string, fall back to the mock."""
    from gemini_service import get_conversation_response
    _patch_gemini(monkeypatch, "")

    out = await get_conversation_response(
        system_prompt="sys",
        transcript=[],
        new_customer_message="order pizza",
    )
    # Mock for "order" returns "what would you like to order today"
    assert "order" in out.lower()


# ---------------------------------------------------------------------------
# _mock_conversation_response — covers all branches
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,expected_substring", [
    ("I want to order pizza", "order"),
    ("Like to place an order", "order"),
    ("Reservation for tonight", "reservation"),
    ("Book a table", "reservation"),
    ("What are your hours?", "open"),
    ("Are you open?", "open"),
    ("", "help"),
    ("random question", "more"),
])
def test_mock_conversation_response_branches(message, expected_substring):
    from gemini_service import _mock_conversation_response
    out = _mock_conversation_response(message)
    assert expected_substring in out.lower()
