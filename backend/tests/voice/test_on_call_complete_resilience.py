"""
PL-14 — a completed call's record must never be silently lost.

These tests drive the module-level ``server._on_call_complete_impl`` (extracted
from the ``telnyx_media_stream`` websocket closure so the critical post-call
save path is testable in isolation). They pin the three layered guarantees:

  1. A Gemini transcript-analysis failure degrades the saved *analysis* only —
     the call record (transcript + extracted order) is still persisted.
  2. ``active_calls`` is always cleaned up, even when the save path errors —
     no stale active-call row is ever left behind.
  3. A failure *before* the primary insert still produces a minimal
     ``status="INCOMPLETE"`` record (a completed call is never zero-rows), and
     the happy path inserts exactly once (the fallback never duplicates).

All DB and downstream side effects are faked — no Mongo, no network, no Gemini.
"""

from __future__ import annotations

import pytest

import server

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# Minimal fakes.
# ---------------------------------------------------------------------------


class FakeCollection:
    def __init__(self) -> None:
        self.docs: list = []
        self.insert_calls = 0
        self.delete_calls = 0
        self.fail_insert = False

    async def insert_one(self, doc):
        self.insert_calls += 1
        if self.fail_insert:
            raise RuntimeError("call_records insert failed")
        self.docs.append(doc)

    async def delete_one(self, query):
        self.delete_calls += 1
        return None

    async def find_one(self, *a, **k):
        return None

    async def update_one(self, *a, **k):
        return None


class FakeDB:
    def __init__(self) -> None:
        self.call_records = FakeCollection()
        self.active_calls = FakeCollection()
        self.customer_profiles = FakeCollection()


class FakeOrder:
    def __init__(self) -> None:
        self.customer_name = None
        self.save_name_consent = None
        self.items: list = []


class FakeSession:
    def __init__(self, record, *, build_raises: bool = False) -> None:
        self._record = record
        self._build_raises = build_raises
        self.order = FakeOrder()
        self.business_type = "restaurant"
        self._sms_count = 0
        self.reservation_booked = False

    def build_final_call_record(self):
        if self._build_raises:
            raise RuntimeError("build_final_call_record blew up")
        return self._record

    async def _ensure_reservation_booked(self):
        self.reservation_booked = True


def _record(**over):
    base = {
        "order": {"items": [{"name": "Pizza", "quantity": 1}], "type": "pickup"},
        "order_total": 1499,
        "quality_eval": {"rule_based_score": 90},
        "status": "COMPLETED",
        "escalated_to_human": False,
        "contained_by_ai": True,
        "caller_name": None,
    }
    base.update(over)
    return base


@pytest.fixture
def isolate_downstream(monkeypatch):
    """Neutralise post-save side effects (billing, plan features, websocket
    notify) so the tests target only the PL-14 save resilience."""

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(server, "_record_call_for_billing", _noop, raising=True)
    monkeypatch.setattr(
        server,
        "get_plan_features",
        lambda *a, **k: {"customer_recognition": False, "auto_learning": False},
        raising=True,
    )
    import websocket_notifications

    monkeypatch.setattr(websocket_notifications, "notify_new_call", _noop, raising=False)
    monkeypatch.setattr(websocket_notifications, "notify_new_order", _noop, raising=False)


def _call_kwargs(db, session):
    return dict(
        call_sid="CA_test_resilience",
        restaurant_id="rest_1",
        transcript=[
            {"role": "customer", "text": "one pizza please"},
            {"role": "ai", "text": "pickup in 20 minutes"},
        ],
        session=session,
        active_call={"caller_number": "+15555550123", "started_at": "2026-06-20T10:00:00+00:00"},
        restaurant={"id": "rest_1", "name": "Test Kitchen", "plan": "STARTER"},
        config={"sms_enabled": True},
        menu_items=[],
    )


# ---------------------------------------------------------------------------
# (1) Gemini analysis failure must NOT discard the record.
# ---------------------------------------------------------------------------


