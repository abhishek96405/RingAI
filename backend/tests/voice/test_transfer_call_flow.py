"""
Tests for the AI-to-human transfer race fix.

Covers:
- _fire_on_call_complete helper: idempotency, single firing
- _schedule_hangup fires on_call_complete for non-confirm reasons
  (escalation, customer_idle, farewell_timeout) — regression for the
  latent bug fixed alongside the race fix
- _handle_transfer_bridged: bridge succeeded → cancel pipeline, no
  double-fire of on_call_complete
- _handle_transfer_timeout: destination didn't answer → hang up A-leg,
  cancel pipeline, no double-fire

All Telnyx HTTP calls are mocked. No live network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.voice


# ---------------------------------------------------------------------------
# _fire_on_call_complete — the single firing helper.
# ---------------------------------------------------------------------------


async def test_fire_on_call_complete_is_idempotent(make_call_session):
    """Two calls to the helper must result in exactly one invocation of
    the wrapped on_call_complete callback. Flag flip is BEFORE the await
    so re-entrant calls during the callback are short-circuited too."""
    sess = make_call_session()
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete

    await sess._fire_on_call_complete()
    await sess._fire_on_call_complete()

    on_complete.assert_awaited_once()
    assert sess._on_call_complete_fired is True


async def test_fire_on_call_complete_swallows_callback_exceptions(make_call_session):
    """Exceptions from the wrapped callback must not propagate — they'd
    bubble into asyncio cleanup paths and could trigger cascade failures.
    The flag stays True so we don't retry billing/analytics."""
    sess = make_call_session()
    sess._on_call_complete = AsyncMock(side_effect=RuntimeError("dashboard down"))

    # Must not raise.
    await sess._fire_on_call_complete()

    assert sess._on_call_complete_fired is True


async def test_fire_on_call_complete_with_no_callback_is_noop(make_call_session):
    """When _on_call_complete is None (test scaffolds without dashboard
    wiring), the helper still sets the flag and returns cleanly."""
    sess = make_call_session()
    sess._on_call_complete = None

    await sess._fire_on_call_complete()

    assert sess._on_call_complete_fired is True


# ---------------------------------------------------------------------------
# _schedule_hangup fires on_call_complete for non-confirm reasons.
# ---------------------------------------------------------------------------


async def test_schedule_hangup_fires_on_call_complete_for_escalation(
    make_call_session, monkeypatch
):
    """Regression for the latent bug: escalation never produced a call_records
    insert because _schedule_hangup didn't fire on_call_complete and the
    on_client_disconnected fallback was suppressed by the _hangup_scheduled
    flag set at the top of _schedule_hangup.

    Post-bug-2-fix: the fire is dispatched as a background task to avoid
    blocking the transfer on slow Gemini analytics. We yield to the event
    loop to let the background task complete before asserting."""
    import asyncio

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=False)  # no transfer, fall through
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete
    monkeypatch.setattr("telnyx_service.hang_up_call", AsyncMock(return_value=True))
    # PL-26: the fall-through path now speaks an apology before hangup.
    monkeypatch.setattr("call_pipeline.TRANSFER_FAIL_HANGUP_DELAY_SECS", 0)
    monkeypatch.setattr("telnyx_service.speak_text", AsyncMock(return_value=True))

    await sess._schedule_hangup(reason="escalation")
    # Let the asyncio.create_task background fire complete.
    for _ in range(5):
        await asyncio.sleep(0)

    on_complete.assert_awaited_once()
    assert sess._on_call_complete_fired is True


async def test_schedule_hangup_fires_on_call_complete_for_customer_idle(
    make_call_session, monkeypatch
):
    """Same regression check for the customer_idle path."""
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete
    monkeypatch.setattr("telnyx_service.hang_up_call", AsyncMock(return_value=True))

    await sess._schedule_hangup(reason="customer_idle")

    on_complete.assert_awaited_once()


async def test_schedule_hangup_fires_on_call_complete_for_farewell_timeout(
    make_call_session, monkeypatch
):
    """Same regression check for the farewell_timeout path."""
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete
    monkeypatch.setattr("telnyx_service.hang_up_call", AsyncMock(return_value=True))

    await sess._schedule_hangup(reason="farewell_timeout")

    on_complete.assert_awaited_once()


