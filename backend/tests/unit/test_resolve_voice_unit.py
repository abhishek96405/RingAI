import pytest
from call_pipeline import _resolve_voice

pytestmark = [pytest.mark.unit]


class _FakeSession:
    def __init__(self, config):
        self.config = config


def test_explicit_voice_wins(monkeypatch):
    monkeypatch.setenv("GEMINI_VOICE", "Puck")
    assert _resolve_voice("Aoede", _FakeSession({"voice_id": "Kore"})) == "Aoede"


def test_config_voice_used_when_no_explicit(monkeypatch):
    # The actual A8-6 fix: per-restaurant config beats the env voice.
    monkeypatch.setenv("GEMINI_VOICE", "Puck")
    assert _resolve_voice(None, _FakeSession({"voice_id": "Kore"})) == "Kore"


def test_env_fallback_when_no_config_voice(monkeypatch):
    monkeypatch.setenv("GEMINI_VOICE", "Aoede")
    assert _resolve_voice(None, _FakeSession({})) == "Aoede"
    assert _resolve_voice(None, None) == "Aoede"


def test_default_when_no_env(monkeypatch):
    monkeypatch.delenv("GEMINI_VOICE", raising=False)
    assert _resolve_voice(None, _FakeSession({})) == "Leda"


def test_resolve_voice_rejects_stale_elevenlabs_id(monkeypatch):
    """A stale ElevenLabs voice_id must NOT reach Gemini Live (it 1011s the
    session → silent call) — _resolve_voice falls back to the default."""
    import call_pipeline
    monkeypatch.delenv("GEMINI_VOICE", raising=False)

    class _S:
        config = {"voice_id": "21m00Tcm4TlvDq8ikWAM"}  # ElevenLabs "Rachel"

    assert call_pipeline._resolve_voice(None, _S()) == "Leda"


def test_resolve_voice_accepts_valid_gemini_voice(monkeypatch):
    import call_pipeline
    monkeypatch.delenv("GEMINI_VOICE", raising=False)

    class _S:
        config = {"voice_id": "Kore"}

    assert call_pipeline._resolve_voice(None, _S()) == "Kore"


def test_resolve_voice_default_when_unset_or_invalid(monkeypatch):
    import call_pipeline
    monkeypatch.delenv("GEMINI_VOICE", raising=False)

    class _Empty:
        config = {}

    assert call_pipeline._resolve_voice(None, _Empty()) == "Leda"
    assert call_pipeline._resolve_voice(None, None) == "Leda"
    assert call_pipeline._resolve_voice("not-a-voice", None) == "Leda"
