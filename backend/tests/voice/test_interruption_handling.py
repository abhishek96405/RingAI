"""
Tests for VAD-driven interruption suppression and pass-through.

Most of the suppression logic lives in :meth:`RingAIGeminiLive._handle_interruption`,
which is regression-tested in ``test_vad_no_greeting_lock_regression.py``.
This file covers the *other* observable consequences of an interruption:
buffer state, capture-flag reset, and the function-call lifecycle guards.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Capture-flag reset across interruption.
# ---------------------------------------------------------------------------


async def test_interruption_resets_model_turn_capture_flag(
    real_ringai_live, monkeypatch
):
    """If model_turn captured text in the current frame, the dedup flag is True.
    An interruption invalidates the in-flight frame, so the flag must reset."""
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


async def test_interruption_does_not_drain_existing_buffer(
    real_ringai_live, monkeypatch
):
    """Production code does not clear the AI text buffer on interruption — the
    next turn_complete will flush whatever was captured. Pin this behavior so
    a future change to drain-on-interrupt is a conscious decision."""
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_interruption",
        AsyncMock(),
        raising=False,
    )

    real_ringai_live._ai_text_buffer = ["partial output "]
    await real_ringai_live._handle_interruption()
    assert real_ringai_live._ai_text_buffer == ["partial output "]


# ---------------------------------------------------------------------------
# Function-call lifecycle — _fn_in_progress must flip to True for the
# duration of a tool call and reset on completion (whether success or error).
# ---------------------------------------------------------------------------


async def test_run_function_call_sets_then_clears_fn_flag_on_success(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    observed_during: list = []

    async def fake_super_run(self, tool_call, llm_context):
        observed_during.append(self._fn_in_progress)

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_run_function_call",
        fake_super_run,
        raising=False,
    )

    await real_ringai_live._run_function_call(tool_call=object(), llm_context=object())
    assert observed_during == [True]
    assert real_ringai_live._fn_in_progress is False


async def test_run_function_call_clears_fn_flag_on_exception(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    async def boom(self, tool_call, llm_context):
        raise RuntimeError("simulated handler crash")

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_run_function_call",
        boom,
        raising=False,
    )

    with pytest.raises(RuntimeError):
        await real_ringai_live._run_function_call(
            tool_call=object(), llm_context=object()
        )
    # Critical: flag must reset even when the handler raised, otherwise
    # the session is permanently stuck refusing interruptions.
    assert real_ringai_live._fn_in_progress is False


# ---------------------------------------------------------------------------
# Cancel suppression — the second-line defense.
# ---------------------------------------------------------------------------


async def test_cancel_function_call_passes_through_when_idle(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    super_cancel = AsyncMock()
    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_cancel_function_call",
        super_cancel,
        raising=False,
    )
    real_ringai_live._fn_in_progress = False
    await real_ringai_live._cancel_function_call("tc_001")
    super_cancel.assert_awaited_once_with("tc_001")


async def test_cancel_function_call_suppressed_during_active_call(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    super_cancel = AsyncMock()
    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_cancel_function_call",
        super_cancel,
        raising=False,
    )
    real_ringai_live._fn_in_progress = True
    await real_ringai_live._cancel_function_call("tc_002")
    super_cancel.assert_not_awaited()
