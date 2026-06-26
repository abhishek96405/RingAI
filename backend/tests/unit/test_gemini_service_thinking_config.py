"""_thinking_config gates thinking_level on the model generation (3.x only)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_thinking_config_is_none_for_2x_models(monkeypatch):
    import gemini_service
    monkeypatch.setattr(gemini_service, "TEXT_MODEL", "gemini-2.5-flash")
    assert gemini_service._thinking_config("low") is None


def test_thinking_config_set_for_3x_models(monkeypatch):
    import gemini_service
    monkeypatch.setattr(gemini_service, "TEXT_MODEL", "gemini-3.1-flash-lite")
    cfg = gemini_service._thinking_config("minimal")
    assert cfg is not None
    # google-genai coerces the string into a ThinkingLevel enum (value "MINIMAL"),
    # so compare case-insensitively against the enum value or raw string.
    level = getattr(cfg, "thinking_level", None)
    assert str(getattr(level, "value", level)).lower() == "minimal"