# ---------------------------------------------------------------------------
# _handle_transfer_bridged — call.bridged webhook path.
# ---------------------------------------------------------------------------


async def test_handle_transfer_bridged_cancels_pipeline_and_fallback(
    make_call_session, monkeypatch
):
    """When Telnyx confirms the bridge, we cancel both the pipeline (releases
    Gemini Live) and the fallback watchdog task. We DO NOT hang up the A-leg
    — it's the bridge anchor and hanging it up would drop the call."""
    import asyncio

    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_in_progress = True

    async def never():
        await asyncio.sleep(999)

    sess._transfer_fallback_task = asyncio.create_task(never())
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._handle_transfer_bridged()

    assert sess._bridge_succeeded is True
    sess._pipeline_task.cancel.assert_awaited_once()
    assert sess._transfer_fallback_task is None
    # CRITICAL: A-leg must NOT be hung up. It's the bridge anchor.
    hang_up.assert_not_awaited()


async def test_handle_transfer_bridged_is_idempotent(make_call_session):
    """If call.bridged somehow fires twice (or webhook + fallback race),
    the second invocation is a no-op."""
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_in_progress = True

    await sess._handle_transfer_bridged()
    await sess._handle_transfer_bridged()

    sess._pipeline_task.cancel.assert_awaited_once()


async def test_call_bridged_does_not_fire_on_call_complete_again(
    make_call_session, monkeypatch
):
    """on_call_complete fires at transfer initiation (in _schedule_hangup),
    not at bridge time. The bridge handler must NOT fire it again — that
    would double-bill, double-insert call_records, etc. Guarded by the
    _on_call_complete_fired flag in the _fire_on_call_complete helper."""
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_in_progress = True
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete
    # Simulate prior firing at transfer initiation.
    sess._on_call_complete_fired = True

    await sess._handle_transfer_bridged()

    # The bridge handler itself never calls the helper, but even if a future
    # change does, the flag protects against double-fire.
    on_complete.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_transfer_timeout — destination didn't answer.
# ---------------------------------------------------------------------------


async def test_handle_transfer_timeout_hangs_up_a_leg(make_call_session, monkeypatch):
    """When the transfer fails to bridge (destination didn't answer), the
    A-leg must be explicitly hung up. Per the May 2026 product scope
    decision, no TTS goodbye is played — customer hears ringing then
    dead line; the call shows as ESCALATED in the dashboard."""
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_in_progress = True
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._handle_transfer_timeout()

    hang_up.assert_awaited_once_with(sess.call_sid)
    sess._pipeline_task.cancel.assert_awaited_once()


async def test_handle_transfer_timeout_is_skipped_if_bridge_already_succeeded(
    make_call_session, monkeypatch
):
    """Race protection: if call.bridged arrives between the timeout decision
    and the timeout handler running, the bridge_succeeded flag should make
    the timeout handler a no-op (don't tear down a successful bridge)."""
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_in_progress = True
    sess._bridge_succeeded = True  # bridge already succeeded
    hang_up = AsyncMock()
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._handle_transfer_timeout()

    hang_up.assert_not_awaited()
    sess._pipeline_task.cancel.assert_not_awaited()


async def test_transfer_timeout_does_not_double_fire_on_call_complete(
    make_call_session, monkeypatch
):
    """If the fallback timer fires AND the webhook also fires (race), the
    on_call_complete callback must still only fire once total. Both paths
    converge on the idempotent helper guarded by _on_call_complete_fired."""
    sess = make_call_session()
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._transfer_in_progress = True
    on_complete = AsyncMock()
    sess._on_call_complete = on_complete
    # Already fired at transfer initiation.
    sess._on_call_complete_fired = True
    monkeypatch.setattr("telnyx_service.hang_up_call", AsyncMock(return_value=True))

    # Two cleanup paths fire (race).
    await sess._handle_transfer_timeout()
    await sess._fire_on_call_complete()  # webhook path also tries

    on_complete.assert_not_awaited()


