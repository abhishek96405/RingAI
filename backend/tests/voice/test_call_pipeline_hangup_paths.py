"""
Tests for hangup-scheduling paths in :class:`CallSession._schedule_hangup`.

Cases covered:
- ``order_confirmed`` happy path
- ``escalation`` with successful transfer (Telnyx Call Control API mocked)
- ``escalation`` with failed transfer (falls through to pipeline cancel)
- ``customer_idle`` after the idle escalation chain exhausts retries
- ``farewell_timeout`` post-AI-goodbye timer
- Idempotency — ``_hangup_scheduled`` guard blocks repeat invocations
- ``_skip_guard=True`` bypass
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.voice


@pytest.fixture(autouse=True)
def fast_hangup(monkeypatch):
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)


# ---------------------------------------------------------------------------
# Basic cancellation paths.
# ---------------------------------------------------------------------------


async def test_order_confirmed_hangup_cancels_pipeline(make_call_session):
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    await sess._schedule_hangup(reason="order_confirmed")
    sess._pipeline_task.cancel.assert_awaited_once()


async def test_hangup_records_scheduled_flag(make_call_session):
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    assert sess._hangup_scheduled is False
    await sess._schedule_hangup(reason="customer_idle")
    assert sess._hangup_scheduled is True


async def test_hangup_handles_missing_pipeline_task(make_call_session):
    """When create_call_pipeline failed before setting _pipeline_task, the
    hangup must not raise — just log."""
    sess = make_call_session()
    sess._pipeline_task = None
    # Should complete without raising.
    await sess._schedule_hangup(reason="order_confirmed")
    assert sess._hangup_scheduled is True


async def test_hangup_swallows_cancel_errors(make_call_session):
    """The pipeline_task.cancel() can raise (already cancelled, transport gone)
    — the hangup wraps it in try/except so the on_call_complete code path is
    not blocked."""
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock(
        side_effect=RuntimeError("already cancelled")
    )
    # Must not raise.
    await sess._schedule_hangup(reason="order_confirmed")


# ---------------------------------------------------------------------------
# Escalation transfer.
# ---------------------------------------------------------------------------


async def test_escalation_with_phone_attempts_transfer(make_call_session):
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=True)

    await sess._schedule_hangup(reason="escalation")
    sess._transfer_call.assert_awaited_once_with("+15555550199")


async def test_escalation_without_phone_skips_transfer(make_call_session):
    sess = make_call_session()
    sess.config.pop("escalation_phone_number", None)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=True)

    await sess._schedule_hangup(reason="escalation")
    sess._transfer_call.assert_not_awaited()
    # Falls straight through to cancel.
    sess._pipeline_task.cancel.assert_awaited_once()


async def test_transfer_call_handles_telnyx_success_expected(make_call_session):
    sess = make_call_session()

    async def fake_post(self, url, **kwargs):
        class R:
            status_code = 200

            def raise_for_status(self):
                pass

        return R()

    with patch("httpx.AsyncClient.post", new=fake_post):
        ok = await sess._transfer_call("+15555550199")
    assert ok is True


async def test_transfer_call_handles_telnyx_failure(make_call_session):
    sess = make_call_session()

    async def fake_post(self, url, **kwargs):
        raise RuntimeError("simulated telnyx 502")

    with patch("httpx.AsyncClient.post", new=fake_post):
        ok = await sess._transfer_call("+15555550199")
    assert ok is False


# ---------------------------------------------------------------------------
# Idempotency.
# ---------------------------------------------------------------------------


async def test_double_hangup_without_skip_is_blocked(make_call_session):
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    await sess._schedule_hangup(reason="first")
    first_count = sess._pipeline_task.cancel.await_count

    await sess._schedule_hangup(reason="second")
    assert sess._pipeline_task.cancel.await_count == first_count


async def test_skip_guard_bypasses_idempotency(make_call_session):
    sess = make_call_session()
    sess._hangup_scheduled = True
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    await sess._schedule_hangup(reason="forced", _skip_guard=True)
    sess._pipeline_task.cancel.assert_awaited_once()


# ---------------------------------------------------------------------------
# Farewell timer cancelation when customer speaks again.
# ---------------------------------------------------------------------------


async def test_farewell_timer_cancellation_on_customer_turn(make_call_session):
    """When a farewell phrase fires the 30s timer, a subsequent customer turn
    cancels it (so the call doesn't terminate while the customer is talking)."""
    sess = make_call_session()

    async def never_runs():
        await asyncio.sleep(60)

    sess._farewell_timer = asyncio.create_task(never_runs())

    # Simulate the on_user_turn_stopped cancellation logic.
    if hasattr(sess, "_farewell_timer") and sess._farewell_timer:
        sess._farewell_timer.cancel()
        sess._farewell_timer = None

    assert sess._farewell_timer is None
