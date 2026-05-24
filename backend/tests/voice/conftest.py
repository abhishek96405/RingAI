"""
Voice-pipeline test fixtures for Duuutah AI.

Provides the shared scaffolding for ``backend/tests/voice/**``:

- ``frame_sink`` — a recording :class:`pipecat.processors.frame_processor.FrameProcessor`
  that captures every frame passed to it. Tests can use it to assert what
  emerged from a partial pipeline without spinning up a real Pipecat
  ``PipelineTask``.
- ``silent_1s_wav_bytes`` — a session-scoped 1-second silent 16 kHz mono
  PCM WAV byte blob. Use when a test needs "valid audio" without depending
  on the audio content.
- ``minimal_menu`` — three-item menu used by extraction tests.
- ``make_call_session`` — factory that returns a fully-formed
  :class:`call_pipeline.CallSession` with sensible defaults; tests override
  only what they care about.
- ``fake_gemini_live`` — drop-in replacement for ``RingAIGeminiLive`` that
  records system prompts, captured AI text, and queued realtime input,
  without ever opening a WebSocket. Mock at the class level via
  ``monkeypatch.setattr("call_pipeline.RingAIGeminiLive", FakeGeminiLive)``.
- ``transcript_fixtures_dir`` — path to ``backend/tests/fixtures/transcripts``;
  each JSON file there is a recorded transcript + the expected extracted
  order shape.
"""

from __future__ import annotations

import io
import json
import struct
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional
from unittest.mock import patch

import pytest

# Make backend/ importable regardless of where pytest was launched from.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ---------------------------------------------------------------------------
# Frame sink for partial-pipeline assertions.
# ---------------------------------------------------------------------------


@pytest.fixture
def frame_sink():
    """Return a lightweight frame recorder.

    Pipecat's real ``FrameProcessor`` requires a fully-initialised TaskManager
    to call ``super().process_frame``. For unit-level tests we don't need the
    framework wiring — we only need to capture what frames a producer would
    push downstream. This sink offers the same observable contract
    (``await sink.process_frame(frame, direction)`` records into ``sink.frames``)
    without inheriting from :class:`pipecat.processors.frame_processor.FrameProcessor`.
    """

    class RecordingSink:
        def __init__(self) -> None:
            self.frames: List[Any] = []

        async def process_frame(self, frame, direction=None):
            self.frames.append(frame)

    return RecordingSink()


# ---------------------------------------------------------------------------
# Silent 16 kHz mono PCM WAV fixture.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def silent_1s_wav_bytes() -> bytes:
    """1 second of silence, 16 kHz mono signed 16-bit PCM, in a valid WAV container."""
    sample_rate = 16000
    n_samples = sample_rate
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + n_samples * 2))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", n_samples * 2))
    buf.write(b"\x00\x00" * n_samples)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Menu + restaurant + config defaults used by CallSession tests.
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_menu() -> list[dict]:
    """Three-item menu sufficient for extraction + dispatch tests."""
    return [
        {
            "id": "m_pizza",
            "name": "Margherita Pizza",
            "category": "Pizza",
            "price": 1499,
            "available": True,
            "allergens": ["gluten", "dairy"],
        },
        {
            "id": "m_biryani",
            "name": "Chicken Biryani",
            "category": "Mains",
            "price": 1699,
            "available": True,
            "allergens": [],
        },
        {
            "id": "m_samosa",
            "name": "Samosa",
            "category": "Starters",
            "price": 399,
            "available": True,
            "allergens": ["gluten"],
        },
    ]


@pytest.fixture
def restaurant_doc() -> dict:
    """A minimal restaurant doc with enough fields for the pipeline to exercise."""
    return {
        "id": "rest_voice_test",
        "name": "Voice Test Kitchen",
        "business_type": "restaurant",
        "plan": "PRO",
        "phone": "+15555550100",
        "address": "1 Test Street, Austin, TX 78701",
        "timezone": "America/Chicago",
        "offers_delivery": True,
        "offers_reservations": True,
        "delivery_radius_miles": 5.0,
        "avg_prep_time_minutes": 20,
    }


@pytest.fixture
def restaurant_config() -> dict:
    """Per-restaurant config row. Overridable per-test."""
    return {
        "business_type": "restaurant",
        "delivery_minimum": 1500,
        "escalation_phone_number": "+15555550199",
    }


