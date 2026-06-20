"""
PL-27 — background side-effect tasks must be GC-safe and error-visible.

The notification/enrichment tasks in the call pipeline were spawned with a
bare ``asyncio.create_task(...)`` whose result was never stored. asyncio only
holds a *weak* reference to such a task, so it can be garbage-collected before
it finishes (silently dropping the work), and any exception it raises is
swallowed. ``CallSession._spawn_tracked`` fixes both:

  - keeps a strong reference in ``self._background_tasks`` until completion
    (GC-safe),
  - attaches a done-callback that logs any exception (visible),
  - discards the task from the set when done (no unbounded growth).

It deliberately does NOT register tasks for blanket cancellation — these
notifications are meant to complete even after the call ends.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

pytestmark = pytest.mark.voice


async def _drain():
    """Yield to the loop enough times for a finished task's done-callback to run."""
    for _ in range(5):
        await asyncio.sleep(0)


async def test_spawn_tracked_logs_exception_and_does_not_propagate(
    make_call_session, caplog
):
    """A tracked task that raises must have its exception LOGGED (not swallowed),
    and the failure must not propagate to the spawning code (the call goes on)."""
    sess = make_call_session()

    async def boom():
        raise RuntimeError("notify operator failed")

    with caplog.at_level(logging.ERROR, logger="call_pipeline"):
        # Spawning must not raise even though the coro will fail.
        task = sess._spawn_tracked(boom(), "notify_dispatch_failure")
        await _drain()

    assert task.done()
    assert "notify_dispatch_failure" in caplog.text
    assert "notify operator failed" in caplog.text
    # Retrieved by the done-callback -> no "exception never retrieved" leak.
    assert task.exception() is not None


async def test_spawn_tracked_keeps_then_releases_reference(make_call_session):
    """While in flight the task is held in the set (GC-safe); once it finishes
    the done-callback discards it so the set doesn't grow unboundedly."""
    sess = make_call_session()
    started = asyncio.Event()
    release = asyncio.Event()

    async def work():
        started.set()
        await release.wait()

    task = sess._spawn_tracked(work(), "send_menu_sms")
    await started.wait()
    # Strong reference retained while running.
    assert task in sess._background_tasks

    release.set()
    await _drain()

    # Released after completion — no unbounded growth.
    assert task.done()
    assert task not in sess._background_tasks
    assert len(sess._background_tasks) == 0


async def test_spawn_tracked_success_is_not_logged_as_error(make_call_session, caplog):
    """A task that completes cleanly must NOT emit an error log."""
    sess = make_call_session()

    async def ok():
        return "done"

    with caplog.at_level(logging.ERROR, logger="call_pipeline"):
        sess._spawn_tracked(ok(), "classifier_availability_check")
        await _drain()

    assert "background task" not in caplog.text


async def test_cancelled_tracked_task_is_not_logged_as_error(make_call_session, caplog):
    """A cancelled task is a normal teardown event, not a failure — it must be
    discarded from the set without logging an error."""
    sess = make_call_session()

    async def slow():
        await asyncio.sleep(999)

    with caplog.at_level(logging.ERROR, logger="call_pipeline"):
        task = sess._spawn_tracked(slow(), "send_menu_sms")
        await asyncio.sleep(0)
        task.cancel()
        await _drain()

    assert task.cancelled()
    assert task not in sess._background_tasks
    assert "background task" not in caplog.text