# ---------------------------------------------------------------------------
# PL-26 (apology only) — speak before hanging up on a FAILED transfer.
#
# When escalation can't dispatch (no number, or the transfer endpoint errored)
# the caller is still connected. The immediate-failure path must speak a short
# apology before hanging up so they're not dropped into silence. (The OTP
# number-verification half of PL-26 is a SEPARATE PR — not covered here. The
# watchdog/timeout path keeps its May-2026 "no TTS goodbye" behavior — see
# test_handle_transfer_timeout_hangs_up_a_leg.)
# ---------------------------------------------------------------------------


async def test_escalation_no_destination_speaks_apology_before_hangup(
    make_call_session, monkeypatch
):
    """Escalation requested but no escalation_phone configured → an apology TTS
    is emitted, THEN the call hangs up (apology strictly before hangup)."""
    import call_pipeline

    sess = make_call_session(config={"business_type": "restaurant"})  # no escalation_phone_number
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    monkeypatch.setattr("call_pipeline.TRANSFER_FAIL_HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._on_call_complete = AsyncMock()

    order: list[str] = []

    async def fake_speak(call_sid, text, *a, **k):
        order.append("speak")
        fake_speak.text = text
        return True

    async def fake_hang_up(call_sid):
        order.append("hangup")
        return True

    monkeypatch.setattr("telnyx_service.speak_text", fake_speak)
    monkeypatch.setattr("telnyx_service.hang_up_call", fake_hang_up)

    await sess._schedule_hangup(reason="escalation")

    assert order == ["speak", "hangup"], "apology must be spoken before hangup"
    assert "couldn't connect you" in fake_speak.text


async def test_escalation_transfer_endpoint_error_speaks_apology_before_hangup(
    make_call_session, monkeypatch
):
    """Escalation phone IS configured but the transfer dispatch fails
    (_transfer_call returns False) → still speak the apology before hangup."""
    sess = make_call_session(config={"escalation_phone_number": "+15555550199"})
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    monkeypatch.setattr("call_pipeline.TRANSFER_FAIL_HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._on_call_complete = AsyncMock()
    sess._transfer_call = AsyncMock(return_value=False)  # dispatch failed

    speak = AsyncMock(return_value=True)
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.speak_text", speak)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._schedule_hangup(reason="escalation")

    speak.assert_awaited_once()
    assert speak.await_args.args[0] == sess.call_sid
    hang_up.assert_awaited_once_with(sess.call_sid)


async def test_escalation_apology_tts_failure_still_hangs_up(
    make_call_session, monkeypatch
):
    """A TTS failure must never block teardown — if speak_text raises, the call
    still hangs up cleanly (no silent hung call)."""
    sess = make_call_session(config={"business_type": "restaurant"})
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    monkeypatch.setattr("call_pipeline.TRANSFER_FAIL_HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    sess._on_call_complete = AsyncMock()

    monkeypatch.setattr(
        "telnyx_service.speak_text", AsyncMock(side_effect=RuntimeError("telnyx 500"))
    )
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._schedule_hangup(reason="escalation")

    hang_up.assert_awaited_once_with(sess.call_sid)


# ---------------------------------------------------------------------------
# Audit defense — explicit hang_up_call on normal-branch hangup paths.
#
# With auto_hang_up=False on the TelnyxFrameSerializer, every legitimate
# hangup path must explicitly call telnyx_service.hang_up_call. The audit
# in PR1 identified three insertion points; these tests pin the assertion
# so regressions surface immediately.
# ---------------------------------------------------------------------------


async def test_escalation_does_not_await_on_call_complete_before_transfer(
    make_call_session, monkeypatch
):
    """Regression for 2026-05-29 production observation. on_call_complete
    runs analyse_call_transcript which makes a Gemini API call; when
    Gemini 503s and retries, it can take 12-16 seconds. Awaiting that
    synchronously before invoking _transfer_call meant the customer
    heard 'Please hold' then dead air for 12+ seconds while we did
    analytics — the actual transfer didn't fire until extraction
    finished.

    Fix: the escalation branch dispatches on_call_complete as an
    asyncio.create_task background fire. This test pins that contract:
    even when on_call_complete sleeps for several seconds, _transfer_call
    must run immediately without waiting on it."""
    import asyncio
    import time

    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()

    # Simulate slow on_call_complete (Gemini 503 retries).
    async def slow_complete(**kwargs):
        await asyncio.sleep(5.0)

    sess._on_call_complete = slow_complete

    transfer_started_at = []

    async def fake_transfer(to_number):
        transfer_started_at.append(time.monotonic())
        return True

    sess._transfer_call = fake_transfer
    monkeypatch.setattr("telnyx_service.stop_streaming", AsyncMock(return_value=True))
    monkeypatch.setattr("telnyx_service.hang_up_call", AsyncMock(return_value=True))

    start = time.monotonic()
    await sess._schedule_hangup(reason="escalation")
    elapsed = time.monotonic() - start

    # Transfer was attempted.
    assert len(transfer_started_at) == 1
    # _schedule_hangup returned in well under a second despite the 5s
    # on_call_complete; the background task is still running.
    assert elapsed < 1.0, (
        f"_schedule_hangup blocked for {elapsed:.2f}s — escalation transfer "
        f"was delayed by synchronous on_call_complete. Background-task "
        f"dispatch regressed."
    )

    # Clean up the still-running background task to avoid lingering work.
    if sess._transfer_fallback_task is not None:
        sess._transfer_fallback_task.cancel()


async def test_normal_hangup_branch_explicitly_hangs_up_telnyx_leg(
    make_call_session, monkeypatch
):
    """The normal branch of _schedule_hangup (any reason that isn't
    'escalation') must call telnyx_service.hang_up_call BEFORE cancelling
    the pipeline. Covered by reason='order_confirmed' here; the branch is
    shared across order_confirmed, appointment_confirmed,
    reservation_confirmed, customer_idle, farewell_timeout."""
    sess = make_call_session()
    monkeypatch.setattr("call_pipeline.HANGUP_DELAY_SECS", 0)
    sess._pipeline_task = AsyncMock()
    sess._pipeline_task.cancel = AsyncMock()
    hang_up = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.hang_up_call", hang_up)

    await sess._schedule_hangup(reason="order_confirmed", _skip_guard=True)

    hang_up.assert_awaited_once_with(sess.call_sid)
    sess._pipeline_task.cancel.assert_awaited_once()


# ---------------------------------------------------------------------------
# DID safety guard inside _transfer_call.
#
# Defense in depth: even if a misconfiguration slips past the API-level
# validate_phones_distinct check, _transfer_call must refuse to dial our
# own AI DID. Forwarding loops back to AI would otherwise re-enter the
# pipeline infinitely.
# ---------------------------------------------------------------------------


async def test_transfer_call_refuses_when_destination_equals_ai_did(
    make_call_session, monkeypatch
):
    """When restaurant_phone_number matches the transfer destination (after
    normalization), _transfer_call returns False and never touches Telnyx."""
    sess = make_call_session()
    sess.restaurant_phone_number = "+18156932226"

    monkeypatch.setenv("TELNYX_API_KEY", "test-key")
    transfer_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.transfer_call", transfer_mock)

    result = await sess._transfer_call("+18156932226")

    assert result is False
    transfer_mock.assert_not_awaited()


async def test_transfer_call_proceeds_when_destination_differs(
    make_call_session, monkeypatch
):
    """Positive regression: distinct numbers still flow through to Telnyx."""
    sess = make_call_session()
    sess.restaurant_phone_number = "+18156932226"

    monkeypatch.setenv("TELNYX_API_KEY", "test-key")
    transfer_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.transfer_call", transfer_mock)

    result = await sess._transfer_call("+15553334444")

    assert result is True
    transfer_mock.assert_awaited_once()


async def test_transfer_call_proceeds_when_restaurant_phone_number_is_none(
    make_call_session, monkeypatch
):
    """Regression: callers that don't supply restaurant_phone_number (legacy
    tests, in-flight callers before the rollout) must keep working — the
    guard is opt-in via the new constructor kwarg."""
    sess = make_call_session()
    # Factory default leaves restaurant_phone_number=None.
    assert sess.restaurant_phone_number is None

    monkeypatch.setenv("TELNYX_API_KEY", "test-key")
    transfer_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("telnyx_service.transfer_call", transfer_mock)

    result = await sess._transfer_call("+15553334444")

    assert result is True
    transfer_mock.assert_awaited_once()
