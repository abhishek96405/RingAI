"""
Regression test — VAD must NOT suppress user audio during the assistant's greeting.

Background
==========
A previous version of :class:`call_pipeline.RingAIGeminiLive` checked a
``_greeting_in_progress`` flag in :meth:`_handle_interruption` and dropped
the VAD-driven interruption when the flag was True. Symptom in production:
during the assistant's opening greeting, a caller who started speaking was
ignored — Pipecat dropped the interruption, the bot kept talking over the
user, and the order flow stalled.

The fix removed the greeting-lock check from ``_handle_interruption`` so
the only remaining suppression is ``_fn_in_progress`` (function-call window,
which is a separate and legitimate guard).

This test PROTECTS that fix. If somebody re-adds the greeting check, the
``test_user_audio_during_greeting_is_NOT_suppressed`` assertion will fail.

The flag attribute itself (``_greeting_in_progress``) is still declared on
the subclass (call_pipeline.py:136) — that's harmless. What matters is that
it is no longer consulted in ``_handle_interruption``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Core regression — greeting flag must not suppress VAD interruption.
# ---------------------------------------------------------------------------


async def test_user_audio_during_greeting_is_NOT_suppressed(
    real_ringai_live, monkeypatch
):
    """The VAD interruption MUST reach the parent class even when the
    ``_greeting_in_progress`` flag is True. This protects against
    re-introduction of the legacy greeting lock."""
    import call_pipeline

    super_called = AsyncMock()
    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_interruption",
        super_called,
        raising=False,
    )

    real_ringai_live._greeting_in_progress = True
    real_ringai_live._fn_in_progress = False

    await real_ringai_live._handle_interruption()
    super_called.assert_awaited_once()


async def test_function_call_window_still_suppresses_interruption(
    real_ringai_live, monkeypatch
):
    """Independent invariant — the OTHER suppression (function call) must still
    work. If a future refactor removes this guard, function calls will be
    cancelled by interruption and tool results will silently disappear."""
    import call_pipeline

    super_called = AsyncMock()
    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_interruption",
        super_called,
        raising=False,
    )

    real_ringai_live._fn_in_progress = True
    real_ringai_live._greeting_in_progress = False

    await real_ringai_live._handle_interruption()
    super_called.assert_not_awaited()


async def test_neither_flag_set_passes_through_normally(real_ringai_live, monkeypatch):
    import call_pipeline

    super_called = AsyncMock()
    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_interruption",
        super_called,
        raising=False,
    )

    real_ringai_live._fn_in_progress = False
    real_ringai_live._greeting_in_progress = False

    await real_ringai_live._handle_interruption()
    super_called.assert_awaited_once()


async def test_handle_interruption_resets_capture_flag(real_ringai_live, monkeypatch):
    """``_handle_interruption`` clears ``_last_captured_from_model_turn`` so the
    next message's output_transcription is captured cleanly."""
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_interruption",
        AsyncMock(),
        raising=False,
    )

    real_ringai_live._last_captured_from_model_turn = True
    await real_ringai_live._handle_interruption()
    assert real_ringai_live._last_captured_from_model_turn is False


# ---------------------------------------------------------------------------
# Source-level guard — quick grep that catches a careless reintroduction
# of the lock. This test fails if anyone wires _greeting_in_progress into
# the interruption path again.
# ---------------------------------------------------------------------------


def test_greeting_flag_is_not_referenced_in_handle_interruption_body():
    """Read the source of ``_handle_interruption`` and assert the lock phrase
    is not present. Defence in depth against the regression."""
    import inspect

    import call_pipeline

    src = inspect.getsource(call_pipeline.RingAIGeminiLive._handle_interruption)
    assert "_greeting_in_progress" not in src, (
        "VAD greeting lock has been re-introduced into _handle_interruption — "
        "this caused the original production bug where the assistant ignored "
        "users who spoke during the opening greeting."
    )


def test_run_function_call_sets_fn_in_progress_flag(real_ringai_live, monkeypatch):
    """``_run_function_call`` must set ``_fn_in_progress`` BEFORE the handler
    body runs, so a concurrent interruption broadcast doesn't cancel the call."""
    import asyncio
    import call_pipeline

    observed: list = []

    async def fake_super_run(self, tool_call, llm_context):
        observed.append(("during", self._fn_in_progress))

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_run_function_call",
        fake_super_run,
        raising=False,
    )

    asyncio.get_event_loop()

    async def run():
        await real_ringai_live._run_function_call(
            tool_call=object(), llm_context=object()
        )

    import asyncio as _asyncio

    _asyncio.get_event_loop().run_until_complete(run())

    assert observed == [("during", True)]
    # Flag is cleared after super returns.
    assert real_ringai_live._fn_in_progress is False


async def test_cancel_function_call_suppressed_when_fn_in_progress(
    real_ringai_live, monkeypatch
):
    """The second-line defence in ``_cancel_function_call`` must block cancels
    that arrive via the interruption broadcast path while the handler is live."""
    import call_pipeline

    super_cancel = AsyncMock()
    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_cancel_function_call",
        super_cancel,
        raising=False,
    )

    real_ringai_live._fn_in_progress = True
    await real_ringai_live._cancel_function_call("tc_123")
    super_cancel.assert_not_awaited()

    real_ringai_live._fn_in_progress = False
    await real_ringai_live._cancel_function_call("tc_124")
    super_cancel.assert_awaited_once()
