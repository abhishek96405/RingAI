"""
Unit tests for the ambient-noise mixer helper in backend/call_pipeline.py.

The helper is `_build_ambient_mixer()` — it constructs a Pipecat SoundfileMixer
for the cafe ambience asset, gracefully degrading to None when:
  - AMBIENT_NOISE_ENABLED env var is "false"
  - The soundfile package is unavailable (SoundfileMixer import failed)
  - The asset WAV file is missing
  - Any other exception is raised during construction

These tests verify each gating branch returns None without raising, and that
the happy path returns a real SoundfileMixer instance.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_mixer_disabled_when_env_var_false(monkeypatch):
    """AMBIENT_NOISE_ENABLED=false short-circuits before any construction."""
    import call_pipeline

    monkeypatch.setenv("AMBIENT_NOISE_ENABLED", "false")

    result = call_pipeline._build_ambient_mixer()

    assert result is None


def test_mixer_disabled_when_file_missing(monkeypatch):
    """Missing asset file degrades to None without raising."""
    import call_pipeline

    monkeypatch.setenv("AMBIENT_NOISE_ENABLED", "true")
    # Force the asset-exists check to fail regardless of real filesystem state.
    monkeypatch.setattr(Path, "exists", lambda self: False)

    result = call_pipeline._build_ambient_mixer()

    assert result is None


def test_mixer_disabled_when_soundfile_unavailable(monkeypatch):
    """When the SoundfileMixer import failed at module load, return None."""
    import call_pipeline

    monkeypatch.setenv("AMBIENT_NOISE_ENABLED", "true")
    monkeypatch.setattr(call_pipeline, "_SOUNDFILE_MIXER_AVAILABLE", False)

    result = call_pipeline._build_ambient_mixer()

    assert result is None


def test_mixer_initialized_when_all_conditions_met(monkeypatch):
    """With default env, real asset, and real package, return a SoundfileMixer."""
    import call_pipeline

    if not call_pipeline._SOUNDFILE_MIXER_AVAILABLE:
        pytest.skip("SoundfileMixer not importable in this environment")

    asset_path = Path(call_pipeline.__file__).parent / "assets" / "cafe_ambience_8k_mono.wav"
    if not asset_path.exists():
        pytest.skip(f"ambient asset not present at {asset_path}")

    monkeypatch.delenv("AMBIENT_NOISE_ENABLED", raising=False)

    result = call_pipeline._build_ambient_mixer()

    assert result is not None
    from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
    assert isinstance(result, SoundfileMixer)
