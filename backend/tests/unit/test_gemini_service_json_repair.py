"""
Unit tests for backend/gemini_service.py — _repair_json fuzz and idempotency.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module slice: >= 85%.
"""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Common LLM mistakes — basic cases
# ---------------------------------------------------------------------------

def test_repair_valid_json_passthrough():
    from gemini_service import _repair_json
    text = '{"a": 1, "b": "x"}'
    out = _repair_json(text)
    assert json.loads(out) == {"a": 1, "b": "x"}


def test_repair_strips_json_codefence():
    from gemini_service import _repair_json
    text = '```json\n{"a": 1}\n```'
    assert json.loads(_repair_json(text)) == {"a": 1}


def test_repair_strips_unlabeled_codefence():
    from gemini_service import _repair_json
    text = '```\n{"a": 1}\n```'
    assert json.loads(_repair_json(text)) == {"a": 1}


def test_repair_strips_leading_commentary():
    from gemini_service import _repair_json
    text = 'Here is the JSON you asked for:\n{"a": 1}'
    assert json.loads(_repair_json(text)) == {"a": 1}


def test_repair_strips_trailing_commentary():
    from gemini_service import _repair_json
    text = '{"a": 1}\n\nThat is your answer.'
    assert json.loads(_repair_json(text)) == {"a": 1}


def test_repair_returns_parseable_or_empty_on_truncated_object():
    """A truncated object may either be repaired or fall back to '{}'.

    Document the current behavior: the repair gives up and returns '{}'
    when the trailing structure can't be closed cleanly.
    """
    from gemini_service import _repair_json
    text = '{"a": 1, "b": {"c": 2'
    out = _repair_json(text)
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_repair_returns_parseable_or_empty_on_truncated_array():
    from gemini_service import _repair_json
    text = '{"items": [1, 2, 3'
    out = _repair_json(text)
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_repair_returns_empty_object_on_no_braces():
    from gemini_service import _repair_json
    assert _repair_json("no json here") == "{}"


def test_repair_returns_empty_object_on_empty_input():
    from gemini_service import _repair_json
    assert _repair_json("") == "{}"


def test_repair_returns_empty_dict_on_partially_recoverable_input():
    """When the first { ... } substring is empty, repair returns '{ }' (or '{}').

    Both parse to an empty dict — that's the important invariant.
    """
    from gemini_service import _repair_json
    out = _repair_json("} { } broken { { mismatched")
    assert json.loads(out) == {}


def test_repair_handles_unterminated_string():
    from gemini_service import _repair_json
    text = '{"a": "unterminated'
    out = _repair_json(text)
    # Either repaired or fell back to "{}"
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_repair_normalises_newlines_inside_object():
    from gemini_service import _repair_json
    text = '{"a":\n1,\n"b":\n2}'
    out = _repair_json(text)
    assert json.loads(out) == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Idempotency property
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"x": "y"}\n```',
    'Before: {"k": "v"}',
    '{"a": 1, "b": [1, 2',  # malformed
    'not json',
    '',
])
def test_repair_is_idempotent(text):
    from gemini_service import _repair_json
    once = _repair_json(text)
    twice = _repair_json(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Hypothesis fuzz
# ---------------------------------------------------------------------------

@given(st.text(min_size=0, max_size=300))
@settings(max_examples=80, deadline=None)
def test_repair_never_raises(text):
    """Property: repair never raises, returns a string."""
    from gemini_service import _repair_json
    result = _repair_json(text)
    assert isinstance(result, str)


@given(st.text(min_size=0, max_size=300))
@settings(max_examples=80, deadline=None)
def test_repair_either_returns_valid_json_or_empty_dict(text):
    """Property: the output is either parseable JSON or the literal '{}'."""
    from gemini_service import _repair_json
    out = _repair_json(text)
    if out == "{}":
        return  # documented escape hatch
    # Otherwise must be parseable
    json.loads(out)


@given(st.text(min_size=0, max_size=300))
@settings(max_examples=80, deadline=None)
def test_repair_idempotent_property(text):
    from gemini_service import _repair_json
    a = _repair_json(text)
    b = _repair_json(a)
    assert a == b


# ---------------------------------------------------------------------------
# _extract_json_fields — regex fallback
# ---------------------------------------------------------------------------

def test_extract_json_fields_quality_score():
    from gemini_service import _extract_json_fields
    text = 'crap "quality_score": 87 other stuff'
    out = _extract_json_fields(text, ["quality_score"])
    assert out["quality_score"] == 87


def test_extract_json_fields_summary():
    from gemini_service import _extract_json_fields
    text = '... "summary": "Order placed successfully" ...'
    out = _extract_json_fields(text, ["summary"])
    assert out["summary"] == "Order placed successfully"


def test_extract_json_fields_list_field():
    from gemini_service import _extract_json_fields
    text = '... "issues": ["one", "two", "three"] ...'
    out = _extract_json_fields(text, ["issues"])
    assert out["issues"] == ["one", "two", "three"]


def test_extract_json_fields_returns_only_requested():
    from gemini_service import _extract_json_fields
    text = '"quality_score": 99, "summary": "x"'
    out = _extract_json_fields(text, ["quality_score"])
    assert "quality_score" in out
    assert "summary" not in out
