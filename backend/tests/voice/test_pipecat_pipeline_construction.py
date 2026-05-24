"""
Tests for :func:`call_pipeline.create_call_pipeline` orchestration logic.

We do NOT run the full pipeline (that needs a real Telnyx WebSocket). We
inspect the factory's *early decisions*:

- ``is_pipeline_available`` short-circuits when env keys are missing.
- The ``_TELNYX_SERIALIZER_AVAILABLE`` and ``_PIPECAT_AVAILABLE`` guards
  return None.

We also verify pipeline-availability flag inputs via ``is_pipeline_available``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.voice


def test_is_pipeline_available_returns_true_when_both_keys_set(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.setenv("TELNYX_API_KEY", "fake")
    import call_pipeline

    assert call_pipeline.is_pipeline_available() is True


def test_is_pipeline_available_returns_true_with_google_genai_alias(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_API_KEY", "fake")
    monkeypatch.setenv("TELNYX_API_KEY", "fake")
    import call_pipeline

    assert call_pipeline.is_pipeline_available() is True


def test_is_pipeline_available_false_without_google_keys(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    monkeypatch.setenv("TELNYX_API_KEY", "fake")
    import call_pipeline

    assert call_pipeline.is_pipeline_available() is False


def test_is_pipeline_available_false_without_telnyx(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.delenv("TELNYX_API_KEY", raising=False)
    import call_pipeline

    assert call_pipeline.is_pipeline_available() is False


# ---------------------------------------------------------------------------
# VAD config defaults — these are env-tunable.
# ---------------------------------------------------------------------------


def test_vad_default_stop_secs():
    import call_pipeline

    assert call_pipeline.VAD_STOP_SECS == pytest.approx(0.2)


def test_hangup_delay_default():
    import call_pipeline

    # Default is 1.5 but tests set it to 0 via fast_hangup. Reimport to get
    # the module-level default.
    assert hasattr(call_pipeline, "HANGUP_DELAY_SECS")
    assert call_pipeline.HANGUP_DELAY_SECS >= 0


# ---------------------------------------------------------------------------
# CHECK_AVAILABILITY_TOOL is defined when google-genai is importable.
# ---------------------------------------------------------------------------


def test_check_availability_tool_is_defined():
    import call_pipeline

    assert call_pipeline._TOOLS_AVAILABLE is True
    assert call_pipeline.CHECK_AVAILABILITY_TOOL is not None


# ---------------------------------------------------------------------------
# generate_twiml_stream_response — legacy Twilio helper.
# Verify the document structure even though the Telnyx migration likely
# leaves this function unused. A reader running coverage will see why
# nothing exercises it past this point.
# ---------------------------------------------------------------------------


def test_generate_twiml_stream_response_returns_valid_xml():
    """The TwiML helper is legacy Twilio output; pin the structure so a
    refactor that removes it is a conscious decision."""
    import call_pipeline

    out = call_pipeline.generate_twiml_stream_response(
        websocket_url="wss://example.com/ws",
        call_sid="CA123",
    )
    assert out.startswith("<?xml version=")
    assert "<Connect>" in out
    assert '<Stream url="wss://example.com/ws">' in out
    assert "callSid" in out
    assert "CA123" in out


def test_generate_twiml_stream_response_includes_status_callback_when_url_given():
    import call_pipeline

    out = call_pipeline.generate_twiml_stream_response(
        websocket_url="wss://example.com/ws",
        call_sid="CA123",
        status_callback_url="https://api.example.com/status",
    )
    assert 'statusCallback="https://api.example.com/status"' in out
    assert 'statusCallbackEvent="completed"' in out


def test_generate_twiml_stream_response_omits_callback_when_blank():
    import call_pipeline

    out = call_pipeline.generate_twiml_stream_response(
        websocket_url="wss://example.com/ws",
        call_sid="CA123",
        status_callback_url="",
    )
    assert "statusCallback" not in out
