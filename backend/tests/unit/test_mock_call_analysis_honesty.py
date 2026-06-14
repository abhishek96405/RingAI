import pytest
import gemini_service

pytestmark = [pytest.mark.unit]


def test_mock_call_analysis_is_honest():
    out = gemini_service._mock_call_analysis([{"role": "ai", "text": "hi"}], None)
    assert out["quality_score"] is None
    assert out["analysis_available"] is False
    assert out["issues"] == []
    assert out["highlights"] == []
    assert "unavailable" in out["summary"].lower()


async def test_analyse_falls_back_honestly_without_client(monkeypatch):
    # No Gemini client → must return the honest marker, never a fabricated score.
    monkeypatch.setattr(gemini_service, "_get_client", lambda: None)
    out = await gemini_service.analyse_call_transcript(
        [{"role": "customer", "text": "hi"}], None, None
    )
    assert out["quality_score"] is None
    assert out["analysis_available"] is False
