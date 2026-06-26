"""PL-03 regression: the Gemini text SDK call must run on the async event loop
without blocking it. The native google-genai client is awaited directly
(client.aio.models.generate_content), so — unlike the old sync OpenAI client —
the model request must NOT be dispatched through asyncio.to_thread.

These bugs passed all prior tests precisely because the client is always mocked,
so we assert on *how* the call is dispatched (awaited natively, not offloaded),
not just that it returns a value.
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


def _async_fake_client(content, flag):
    """Native google-genai stand-in that records when generate_content is awaited."""
    async def _gen(**kwargs):
        flag["awaited"] = True
        return SimpleNamespace(
            text=content,
            usage_metadata=SimpleNamespace(
                prompt_token_count=10, candidates_token_count=5, total_token_count=15),
        )
    return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=_gen)))


def _spy_to_thread(monkeypatch, module):
    """Record every callable handed to the module's asyncio.to_thread."""
    seen = []
    real_to_thread = asyncio.to_thread

    async def _spy(func, *args, **kwargs):
        seen.append(getattr(func, "__name__", repr(func)))
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", _spy)
    return seen


async def test_extract_order_uses_native_async_not_thread(monkeypatch):
    import gemini_service
    from gemini_service import MenuIndex, extract_order_from_transcript

    flag = {}
    monkeypatch.setattr(
        "gemini_service._get_client",
        lambda: _async_fake_client(json.dumps({"order_confirmed": False, "items": []}), flag),
    )
    seen = _spy_to_thread(monkeypatch, gemini_service)

    await extract_order_from_transcript(
        transcript=[
            {"role": "customer", "text": "one biryani please"},
            {"role": "ai", "text": "Your order is confirmed!"},
        ],
        menu_index=MenuIndex(_MENU),
    )

    assert flag.get("awaited") is True, "must await the native async Gemini client"
    assert "generate_content" not in seen, (
        "the native async model call must NOT be offloaded to a worker thread"
    )


async def test_analyse_uses_native_async_not_thread(monkeypatch):
    import gemini_service
    from gemini_service import analyse_call_transcript

    flag = {}
    monkeypatch.setattr(
        "gemini_service._get_client",
        lambda: _async_fake_client(json.dumps({"quality_score": 5, "order_accuracy": "n/a"}), flag),
    )
    seen = _spy_to_thread(monkeypatch, gemini_service)

    await analyse_call_transcript(
        transcript=[{"role": "customer", "text": "hi"}, {"role": "ai", "text": "hello"}],
    )

    assert flag.get("awaited") is True, "must await the native async Gemini client"
    assert "create" not in seen and "generate_content" not in seen
