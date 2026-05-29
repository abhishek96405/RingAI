"""
Orchestration-level tests for :func:`create_call_pipeline`.

We replace every Pipecat construction primitive with a record-keeping fake
so the factory can be driven all the way to ``runner.run(task)`` without
opening sockets. The goal is to cover the inner closures
(``on_ai_transcript``, ``_handle_check_availability``,
``_classifier_availability_check``, ``handle_user_idle``,
``on_client_connected``, ``on_client_disconnected``) so the source-level
guards already pinned by the regression tests are also exercised at runtime.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Heavy-mock fixture — replaces every Pipecat surface that ``create_call_pipeline``
# touches with a controllable stub.
# ---------------------------------------------------------------------------


@pytest.fixture
def pipecat_mocks(monkeypatch):
    """Patch Pipecat primitives so create_call_pipeline can run to completion."""
    state: dict = {
        "transport": None,
        "task": None,
        "runner": None,
        "pipeline_processors": None,
        "event_handlers": {},
        "task_frames": [],
    }

    class FakeTransport:
        def __init__(self, websocket=None, params=None):
            self._handlers: dict = {}
            state["transport"] = self

        def input(self):
            return MagicMock(name="transport_input")

        def output(self):
            return MagicMock(name="transport_output")

        def event_handler(self, name):
            def deco(fn):
                self._handlers[name] = fn
                state["event_handlers"][name] = fn
                return fn

            return deco

    class FakeSerializer:
        class InputParams:
            def __init__(self, **kw):
                self.kwargs = kw

        def __init__(self, **kw):
            self.kwargs = kw

    class FakePipeline:
        def __init__(self, processors):
            state["pipeline_processors"] = processors
            self.processors = processors

    class FakeTask:
        def __init__(self, pipeline, enable_rtvi=None, params=None):
            state["task"] = self
            self.pipeline = pipeline
            self.params = params
            self.queued: list = []
            self.cancel = AsyncMock()

        async def queue_frame(self, frame):
            self.queued.append(frame)
            state["task_frames"].append(frame)

    class FakeRunner:
        def __init__(self, *a, **kw):
            state["runner"] = self

        async def run(self, task):
            # Just return — we don't actually drive frames.
            return None

    class FakeAggregator:
        def __init__(self):
            self.handlers: dict = {}

        def event_handler(self, name):
            def deco(fn):
                self.handlers[name] = fn
                state["event_handlers"][name] = fn
                return fn

            return deco

    class FakeAggregatorPair:
        def __init__(self, *a, **kw):
            self._u = FakeAggregator()
            self._a = FakeAggregator()

        def user(self):
            return self._u

        def assistant(self):
            return self._a

    class FakeIdleProcessor:
        def __init__(self, callback=None, timeout=None):
            self._callback = callback
            self.timeout = timeout

        def _wrap_callback(self, fn):
            return fn

    import call_pipeline

    monkeypatch.setattr(call_pipeline, "FastAPIWebsocketTransport", FakeTransport)
    monkeypatch.setattr(call_pipeline, "FastAPIWebsocketParams", lambda **kw: kw)
    monkeypatch.setattr(call_pipeline, "TelnyxFrameSerializer", FakeSerializer)
    monkeypatch.setattr(call_pipeline, "Pipeline", FakePipeline)
    monkeypatch.setattr(call_pipeline, "PipelineTask", FakeTask)
    monkeypatch.setattr(call_pipeline, "PipelineRunner", FakeRunner)
    monkeypatch.setattr(call_pipeline, "PipelineParams", lambda **kw: kw)
    monkeypatch.setattr(call_pipeline, "LLMContext", MagicMock())
    monkeypatch.setattr(call_pipeline, "LLMContextAggregatorPair", FakeAggregatorPair)

    # UserIdleProcessor is imported inside the function body; we need to make
    # the import return our fake.
    import sys
    import types

    fake_uip_module = types.ModuleType("pipecat.processors.user_idle_processor")
    fake_uip_module.UserIdleProcessor = FakeIdleProcessor
    monkeypatch.setitem(
        sys.modules, "pipecat.processors.user_idle_processor", fake_uip_module
    )

    # SpeechTimeoutUserTurnStopStrategy etc. — these are imported inside the
    # function. Provide stub modules so the imports succeed.
    for mod_name, attrs in [
        ("pipecat.turns.user_stop", {"SpeechTimeoutUserTurnStopStrategy": MagicMock}),
        ("pipecat.turns.user_turn_strategies", {"UserTurnStrategies": MagicMock}),
    ]:
        mod = types.ModuleType(mod_name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, mod_name, mod)

    # The function also imports from a nested pipecat path — provide it.
    nested_path = "pipecat.services.google.gemini_live.llm"
    nested_mod = types.ModuleType(nested_path)
    nested_mod.GeminiVADParams = MagicMock
    nested_mod.EndSensitivity = MagicMock(END_SENSITIVITY_HIGH=1)
    nested_mod.StartSensitivity = MagicMock(START_SENSITIVITY_HIGH=1)
    nested_mod.InputParams = MagicMock
    monkeypatch.setitem(sys.modules, nested_path, nested_mod)

    google_types = types.ModuleType("google.genai.types")
    google_types.ThinkingConfig = MagicMock
    monkeypatch.setitem(sys.modules, "google.genai.types", google_types)

    return state


# ---------------------------------------------------------------------------
# End-to-end factory runs.
# ---------------------------------------------------------------------------


async def test_create_call_pipeline_runs_for_restaurant_session(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    sess = make_call_session()
    task = await call_pipeline.create_call_pipeline(
        websocket=MagicMock(name="ws"),
        system_prompt="You are a helpful AI",
        restaurant_id="rest_voice_test",
        call_sid="cs_test",
        stream_sid="stream_test",
        session=sess,
    )
    assert task is pipecat_mocks["task"]
    # Pipeline was built with 6 processors.
    assert len(pipecat_mocks["pipeline_processors"]) == 6
    assert sess._pipeline_task is task


async def test_create_call_pipeline_passes_no_tools_for_restaurant(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    sess = make_call_session(business_type="restaurant")
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    # The fake GeminiLive instance was constructed with tools=None for restaurant.
    inst = fake_gemini_live.instances[0]
    assert inst.tools is None


async def test_create_call_pipeline_passes_tools_for_salon(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    sess = make_call_session(
        business_type="salon", services=[{"name": "Haircut", "price_cents": 4500}]
    )
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    assert inst.tools is not None
    assert "register_function" not in inst.tools  # tools list, not method name


async def test_on_ai_transcript_appointment_signal_for_salon(
    pipecat_mocks, fake_gemini_live, make_call_session, stub_appointment_dispatch
):
    """When the AI says "your appointment is confirmed" in a salon session,
    APPOINTMENT_CONFIRMED routes through _handle_appointment_confirmed."""
    import call_pipeline

    stub_appointment_dispatch["extracted"] = {
        "customer_name": "Jane",
        "service_name": "Haircut",
        "date": "2026-05-30",
    }

    sess = make_call_session(
        business_type="salon",
        services=[{"name": "Haircut", "price_cents": 4500}],
    )
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    # Drive the on_ai_transcript closure.
    sess._pipeline_task = pipecat_mocks["task"]
    await inst.emit_ai_text("Your appointment is confirmed for tomorrow at 3pm.")
    # Let the spawned task run.
    for _ in range(5):
        await asyncio.sleep(0)
    # Appointment dispatch was called.
    assert len(stub_appointment_dispatch["dispatch_calls"]) == 1


async def test_on_ai_transcript_reservation_signal_for_restaurant(
    pipecat_mocks, fake_gemini_live, make_call_session, monkeypatch
):
    import sys
    import types

    import call_pipeline

    fake_module = types.ModuleType("reservation_service")

    async def fake_extract(transcript, menu_index=None):
        return {"party_size": 4, "date": "2026-05-30", "time": "19:00"}

    async def fake_dispatch(**kw):
        return {"success": True, "reservation_id": "rsv_456"}

    fake_module.extract_reservation_from_transcript = fake_extract
    fake_module.dispatch_reservation = fake_dispatch
    monkeypatch.setitem(sys.modules, "reservation_service", fake_module)
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)

    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr("call_pipeline.asyncio.sleep", fast_sleep)

    sess = make_call_session(business_type="restaurant")
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    sess._pipeline_task = pipecat_mocks["task"]
    sess._pipeline_task.cancel = AsyncMock()
    await inst.emit_ai_text("Your reservation is confirmed.")
    # Allow the spawned reservation task to progress.
    for _ in range(20):
        await asyncio.sleep(0)
    assert sess._reservation_dispatched is True


async def test_on_ai_transcript_skips_system_frames(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """SYSTEM: prefixed text is internal — must not be appended to the
    transcript."""
    import call_pipeline

    sess = make_call_session()
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    await inst.emit_ai_text("SYSTEM: directive")
    assert sess.transcript == []


async def test_on_ai_transcript_call_end_starts_farewell_timer(
    pipecat_mocks, fake_gemini_live, make_call_session, monkeypatch
):
    """For non-restaurant tenants, farewell phrases start a 30-second silence
    timer that ends the call if the customer doesn't say anything more."""
    import call_pipeline

    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)

    sess = make_call_session(
        business_type="salon", services=[{"name": "Haircut", "price_cents": 4500}]
    )
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    sess._pipeline_task = pipecat_mocks["task"]
    sess._pipeline_task.cancel = AsyncMock()
    await inst.emit_ai_text("Have a great day!")
    # Timer was created.
    assert hasattr(sess, "_farewell_timer")
    assert sess._farewell_timer is not None
    # Cancel the timer to avoid lingering background tasks.
    sess._farewell_timer.cancel()
    try:
        await sess._farewell_timer
    except (asyncio.CancelledError, Exception):
        pass


