"""PL-03 regression: blocking SDK calls must be offloaded to a worker thread
via asyncio.to_thread so they never stall the single-worker event loop while
live audio calls are in flight.

These are the bugs that passed all 1695 prior tests precisely because the
OpenAI client is always mocked — so we assert on *how* the call is dispatched
(through to_thread), not just that it returns a value.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_MENU = [
    {"id": "m1", "name": "Chicken Biryani", "category": "Mains", "price": 1299, "available": True},
]


def _fake_client(content):
    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                        usage=None,
                    )

    return _FakeClient


def _spy_to_thread(monkeypatch, module):
    """Patch the given module's asyncio.to_thread, recording each offloaded
    callable's name while still delegating to the real implementation."""
    seen = []
    real_to_thread = asyncio.to_thread

    async def _spy(func, *args, **kwargs):
        seen.append(getattr(func, "__name__", repr(func)))
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", _spy)
    return seen


async def test_extract_order_offloads_blocking_sdk_call(monkeypatch):
    import gemini_service
    from gemini_service import MenuIndex, extract_order_from_transcript

    monkeypatch.setattr(
        "gemini_service._get_client",
        lambda: _fake_client(json.dumps({"order_confirmed": False, "items": []})),
    )
    seen = _spy_to_thread(monkeypatch, gemini_service)

    idx = MenuIndex(_MENU)
    await extract_order_from_transcript(
        transcript=[
            {"role": "customer", "text": "one biryani please"},
            {"role": "ai", "text": "Your order is confirmed!"},
        ],
        menu_index=idx,
    )

    assert "create" in seen, (
        "extract_order_from_transcript must dispatch the OpenAI SDK call via "
        "asyncio.to_thread (offloaded), not directly on the event loop"
    )


async def test_analyse_transcript_offloads_blocking_sdk_call(monkeypatch):
    import gemini_service
    from gemini_service import analyse_call_transcript

    monkeypatch.setattr(
        "gemini_service._get_client",
        lambda: _fake_client(json.dumps({"quality_score": 5, "order_accuracy": "n/a"})),
    )
    seen = _spy_to_thread(monkeypatch, gemini_service)

    await analyse_call_transcript(
        transcript=[{"role": "customer", "text": "hi"}, {"role": "ai", "text": "hello"}],
    )

    assert "create" in seen, (
        "analyse_call_transcript must dispatch the OpenAI SDK call via asyncio.to_thread"
    )
