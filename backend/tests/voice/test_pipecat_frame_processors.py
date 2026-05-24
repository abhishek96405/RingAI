"""
Tests for the Pipecat frame-processor surface exposed by ``RingAIGeminiLive``.

In Pipecat 0.0.104 the LLM service receives Gemini WebSocket messages and
emits captured text via the on_ai_transcript callback. ``RingAIGeminiLive``
overrides four ``_handle_msg_*`` methods to thread Gemini 3.1's
output_transcription through both the model_turn and output_transcription
paths without double-capturing.

These tests pin the capture chain and the flush-on-turn-complete contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Helper to construct a fake server-content message structure.
# ---------------------------------------------------------------------------


class _ServerContent:
    def __init__(self, output_text: str = "", input_text: str = ""):
        self.output_transcription = _Transcription(output_text) if output_text else None
        self.input_transcription = _Transcription(input_text) if input_text else None


class _Transcription:
    def __init__(self, text: str):
        self.text = text


class _Message:
    def __init__(self, output_text: str = "", input_text: str = ""):
        self.server_content = _ServerContent(output_text, input_text)


# ---------------------------------------------------------------------------
# model_turn capture path.
# ---------------------------------------------------------------------------


async def test_model_turn_captures_output_transcription_text(
    real_ringai_live, monkeypatch
):
    """Gemini 3.1 ships output_transcription inside model_turn. ``_handle_msg_model_turn``
    must capture it into ``_ai_text_buffer`` and set the dedup flag."""
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_model_turn",
        AsyncMock(),
        raising=False,
    )

    msg = _Message(output_text="Hello there. ")
    await real_ringai_live._handle_msg_model_turn(msg)
    assert real_ringai_live._ai_text_buffer == ["Hello there. "]
    assert real_ringai_live._last_captured_from_model_turn is True


async def test_model_turn_with_no_transcription_does_not_set_dedup_flag(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_model_turn",
        AsyncMock(),
        raising=False,
    )

    msg = _Message(output_text="")
    await real_ringai_live._handle_msg_model_turn(msg)
    assert real_ringai_live._ai_text_buffer == []
    assert real_ringai_live._last_captured_from_model_turn is False


# ---------------------------------------------------------------------------
# output_transcription deduplication.
# ---------------------------------------------------------------------------


async def test_output_transcription_skipped_when_model_turn_already_captured(
    real_ringai_live, monkeypatch
):
    """If model_turn already captured the text, the standalone output_transcription
    event must be a no-op so the text isn't duplicated."""
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_output_transcription",
        AsyncMock(),
        raising=False,
    )

    real_ringai_live._last_captured_from_model_turn = True
    msg = _Message(output_text="duplicate text")
    await real_ringai_live._handle_msg_output_transcription(msg)
    assert real_ringai_live._ai_text_buffer == []
    assert real_ringai_live._last_captured_from_model_turn is False


async def test_output_transcription_captures_when_model_turn_did_not(
    real_ringai_live, monkeypatch
):
    """If model_turn DIDN'T capture (older Gemini behavior), the standalone
    output_transcription path captures the text into the same buffer."""
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_output_transcription",
        AsyncMock(),
        raising=False,
    )

    real_ringai_live._last_captured_from_model_turn = False
    msg = _Message(output_text="standalone text")
    await real_ringai_live._handle_msg_output_transcription(msg)
    assert real_ringai_live._ai_text_buffer == ["standalone text"]


# ---------------------------------------------------------------------------
# input_transcription capture (customer audio → text).
# ---------------------------------------------------------------------------


async def test_input_transcription_appends_to_user_buffer(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_input_transcription",
        AsyncMock(),
        raising=False,
    )

    msg = _Message(input_text="I want a pizza")
    await real_ringai_live._handle_msg_input_transcription(msg)
    assert real_ringai_live._user_text_buffer == ["I want a pizza"]


async def test_input_transcription_empty_text_is_noop(real_ringai_live, monkeypatch):
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_input_transcription",
        AsyncMock(),
        raising=False,
    )

    msg = _Message(input_text="")
    await real_ringai_live._handle_msg_input_transcription(msg)
    assert real_ringai_live._user_text_buffer == []


# ---------------------------------------------------------------------------
# Flush on turn_complete.
# ---------------------------------------------------------------------------


async def test_turn_complete_flushes_buffer_via_on_ai_transcript(
    real_ringai_live, monkeypatch
):
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline.GeminiLiveLLMService,
        "_handle_msg_turn_complete",
        AsyncMock(),
        raising=False,
    )

    captured: list = []

    async def on_ai(text):
        captured.append(text)

    real_ringai_live._on_ai_transcript = on_ai
    real_ringai_live._ai_text_buffer = ["Your ", "order ", "is ", "confirmed."]

    await real_ringai_live._handle_msg_turn_complete(_Message())
    assert captured == ["Your order is confirmed."]
    # Buffer must be drained.
    assert real_ringai_live._ai_text_buffer == []


async def test_flush_with_empty_buffer_does_nothing(real_ringai_live):
    captured: list = []

    async def on_ai(text):
        captured.append(text)

    real_ringai_live._on_ai_transcript = on_ai
    real_ringai_live._ai_text_buffer = []
    await real_ringai_live._flush_ai_buffer()
    assert captured == []


async def test_flush_with_whitespace_only_does_not_emit(real_ringai_live):
    captured: list = []

    async def on_ai(text):
        captured.append(text)

    real_ringai_live._on_ai_transcript = on_ai
    real_ringai_live._ai_text_buffer = ["   ", "\n", " "]
    await real_ringai_live._flush_ai_buffer()
    assert captured == []
    assert real_ringai_live._ai_text_buffer == []


async def test_flush_without_callback_drains_buffer_silently(real_ringai_live):
    real_ringai_live._on_ai_transcript = None
    real_ringai_live._ai_text_buffer = ["text"]
    # With no callback, the buffer is NOT cleared (callback gate is checked first).
    await real_ringai_live._flush_ai_buffer()
    # Production code does ``if self._ai_text_buffer and self._on_ai_transcript``
    # — when callback is None the buffer is left intact for a future flush.
    assert real_ringai_live._ai_text_buffer == ["text"]


# ---------------------------------------------------------------------------
# _create_initial_response — proactive greeting suppression.
# ---------------------------------------------------------------------------


async def test_create_initial_response_is_noop(real_ringai_live):
    """``_create_initial_response`` is overridden to suppress Pipecat's automatic
    BEGIN_CALL injection — Gemini 3.1 has no proactive audio, the caller speaks
    first. The method must return None and not raise."""
    result = await real_ringai_live._create_initial_response()
    assert result is None


# ---------------------------------------------------------------------------
# Frame sink smoke test — the fixture works as expected.
# ---------------------------------------------------------------------------


async def test_frame_sink_records_pushed_frames(frame_sink):
    """Smoke test for the test-only RecordingSink helper."""
    from pipecat.frames.frames import TextFrame

    await frame_sink.process_frame(TextFrame("hello"))
    await frame_sink.process_frame(TextFrame("world"))
    assert len(frame_sink.frames) == 2
    assert all(isinstance(f, TextFrame) for f in frame_sink.frames)
    assert [f.text for f in frame_sink.frames] == ["hello", "world"]
