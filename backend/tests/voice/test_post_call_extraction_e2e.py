"""
End-to-end post-call extraction tests using realistic transcript fixtures.

Post-call extraction is **the source of truth for cart and order totals**:
the in-call running cart is approximate — what actually goes to the kitchen
and what the customer is billed is determined here. The kitchen and POS
adapters consume this output, so any regression here propagates straight
to revenue.

We test ``extract_order_from_transcript`` from ``gemini_service``. The
real function uses Gemini; we mock the LLM client to return a deterministic
JSON shape derived from the transcript fixture's ``expected`` block. This
lets us pin the downstream parsing, menu validation, and order construction
without any network or LLM nondeterminism.

The 12 transcript fixtures live in ``backend/tests/fixtures/transcripts/``
— each one is a recorded conversation plus an ``expected`` block describing
the structured output the extraction pipeline should produce.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from tests.voice.conftest import _load_transcript_fixture, transcript_fixture_ids

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_gemini_response(
    items: list[dict] | None,
    order_type: str = "pickup",
    delivery_address: str = "",
    special_instructions: str = "",
) -> str:
    """Build the JSON body the Gemini client would return for a given fixture."""
    payload = {
        "order_confirmed": items is not None and len(items) > 0,
        "items": items or [],
        "order_type": order_type,
        "customer_name": "",
        "delivery_address": delivery_address,
        "special_instructions": special_instructions,
    }
    return json.dumps(payload)


class _FakeGenResponse:
    """Stand-in for google-genai ``generate_content`` return value."""

    def __init__(self, content: str):
        self.text = content
        self.usage_metadata = type("U", (), {
            "prompt_token_count": 100, "candidates_token_count": 50, "total_token_count": 150})()


def _patch_gemini_client(monkeypatch, response_json: str):
    """Force ``gemini_service._get_client()`` to return a native stub whose
    ``aio.models.generate_content`` returns ``response_json``."""
    import gemini_service
    from types import SimpleNamespace

    async def _gen(**kwargs):
        return _FakeGenResponse(response_json)

    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))
    monkeypatch.setattr(gemini_service, "_get_client", lambda: fake)


# ---------------------------------------------------------------------------
# Per-fixture parametrized smoke test.
# ---------------------------------------------------------------------------


def _load_all_fixtures() -> list[dict]:
    from pathlib import Path

    fdir = Path(__file__).resolve().parents[1] / "fixtures" / "transcripts"
    return [_load_transcript_fixture(p) for p in sorted(fdir.glob("*.json"))]


_ALL_FIXTURES = _load_all_fixtures()


@pytest.mark.parametrize(
    "fixture", _ALL_FIXTURES, ids=transcript_fixture_ids(_ALL_FIXTURES)
)
def test_transcript_fixture_has_required_keys(fixture):
    """Each fixture must declare name, transcript, and expected."""
    assert "name" in fixture
    assert "transcript" in fixture
    assert "expected" in fixture
    assert isinstance(fixture["transcript"], list)


# ---------------------------------------------------------------------------
# Targeted extraction tests per fixture — each runs the real extraction
# function against a mocked Gemini client and asserts the structured output.
# ---------------------------------------------------------------------------


async def test_simple_single_item_pickup_extracts_one_item(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "simple_single_item_pickup")
    response = _make_fake_gemini_response(
        items=[{"name": "Margherita Pizza", "quantity": 1}],
        order_type="pickup",
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is not None
    assert order.order_type == "pickup"
    assert len(order.items) == 1
    assert order.items[0].name == "Margherita Pizza"
    assert order.total == 1499


async def test_multi_item_with_modifiers_preserves_special_instructions(
    monkeypatch, minimal_menu
):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "multi_item_with_modifiers")
    response = _make_fake_gemini_response(
        items=[
            {
                "name": "Margherita Pizza",
                "quantity": 1,
                "special_instructions": "no onions",
            },
            {"name": "Samosa", "quantity": 2},
        ],
        order_type="pickup",
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is not None
    names = sorted(i.name for i in order.items)
    assert names == ["Margherita Pizza", "Samosa"]
    assert order.total == 1499 + (2 * 399)
    pizza = next(i for i in order.items if i.name == "Margherita Pizza")
    assert pizza.special_instructions == "no onions"


async def test_mid_call_correction_extracts_only_final_order(monkeypatch, minimal_menu):
    """Capture the bug: extraction is told to ignore cancelled items via the
    prompt, but ultimately the test verifies the LLM's structured output
    contains only what the customer confirmed after restart."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(
        f for f in _ALL_FIXTURES if f["name"] == "order_with_mid_call_correction"
    )
    response = _make_fake_gemini_response(
        items=[{"name": "Chicken Biryani", "quantity": 1}],
        order_type="pickup",
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is not None
    names = [i.name for i in order.items]
    assert "Margherita Pizza" not in names
    assert "Chicken Biryani" in names


async def test_ambiguous_trailing_off_returns_none(monkeypatch, minimal_menu):
    """When the AI never confirms, extraction returns None — no items dispatched."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "ambiguous_trailing_off")
    response = json.dumps({"order_confirmed": False, "items": []})
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is None


async def test_telugu_order_extraction(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "telugu_order")
    response = _make_fake_gemini_response(
        items=[{"name": "Chicken Biryani", "quantity": 1}],
        order_type="pickup",
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is not None
    assert order.items[0].name == "Chicken Biryani"


async def test_language_mid_switch_extraction(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "language_mid_switch")
    response = _make_fake_gemini_response(
        items=[{"name": "Samosa", "quantity": 2}],
        order_type="pickup",
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is not None
    assert order.total == 798


async def test_delivery_with_address_preserves_address(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "delivery_with_address")
    response = _make_fake_gemini_response(
        items=[{"name": "Margherita Pizza", "quantity": 1}],
        order_type="delivery",
        delivery_address="1234 Elm Street, Apartment 5B, Austin TX 78704",
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is not None
    assert order.order_type == "delivery"
    assert "Elm Street" in order.delivery_address


async def test_reservation_only_does_not_produce_order(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "reservation_not_order")
    response = json.dumps({"order_confirmed": False, "items": []})
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is None


async def test_appointment_booking_not_an_order(monkeypatch, minimal_menu):
    """Salon appointments don't go through extract_order_from_transcript at all
    in production. If a developer accidentally routes one through, the
    extractor should still return None (no kitchen dispatch)."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "appointment_booking")
    response = json.dumps({"order_confirmed": False, "items": []})
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is None


async def test_general_questions_only_no_order(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    fixture = next(f for f in _ALL_FIXTURES if f["name"] == "general_questions_only")
    response = json.dumps({"order_confirmed": False, "items": []})
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        fixture["transcript"], MenuIndex(minimal_menu)
    )
    assert order is None


async def test_empty_transcript_returns_none(monkeypatch, minimal_menu):
    from gemini_service import MenuIndex, extract_order_from_transcript

    response = json.dumps({"order_confirmed": False, "items": []})
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript([], MenuIndex(minimal_menu))
    assert order is None


# ---------------------------------------------------------------------------
# Invariants that hold across every fixture.
# ---------------------------------------------------------------------------


async def test_extraction_with_no_gemini_client_returns_none(monkeypatch, minimal_menu):
    """If the Gemini client isn't configured (no API key), extraction returns
    None gracefully — does not raise."""
    import gemini_service
    from gemini_service import MenuIndex, extract_order_from_transcript

    monkeypatch.setattr(gemini_service, "_get_client", lambda: None)
    order = await extract_order_from_transcript(
        [{"role": "customer", "text": "I want a pizza"}], MenuIndex(minimal_menu)
    )
    assert order is None


async def test_extraction_with_unknown_item_skips_it(monkeypatch, minimal_menu):
    """LLM hallucinations of items not on the menu must be filtered out."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    response = _make_fake_gemini_response(
        items=[
            {"name": "Margherita Pizza", "quantity": 1},
            {"name": "Imaginary Item Not On Menu", "quantity": 2},
        ],
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        [{"role": "customer", "text": "..."}],
        MenuIndex(minimal_menu),
    )
    assert order is not None
    assert len(order.items) == 1
    assert order.items[0].name == "Margherita Pizza"


async def test_extraction_with_quantity_zero_clamps_to_one(monkeypatch, minimal_menu):
    """Production code does ``max(1, int(raw_item.get("quantity", 1)))``."""
    from gemini_service import MenuIndex, extract_order_from_transcript

    response = _make_fake_gemini_response(
        items=[{"name": "Samosa", "quantity": 0}],
    )
    _patch_gemini_client(monkeypatch, response)

    order = await extract_order_from_transcript(
        [{"role": "customer", "text": "..."}],
        MenuIndex(minimal_menu),
    )
    assert order is not None
    assert order.items[0].quantity == 1
