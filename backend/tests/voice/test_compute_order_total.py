"""
Unit tests for the compute_order_total Gemini Live function tool.

Covers:
- _handle_compute_order_total: resolves items via session.menu_index,
  multiplies unit price by quantity, sums to a total in cents/dollars.
  Robust to missing/invalid quantities, unresolved item names,
  and fuzzy menu matches.
- _tools_list wiring: COMPUTE_ORDER_TOTAL_TOOL is registered for
  non-appointment business types and excluded for appointment ones.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Heavy-mock fixture cloned from test_create_call_pipeline_orchestration.
# Pipecat construction primitives are replaced so create_call_pipeline can
# run to completion without opening sockets — we just need to inspect the
# registered handler and the tools kwarg passed to FakeGeminiLive.
# ---------------------------------------------------------------------------


@pytest.fixture
def pipecat_mocks(monkeypatch):
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
            state["transport"] = self

        def input(self):
            return MagicMock(name="transport_input")

        def output(self):
            return MagicMock(name="transport_output")

        def event_handler(self, name):
            def deco(fn):
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
            return None

    class FakeAggregator:
        def __init__(self):
            self.handlers: dict = {}

        def event_handler(self, name):
            def deco(fn):
                self.handlers[name] = fn
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

    import sys
    import types

    fake_uip_module = types.ModuleType("pipecat.processors.user_idle_processor")
    fake_uip_module.UserIdleProcessor = FakeIdleProcessor
    monkeypatch.setitem(
        sys.modules, "pipecat.processors.user_idle_processor", fake_uip_module
    )

    for mod_name, attrs in [
        ("pipecat.turns.user_stop", {"SpeechTimeoutUserTurnStopStrategy": MagicMock}),
        ("pipecat.turns.user_turn_strategies", {"UserTurnStrategies": MagicMock}),
    ]:
        mod = types.ModuleType(mod_name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, mod_name, mod)

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
# Helper — build a pipeline and retrieve the registered handler.
# ---------------------------------------------------------------------------


async def _get_handler(make_call_session, business_type="restaurant", menu_items=None):
    import call_pipeline

    sess = make_call_session(business_type=business_type, menu_items=menu_items)
    await call_pipeline.create_call_pipeline(
        websocket=MagicMock(),
        system_prompt="hi",
        restaurant_id="r",
        call_sid="c",
        session=sess,
    )
    return sess


class FakeParams:
    """Minimal stand-in for Pipecat's function-call params object."""

    def __init__(self, arguments):
        self.arguments = arguments
        self.tool_call_id = "tc_test"
        self.results: list = []

    async def result_callback(self, result):
        self.results.append(result)


# ---------------------------------------------------------------------------
# Handler-level tests.
# ---------------------------------------------------------------------------


SIMPLE_MENU = [
    {"id": "1", "name": "Chicken Biryani", "category": "Mains",
     "price": 1499, "available": True, "allergens": []},
    {"id": "2", "name": "Samosas", "category": "Starters",
     "price": 399, "available": True, "allergens": []},
]


async def test_tool_resolves_simple_order(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """1 Chicken Biryani + 2 Samosas → $14.99 + $7.98 = $22.97."""
    await _get_handler(make_call_session, menu_items=SIMPLE_MENU)
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["compute_order_total"]

    params = FakeParams(arguments={
        "items": [
            {"name": "Chicken Biryani", "quantity": 1},
            {"name": "Samosas", "quantity": 2},
        ]
    })
    await handler(params)
    assert len(params.results) == 1
    result = params.results[0]
    assert result["total_dollars"] == "$22.97"
    assert len(result["items_resolved"]) == 2
    assert result["items_unresolved"] == []


async def test_tool_handles_unresolved_item(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """An item name that doesn't match the menu lands in items_unresolved
    and does NOT contribute to the total."""
    await _get_handler(make_call_session, menu_items=SIMPLE_MENU)
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["compute_order_total"]

    params = FakeParams(arguments={
        "items": [
            {"name": "Chicken Biryani", "quantity": 1},
            {"name": "Quantum Foie Gras", "quantity": 3},
        ]
    })
    await handler(params)
    result = params.results[0]
    # Total reflects only the resolved item.
    assert result["total_dollars"] == "$14.99"
    assert "Quantum Foie Gras" in result["items_unresolved"]
    assert len(result["items_resolved"]) == 1


async def test_tool_handles_missing_quantity_defaults_to_one(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    await _get_handler(make_call_session, menu_items=SIMPLE_MENU)
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["compute_order_total"]

    params = FakeParams(arguments={"items": [{"name": "Samosas"}]})
    await handler(params)
    result = params.results[0]
    assert result["total_dollars"] == "$3.99"
    assert result["items_resolved"][0]["quantity"] == 1


@pytest.mark.parametrize("bad_qty", [0, -1, -5])
async def test_tool_handles_invalid_quantity_defaults_to_one(
    pipecat_mocks, fake_gemini_live, make_call_session, bad_qty
):
    """Quantities <= 0 floor to 1 so the order can't silently lose items."""
    await _get_handler(make_call_session, menu_items=SIMPLE_MENU)
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["compute_order_total"]

    params = FakeParams(arguments={
        "items": [{"name": "Samosas", "quantity": bad_qty}]
    })
    await handler(params)
    result = params.results[0]
    assert result["total_dollars"] == "$3.99"
    assert result["items_resolved"][0]["quantity"] == 1


async def test_tool_handles_empty_items_list(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    await _get_handler(make_call_session, menu_items=SIMPLE_MENU)
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["compute_order_total"]

    params = FakeParams(arguments={"items": []})
    await handler(params)
    result = params.results[0]
    assert result["total_dollars"] == "$0.00"
    assert result["items_resolved"] == []
    assert result["items_unresolved"] == []


async def test_tool_uses_menu_index_fuzzy_matching(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    """Slight name variations should still resolve via MenuIndex.find's
    partial / word-based fuzzy logic."""
    await _get_handler(make_call_session, menu_items=SIMPLE_MENU)
    inst = fake_gemini_live.instances[0]
    handler = inst.registered_functions["compute_order_total"]

    params = FakeParams(arguments={
        "items": [{"name": "chicken biryani", "quantity": 1}]
    })
    await handler(params)
    result = params.results[0]
    # Fuzzy match resolves to canonical "Chicken Biryani" and total = price.
    assert result["total_dollars"] == "$14.99"
    assert result["items_unresolved"] == []
    assert result["items_resolved"][0]["name"] == "Chicken Biryani"


# ---------------------------------------------------------------------------
# _tools_list wiring tests.
# ---------------------------------------------------------------------------


async def test_tool_includes_tool_in_tools_list_for_restaurant(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    await _get_handler(make_call_session, business_type="restaurant")
    inst = fake_gemini_live.instances[0]
    assert inst.tools is not None
    assert call_pipeline.COMPUTE_ORDER_TOTAL_TOOL in inst.tools
    # And the corresponding handler is registered.
    assert "compute_order_total" in inst.registered_functions


async def test_tool_excludes_tool_for_appointment_business(
    pipecat_mocks, fake_gemini_live, make_call_session
):
    import call_pipeline

    await _get_handler(make_call_session, business_type="salon")
    inst = fake_gemini_live.instances[0]
    assert inst.tools is not None
    assert call_pipeline.CHECK_AVAILABILITY_TOOL in inst.tools
    assert call_pipeline.COMPUTE_ORDER_TOTAL_TOOL not in inst.tools
    # And the order-total handler is NOT registered.
    assert "compute_order_total" not in inst.registered_functions
