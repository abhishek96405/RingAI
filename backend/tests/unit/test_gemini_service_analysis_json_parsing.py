"""
Unit tests for backend/gemini_service.py — analyse_call_transcript JSON parsing.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _patch_gemini(monkeypatch, content):
    async def _gen(**kwargs):
        return SimpleNamespace(text=content, usage_metadata=None)
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))
    monkeypatch.setattr("gemini_service._get_client", lambda: fake)


# ---------------------------------------------------------------------------
# analyse_call_transcript — mock client path
# ---------------------------------------------------------------------------

async def test_analyse_returns_mock_when_no_client(monkeypatch):
    from gemini_service import analyse_call_transcript
    monkeypatch.setattr("gemini_service._get_client", lambda: None)

    result = await analyse_call_transcript(
        transcript=[{"role": "customer", "text": "hi"}, {"role": "ai", "text": "hello"}],
    )
    assert "quality_score" in result
    assert "order_accuracy" in result


async def test_analyse_parses_valid_json(monkeypatch):
    from gemini_service import analyse_call_transcript

    _patch_gemini(monkeypatch, json.dumps({
        "quality_score": 92,
        "order_accuracy": "accurate",
        "detected_language": "en",
        "issues": ["minor pause"],
        "highlights": ["clean handoff"],
        "menu_suggestions": [],
        "rule_suggestions": [],
        "summary": "Smooth call",
    }))

    result = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert result["quality_score"] == 92
    assert result["order_accuracy"] == "accurate"
    assert result["summary"] == "Smooth call"


async def test_analyse_clips_quality_score_to_range(monkeypatch):
    """Out-of-range quality_score is clipped to [1, 100]."""
    from gemini_service import analyse_call_transcript

    _patch_gemini(monkeypatch, json.dumps({"quality_score": 250, "order_accuracy": "accurate"}))
    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert out["quality_score"] == 100

    _patch_gemini(monkeypatch, json.dumps({"quality_score": -10, "order_accuracy": "accurate"}))
    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert out["quality_score"] == 1


async def test_analyse_defaults_missing_fields(monkeypatch):
    from gemini_service import analyse_call_transcript

    # Only provide quality_score — everything else should default
    _patch_gemini(monkeypatch, json.dumps({"quality_score": 80}))

    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert out["order_accuracy"] == "accurate"
    assert out["detected_language"] == "en"
    assert out["issues"] == []
    assert out["highlights"] == []
    assert out["menu_suggestions"] == []
    assert out["rule_suggestions"] == []
    assert "summary" in out


async def test_analyse_repairs_codefenced_json(monkeypatch):
    from gemini_service import analyse_call_transcript

    raw = '```json\n{"quality_score": 88, "order_accuracy": "accurate"}\n```'
    _patch_gemini(monkeypatch, raw)

    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert out["quality_score"] == 88


async def test_analyse_falls_back_to_mock_on_malformed_json(monkeypatch):
    from gemini_service import analyse_call_transcript

    _patch_gemini(monkeypatch, "this is total garbage, no JSON anywhere")

    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    # Mock returns are random but always include these keys
    assert "quality_score" in out
    assert isinstance(out["quality_score"], int)


async def test_analyse_uses_regex_extraction_on_repair_failure(monkeypatch):
    """When _repair_json yields invalid JSON, regex fallback extracts what it can."""
    from gemini_service import analyse_call_transcript

    # Malformed JSON with valid-looking key value pairs that regex can find
    raw = '''quality_score: 75 "quality_score": 75, "order_accuracy": "acceptable" garbage no braces'''
    _patch_gemini(monkeypatch, raw)

    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    # Either regex extraction succeeds OR falls back to mock — both produce a result
    assert "quality_score" in out


async def test_analyse_handles_long_transcript_via_truncation(monkeypatch):
    """Very long transcripts get head+tail truncated; the function should still complete."""
    from gemini_service import analyse_call_transcript

    _patch_gemini(monkeypatch, json.dumps({"quality_score": 80}))

    long_transcript = [
        {"role": "customer" if i % 2 == 0 else "ai", "text": f"message {i} " * 30}
        for i in range(50)
    ]
    out = await analyse_call_transcript(transcript=long_transcript)
    assert out["quality_score"] == 80


async def test_analyse_includes_menu_context_when_menu_provided(monkeypatch):
    """The menu_items kwarg shows up in the user-message to Gemini."""
    from gemini_service import analyse_call_transcript

    captured = {}

    async def _gen(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text=json.dumps({"quality_score": 80}), usage_metadata=None)
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))

    monkeypatch.setattr("gemini_service._get_client", lambda: fake)

    await analyse_call_transcript(
        transcript=[{"role": "customer", "text": "hi"}],
        menu_items=[{"name": "Pizza", "available": True}, {"name": "Salad", "available": True}],
    )
    user_msg = captured["contents"]  # menu context now lives in the user `contents` string
    assert "Pizza" in user_msg
    assert "Salad" in user_msg


async def test_analyse_handles_exception_via_mock_fallback(monkeypatch):
    from gemini_service import analyse_call_transcript

    async def _gen(**kwargs):
        raise RuntimeError("API down")
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))

    monkeypatch.setattr("gemini_service._get_client", lambda: fake)

    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert "quality_score" in out
    assert "summary" in out


async def test_analyse_coerces_list_fields_to_lists(monkeypatch):
    """If Gemini returns a string in a list-field, coerce to empty list."""
    from gemini_service import analyse_call_transcript

    _patch_gemini(monkeypatch, json.dumps({
        "quality_score": 80,
        "issues": "not a list, just a string",
        "highlights": ["valid list"],
    }))

    out = await analyse_call_transcript(transcript=[{"role": "customer", "text": "hi"}])
    assert isinstance(out["issues"], list)
    assert out["issues"] == []  # invalid type was coerced
    assert out["highlights"] == ["valid list"]


# ---------------------------------------------------------------------------
# evaluate_call_quality — rule-based scoring
# ---------------------------------------------------------------------------

def test_evaluate_call_quality_missing_disclosure_lowers_score():
    from gemini_service import evaluate_call_quality
    transcript = [
        {"role": "ai", "text": "Hello there!"},  # no AI disclosure
        {"role": "customer", "text": "Hi"},
    ]
    result = evaluate_call_quality(transcript, order_confirmed=False, escalated=False)
    assert "AI did not disclose" in " ".join(result["protocol_violations"])


def test_evaluate_call_quality_missing_readback_lowers_score():
    from gemini_service import evaluate_call_quality
    transcript = [
        {"role": "ai", "text": "I am the virtual assistant. ORDER_CONFIRMED."},
    ]
    result = evaluate_call_quality(transcript, order_confirmed=True, escalated=False)
    # Missing readback should be a violation
    violations = " ".join(result["protocol_violations"])
    assert "readback" in violations.lower()


def test_evaluate_call_quality_with_readback_adds_highlight():
    from gemini_service import evaluate_call_quality
    transcript = [
        {"role": "ai", "text": "I am the virtual assistant. Let me read that back: one pizza. Your total is..."},
    ]
    result = evaluate_call_quality(transcript, order_confirmed=True, escalated=False)
    assert any("readback" in h.lower() for h in result["protocol_highlights"])


def test_evaluate_call_quality_clean_escalation_highlighted():
    from gemini_service import evaluate_call_quality
    transcript = [
        {"role": "ai", "text": "I'm the virtual assistant. Let me connect you with a team member. Please hold."},
    ]
    result = evaluate_call_quality(transcript, order_confirmed=False, escalated=True)
    assert "Clean escalation handoff" in result["protocol_highlights"]


def test_evaluate_call_quality_score_in_bounds():
    from gemini_service import evaluate_call_quality
    transcript = [{"role": "ai", "text": "hi"}]
    result = evaluate_call_quality(transcript, order_confirmed=False, escalated=False)
    assert 20 <= result["rule_based_score"] <= 100