# ---------------------------------------------------------------------------
# CallSession factory.
# ---------------------------------------------------------------------------


@pytest.fixture
def make_call_session(minimal_menu, restaurant_doc, restaurant_config):
    """Return a factory that builds a fully-formed ``CallSession``.

    Defaults yield a restaurant session with PRO plan and three menu items;
    keyword overrides shadow any field. Example::

        sess = make_call_session(
            business_type="salon",
            services=[{"name": "Haircut", "price_cents": 4500}],
        )
    """
    import call_pipeline

    def _factory(
        *,
        call_sid: str = "test_call_001",
        restaurant_id: str = "rest_voice_test",
        caller_number: str = "+15555550199",
        restaurant: Optional[dict] = None,
        config: Optional[dict] = None,
        menu_items: Optional[list[dict]] = None,
        services: Optional[list[dict]] = None,
        lang: str = "en",
        business_type: Optional[str] = None,
    ) -> Any:
        rest = dict(restaurant or restaurant_doc)
        cfg = dict(config or restaurant_config)
        if business_type is not None:
            cfg["business_type"] = business_type
            rest["business_type"] = business_type
        sess = call_pipeline.CallSession(
            call_sid=call_sid,
            restaurant_id=restaurant_id,
            caller_number=caller_number,
            restaurant=rest,
            config=cfg,
            menu_items=menu_items if menu_items is not None else minimal_menu,
            services=services or [],
            lang=lang,
        )
        return sess

    return _factory


# ---------------------------------------------------------------------------
# RingAIGeminiLive stand-in.
# ---------------------------------------------------------------------------


class _FakeGeminiSession:
    """Stand-in for the ``_session`` attribute Pipecat sets after handshake."""

    def __init__(self) -> None:
        self.realtime_inputs: List[dict] = []

    async def send_realtime_input(self, **kwargs) -> None:
        self.realtime_inputs.append(kwargs)


class FakeGeminiLive:
    """Drop-in replacement for ``RingAIGeminiLive``.

    Records the constructor kwargs (system prompt, voice, tools, params),
    exposes the public hook ``_on_ai_transcript`` so tests can drive
    transcript emission, and provides a fake ``_session`` so the
    on_client_connected handler in ``create_call_pipeline`` finds it.
    """

    instances: List["FakeGeminiLive"] = []

    def __init__(self, on_ai_transcript=None, **kwargs):
        FakeGeminiLive.instances.append(self)
        self._on_ai_transcript = on_ai_transcript
        self.constructor_kwargs = dict(kwargs)
        self.system_prompt = kwargs.get("system_instruction", "")
        self.voice_id = kwargs.get("voice_id", "")
        self.tools = kwargs.get("tools")
        self._fn_in_progress = False
        self._greeting_in_progress = False
        self._ai_text_buffer: List[str] = []
        self._user_text_buffer: List[str] = []
        self._session = _FakeGeminiSession()
        self.registered_functions: dict = {}
        self.sent_text_messages: List[str] = []

    def register_function(self, name: str, handler) -> None:
        self.registered_functions[name] = handler

    async def send_text_message(self, text: str) -> None:
        self.sent_text_messages.append(text)

    async def _flush_ai_buffer(self) -> None:
        if self._ai_text_buffer and self._on_ai_transcript:
            full = "".join(self._ai_text_buffer).strip()
            self._ai_text_buffer.clear()
            if full:
                await self._on_ai_transcript(full)

    async def emit_ai_text(self, text: str) -> None:
        """Test helper — pretend the model produced ``text`` and flush."""
        if self._on_ai_transcript:
            await self._on_ai_transcript(text)


@pytest.fixture
def fake_gemini_live(monkeypatch):
    """Patch ``call_pipeline.RingAIGeminiLive`` with :class:`FakeGeminiLive`."""
    FakeGeminiLive.instances.clear()
    import call_pipeline

    monkeypatch.setattr(call_pipeline, "RingAIGeminiLive", FakeGeminiLive)
    yield FakeGeminiLive
    FakeGeminiLive.instances.clear()


@pytest.fixture
def real_ringai_live():
    """Construct a real ``RingAIGeminiLive`` with the Pipecat parent class no-op'd.

    Use this when a test exercises ``RingAIGeminiLive`` methods directly
    (capture buffers, interruption suppression, function-call guards) and
    needs the actual subclass under test.
    """
    import call_pipeline

    with patch.object(
        call_pipeline.GeminiLiveLLMService, "__init__", return_value=None
    ):
        live = call_pipeline.RingAIGeminiLive(
            api_key="fake",
            model="models/fake",
            system_instruction="test",
            voice_id="Leda",
        )
    return live