async def test_analysis_failure_still_saves_record_and_cleans_active_call(
    monkeypatch, isolate_downstream
):
    """The core scenario: analyse_call_transcript raises (Gemini 503). The call
    record — transcript + extracted order — must still be persisted, and the
    active_calls row cleaned up."""

    async def _boom(*a, **k):
        raise RuntimeError("Gemini 503")

    monkeypatch.setattr(server, "analyse_call_transcript", _boom, raising=True)

    db = FakeDB()
    session = FakeSession(_record())

    await server._on_call_complete_impl(db, **_call_kwargs(db, session))

    # Record was saved despite the analysis failure.
    assert db.call_records.insert_calls == 1
    saved = db.call_records.docs[0]
    assert saved["transcript"]  # transcript preserved
    assert saved["order_json"] == {"items": [{"name": "Pizza", "quantity": 1}], "type": "pickup"}
    assert saved["status"] == "COMPLETED"
    # Degraded analysis: no quality_score, rule_eval retained.
    assert saved["quality_score"] is None
    assert saved["analysis_json"]["rule_eval"] == {"rule_based_score": 90}
    # active_calls cleaned exactly once.
    assert db.active_calls.delete_calls == 1


# ---------------------------------------------------------------------------
# (2) Failure before the primary insert -> minimal INCOMPLETE fallback.
# ---------------------------------------------------------------------------


async def test_failure_before_insert_writes_incomplete_fallback(
    monkeypatch, isolate_downstream
):
    """If the save path raises before the primary insert (here:
    build_final_call_record blows up), a minimal status=INCOMPLETE record is
    still written and active_calls is cleaned."""

    async def _ok(*a, **k):
        return {"quality_score": 88}

    monkeypatch.setattr(server, "analyse_call_transcript", _ok, raising=True)

    db = FakeDB()
    session = FakeSession(_record(), build_raises=True)

    await server._on_call_complete_impl(db, **_call_kwargs(db, session))

    # Exactly one record — the fallback.
    assert db.call_records.insert_calls == 1
    saved = db.call_records.docs[0]
    assert saved["status"] == "INCOMPLETE"
    assert saved["caller_number"] == "+15555550123"
    assert saved["transcript"]
    # active_calls still cleaned.
    assert db.active_calls.delete_calls == 1


async def test_active_calls_cleaned_even_when_everything_fails(monkeypatch):
    """Even if both the primary and fallback inserts fail, the finally block
    must still clean up active_calls (no stale row)."""

    async def _ok(*a, **k):
        return {"quality_score": 88}

    monkeypatch.setattr(server, "analyse_call_transcript", _ok, raising=True)

    db = FakeDB()
    db.call_records.fail_insert = True  # both primary and fallback insert fail
    session = FakeSession(_record())

    # Must not raise.
    await server._on_call_complete_impl(db, **_call_kwargs(db, session))

    assert db.active_calls.delete_calls == 1


# ---------------------------------------------------------------------------
# (3) Happy path — saved exactly once, no duplicate from the fallback.
# ---------------------------------------------------------------------------


async def test_happy_path_saves_once_no_duplicate(monkeypatch, isolate_downstream):
    """Full save succeeds: exactly one insert, active_calls cleaned, and the
    post-call reservation fallback runs. The INCOMPLETE fallback must NOT fire."""

    async def _ok(*a, **k):
        return {"quality_score": 91}

    monkeypatch.setattr(server, "analyse_call_transcript", _ok, raising=True)

    db = FakeDB()
    session = FakeSession(_record())

    await server._on_call_complete_impl(db, **_call_kwargs(db, session))

    assert db.call_records.insert_calls == 1
    saved = db.call_records.docs[0]
    assert saved["status"] == "COMPLETED"
    assert saved["quality_score"] == 91
    assert db.active_calls.delete_calls == 1
    assert session.reservation_booked is True
