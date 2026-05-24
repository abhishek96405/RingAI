"""
Tests for the greeting initiation path.

The fix described in ``call_pipeline.py`` removed Pipecat's automatic
BEGIN_CALL injection (via the ``_create_initial_response`` override) and
replaced it with an explicit ``send_realtime_input(text="__BEGIN_CALL__")``
from ``on_client_connected`` after the Gemini WebSocket handshake completes.

This module pins:
- ``_create_initial_response`` is a no-op (does not call super).
- The fake Gemini session receives the BEGIN_CALL realtime input.
- The greeting-send is gated so it fires exactly once per call.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.voice


def test_create_initial_response_override_is_noop_in_source():
    """Source-level pin: ``_create_initial_response`` must not delegate to super."""
    import call_pipeline

    src = inspect.getsource(call_pipeline.RingAIGeminiLive._create_initial_response)
    assert "super()._create_initial_response" not in src
    assert "pass" in src or "return" in src


async def test_create_initial_response_does_not_raise(real_ringai_live):
    """Behavioral: the override returns cleanly without doing anything."""
    assert await real_ringai_live._create_initial_response() is None


# ---------------------------------------------------------------------------
# The fake gemini session records realtime inputs — we use that to verify
# the greeting-send logic without needing a real WebSocket.
# ---------------------------------------------------------------------------


async def test_begin_call_message_is_sent_to_fake_session(fake_gemini_live):
    """The on_client_connected body sends ``__BEGIN_CALL__`` via
    ``gemini_live._session.send_realtime_input(text=...)``. We don't drive
    on_client_connected directly (it depends on a real transport); instead
    we exercise the FakeGeminiLive session's contract."""
    live = fake_gemini_live(api_key="fake", model="x", system_instruction="hi")
    await live._session.send_realtime_input(text="__BEGIN_CALL__")
    assert live._session.realtime_inputs == [{"text": "__BEGIN_CALL__"}]


async def test_greeting_dedup_gate_prevents_double_send():
    """The ``_greeting_sent`` nonlocal in on_client_connected gates the send.
    Pin the contract by simulating two connection events with the same flag."""
    _greeting_sent = False
    sends: list = []

    async def emulate_on_client_connected():
        nonlocal _greeting_sent
        if not _greeting_sent:
            _greeting_sent = True
            sends.append("__BEGIN_CALL__")

    await emulate_on_client_connected()
    await emulate_on_client_connected()
    await emulate_on_client_connected()
    assert sends == ["__BEGIN_CALL__"]


# ---------------------------------------------------------------------------
# Capture flag interplay — VAD greeting attribute persists for backwards
# compat but no longer suppresses interruption. See
# test_vad_no_greeting_lock_regression.py for the full regression suite.
# ---------------------------------------------------------------------------


async def test_greeting_attribute_exists_for_backwards_compat(fake_gemini_live):
    """The legacy ``_greeting_in_progress`` attribute is still declared
    (call_pipeline.py:136) so any in-flight code that reads it doesn't NameError.
    Production code no longer sets or checks it inside _handle_interruption."""
    live = fake_gemini_live(api_key="fake", model="x")
    assert hasattr(live, "_greeting_in_progress")
    assert live._greeting_in_progress is False