async def test_create_call_pipeline_assigns_on_call_complete(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    sess = make_call_session()
    on_complete = AsyncMock()
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
        on_call_complete=on_complete,
    )
    assert sess._on_call_complete is on_complete


async def test_create_call_pipeline_registers_check_availability_for_salon(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """When the business is salon/clinic/legal/home_services, the native
    check_availability tool handler must be registered on the LLM service."""
    import call_pipeline

    sess = make_call_session(
        business_type="clinic", services=[{"name": "Consultation", "price_cents": 5000}]
    )
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    assert "check_availability" in inst.registered_functions


# ---------------------------------------------------------------------------
# Drive the registered check_availability handler + the disconnect handler
# to cover the remaining body lines.
# ---------------------------------------------------------------------------


async def test_check_availability_handler_calls_appointment_service(
    pipecat_mocks, fake_gemini_live, make_call_session, monkeypatch
):
    import call_pipeline

    sess = make_call_session(
        business_type="salon", services=[{"name": "Haircut", "price_cents": 4500}]
    )
    fake_slots = [
        {"available": True, "display_time": "10:00 AM"},
        {"available": True, "display_time": "11:30 AM"},
        {"available": False, "display_time": "1:00 PM"},
    ]

    async def fake_get_slots(**kw):
        return fake_slots

    import appointment_service

    monkeypatch.setattr(appointment_service, "get_available_slots", fake_get_slots)

    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["check_availability"]

    captured_results: list = []

    class FakeParams:
        arguments = {"date": "2026-05-30", "service_name": "Haircut"}
        tool_call_id = "tc_test"

        async def result_callback(self, result):
            captured_results.append(result)

    await handler(FakeParams())
    assert len(captured_results) == 1
    assert captured_results[0]["available"] is True
    assert "10:00 AM" in captured_results[0]["slots"]


async def test_check_availability_handler_rejects_missing_date(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    sess = make_call_session(
        business_type="salon", services=[{"name": "Haircut", "price_cents": 4500}]
    )
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["check_availability"]

    captured: list = []

    class FakeParams:
        arguments = {"date": "", "service_name": ""}
        tool_call_id = "tc_x"

        async def result_callback(self, result):
            captured.append(result)

    await handler(FakeParams())
    assert captured == [{"error": "date is required"}]


async def test_check_availability_handler_swallows_exceptions(
    pipecat_mocks, fake_gemini_live, make_call_session, monkeypatch
):
    """If the appointment service raises, the handler returns a generic error
    string to the LLM rather than crashing the pipeline."""
    import call_pipeline

    sess = make_call_session(
        business_type="salon", services=[{"name": "Haircut", "price_cents": 4500}]
    )

    async def boom(**kw):
        raise RuntimeError("appointment service down")

    import appointment_service

    monkeypatch.setattr(appointment_service, "get_available_slots", boom)

    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["check_availability"]

    captured: list = []

    class FakeParams:
        arguments = {"date": "2026-05-30", "service_name": "Haircut"}
        tool_call_id = "tc_err"

        async def result_callback(self, result):
            captured.append(result)

    await handler(FakeParams())
    assert captured[0]["error"].startswith("Could not check")


async def test_disconnect_handler_invokes_on_call_complete_when_not_scheduled(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """on_client_disconnected calls on_call_complete iff _hangup_scheduled
    has not already done so. This pins the disconnect-path dispatch."""
    import call_pipeline

    sess = make_call_session()
    on_complete = AsyncMock()
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
        on_call_complete=on_complete,
    )
    handler = pipecat_mocks["event_handlers"]["on_client_disconnected"]
    # Reset the task cancel mock so we can observe disconnect's call.
    pipecat_mocks["task"].cancel = AsyncMock()
    await handler(transport=None, client=None)
    on_complete.assert_awaited_once()


async def test_disconnect_handler_skips_on_call_complete_when_already_fired(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """When a prior path (order_confirmed, _schedule_hangup, etc.) has
    already fired on_call_complete, the disconnect handler must not fire
    it again. Guarded by session._on_call_complete_fired via the
    _fire_on_call_complete helper."""
    import call_pipeline

    sess = make_call_session()
    on_complete = AsyncMock()
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
        on_call_complete=on_complete,
    )
    sess._on_call_complete_fired = True  # simulate prior fire site
    handler = pipecat_mocks["event_handlers"]["on_client_disconnected"]
    pipecat_mocks["task"].cancel = AsyncMock()
    await handler(transport=None, client=None)
    on_complete.assert_not_awaited()


async def test_disconnect_handler_cancels_call_timer(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """If a call-duration timer is active when the client disconnects, it must
    be cancelled to avoid a late escalation firing on a finished call."""
    import call_pipeline

    sess = make_call_session()
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )

    async def never():
        await asyncio.sleep(60)

    sess._call_timer_task = asyncio.create_task(never())
    pipecat_mocks["task"].cancel = AsyncMock()
    handler = pipecat_mocks["event_handlers"]["on_client_disconnected"]
    await handler(transport=None, client=None)
    assert sess._call_timer_task is None
