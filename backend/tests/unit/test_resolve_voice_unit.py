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