# ---------------------------------------------------------------------------
# External downstream patches — kitchen / SMS / extraction.
# These keep CallSession tests hermetic without per-test boilerplate.
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_kitchen_dispatch(monkeypatch):
    """Make ``send_order_to_kitchen`` return a deterministic success.

    Tests can inspect the captured payloads via the returned ``calls`` list.
    Reassign the function on the returned ``calls`` dict to inject failures
    or alternate behavior.
    """
    calls: dict = {
        "sends": [],
        "result": {"success": True, "order_id": "DTH-TEST", "method": "database"},
    }

    async def _fake_send(order, restaurant):
        calls["sends"].append({"order": order, "restaurant": restaurant})
        return dict(calls["result"])

    import call_pipeline

    monkeypatch.setattr(
        call_pipeline, "send_order_to_kitchen", _fake_send, raising=True
    )
    return calls


@pytest.fixture
def stub_order_extraction(monkeypatch):
    """Patch ``extract_order_from_transcript`` to a controllable stub."""
    state: dict = {"return_value": None, "calls": []}

    async def _fake_extract(transcript, menu_index, detected_order_type=None):
        state["calls"].append(
            {"transcript": transcript, "detected_order_type": detected_order_type}
        )
        _fake_extract._last_tokens = 0
        return state["return_value"]

    _fake_extract._last_tokens = 0
    import call_pipeline

    monkeypatch.setattr(
        call_pipeline, "extract_order_from_transcript", _fake_extract, raising=True
    )
    return state


@pytest.fixture
def stub_send_sms(monkeypatch):
    """Stub ``telnyx_service.send_sms`` so SMS-triggering code paths are exercisable."""
    calls: list = []

    async def _fake_send_sms(**kw):
        calls.append(kw)

        class _R:
            success = True
            message_id = "msg_test"
            error_code = None
            error_message = None

        return _R()

    import telnyx_service

    monkeypatch.setattr(telnyx_service, "send_sms", _fake_send_sms, raising=False)
    return calls


@pytest.fixture
def stub_appointment_dispatch(monkeypatch):
    """Patch appointment-service helpers for non-restaurant business tests."""
    state: dict = {
        "extracted": None,
        "dispatch_result": {
            "success": True,
            "calendar_event_id": "evt_test",
            "sms_sent": True,
        },
        "extract_calls": [],
        "dispatch_calls": [],
    }

    async def _fake_extract(transcript, services):
        state["extract_calls"].append({"transcript": transcript, "services": services})
        _fake_extract._last_tokens = 0
        return state["extracted"]

    async def _fake_dispatch(booking, restaurant, config, services, db=None):
        state["dispatch_calls"].append(
            {"booking": booking, "restaurant": restaurant, "services": services}
        )
        return dict(state["dispatch_result"])

    _fake_extract._last_tokens = 0

    import call_pipeline

    monkeypatch.setattr(
        call_pipeline, "extract_booking_from_transcript", _fake_extract, raising=True
    )
    monkeypatch.setattr(
        call_pipeline, "dispatch_appointment", _fake_dispatch, raising=True
    )
    return state


# ---------------------------------------------------------------------------
# Transcript fixtures (JSON files under backend/tests/fixtures/transcripts/).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def transcript_fixtures_dir() -> Path:
    """Path to the directory holding transcript JSON fixtures.

    Each ``*.json`` file has the shape::

        {
          "name": "single_item_pickup",
          "transcript": [{"role": "customer"|"ai", "text": "..."}, ...],
          "expected": { ... assertion hints ... }
        }
    """
    return Path(__file__).resolve().parents[1] / "fixtures" / "transcripts"


def _load_transcript_fixture(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def all_transcript_fixtures(transcript_fixtures_dir) -> list[dict]:
    """All transcript JSON fixtures preloaded into memory."""
    return [
        _load_transcript_fixture(p)
        for p in sorted(transcript_fixtures_dir.glob("*.json"))
    ]


def transcript_fixture_ids(fixtures: Iterable[dict]) -> list[str]:
    """pytest id helper — use the ``name`` field of each fixture."""
    return [f["name"] for f in fixtures]
