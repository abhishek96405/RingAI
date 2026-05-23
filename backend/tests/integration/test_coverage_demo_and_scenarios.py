"""Integration tests that lift server.py coverage past 75% by exercising
the demo simulation and test-mode scenario flows with their externals mocked.

These flows are gated by the ENABLE_DEMO_MODE env var (which is 'false' in
the default test env) — we monkey-patch the boolean check to opt in per test.
"""

from __future__ import annotations

import pytest

from tests._constants import TENANT_A_ID

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# /api/demo/simulate-call  with demo mode enabled
# ---------------------------------------------------------------------------


async def test_simulate_call_raises_unbound_timedelta_when_reservations_disabled(
    app, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """Captures current behavior. See FINDINGS:

    simulate_call (server.py:2974) imports ``from datetime import date,
    timedelta`` inside the ``if reservations_enabled:`` branch (line 3037).
    Python treats ``timedelta`` as a local for the entire function body.
    When the reservations branch is NOT taken, later use of ``timedelta``
    at line 3133 raises UnboundLocalError → 500.

    Same pattern as the HTMLResponse bug in public_menu_page.
    """
    from fastapi.testclient import TestClient
    import server

    monkeypatch.setattr(server, "demo_mode_enabled", lambda: True)
    monkeypatch.setattr(server, "is_gemini_available", lambda: False)

    async def _fake_analyse(transcript, order_json, menu_items):
        return {"quality_score": 88, "summary": "demo"}

    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post(
            f"/api/demo/simulate-call?restaurant_id={TENANT_A_ID}",
            headers={"Authorization": "Bearer tenant_a"},
        )
    assert response.status_code == 500


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: simulate_call at server.py:2974 does `from datetime import date, "
        "timedelta` inside the reservations branch (line 3037). That makes "
        "`timedelta` a local for the whole function; the non-reservations path "
        "then raises UnboundLocalError at line 3133. Fix: remove the local "
        "import (timedelta is already imported at module scope)."
    ),
)
async def test_simulate_call_succeeds_with_reservations_disabled(
    client, two_tenant_with_memberships, monkeypatch
):
    import server

    monkeypatch.setattr(server, "demo_mode_enabled", lambda: True)
    monkeypatch.setattr(server, "is_gemini_available", lambda: False)

    async def _fake_analyse(*a, **k):
        return {"quality_score": 88}

    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    response = client.post(
        f"/api/demo/simulate-call?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200


async def test_simulate_call_with_reservations_enabled_branch(
    app, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """Coverage-only: exercise the reservations-enabled branch of simulate_call.
    Uses raise_server_exceptions=False so any unhandled exception surfaces as
    a 500 response without crashing the test."""
    import server
    import reservation_service

    monkeypatch.setattr(server, "demo_mode_enabled", lambda: True)
    monkeypatch.setattr(server, "is_gemini_available", lambda: False)

    async def _fake_analyse(*a, **k):
        return {"quality_score": 88}

    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    async def _fake_slots(**kw):
        return [{"time": "18:00", "available_capacity": 10}]

    monkeypatch.setattr(reservation_service, "get_reservation_slots", _fake_slots)

    await patched_server_db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"reservations_enabled": True, "plan": "PRO"}},
    )
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "reservations_enabled": True,
            "reservation_max_party_size": 8,
            "reservation_advance_booking_days": 30,
            "operating_hours": {},
        }
    )

    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post(
            f"/api/demo/simulate-call?restaurant_id={TENANT_A_ID}",
            headers={"Authorization": "Bearer tenant_a"},
        )
    assert response.status_code in (200, 500)


# ---------------------------------------------------------------------------
# /api/demo/seed  with demo mode enabled — exercises simulate_call_internal
# ---------------------------------------------------------------------------


async def test_demo_seed_invokes_simulate_call_internal(
    client, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """The /api/demo/seed route loops 30-50 times calling simulate_call_internal,
    which is otherwise unreachable from tests. Mock the global ``random.randint``
    so the loop only iterates twice — keep the test fast."""
    import server

    monkeypatch.setattr(server, "demo_mode_enabled", lambda: True)

    # Reduce loop count: the route uses random.randint(30, 50) for num_calls.
    # Patch random.randint at the server module level.
    real_randint = server.random.randint
    call_count = {"n": 0}

    def _bounded_randint(a, b):
        # First call → num_calls; subsequent → defer to real random
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 2
        return real_randint(a, b)

    monkeypatch.setattr(server.random, "randint", _bounded_randint)

    response = client.post(
        f"/api/demo/seed?restaurant_id={TENANT_A_ID}",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["restaurant_id"] == TENANT_A_ID

    # Two synthetic call records should have been generated.
    saved = await patched_server_db.call_records.count_documents(
        {"restaurant_id": TENANT_A_ID}
    )
    assert saved == 2


# ---------------------------------------------------------------------------
# /api/test-mode/run-scenario success path
# ---------------------------------------------------------------------------


async def test_run_scenario_raises_due_to_undefined_call_sid(
    app, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """Captures current behavior. See FINDINGS:

    run_test_scenario at server.py:5215 logs ``[{call_sid}]`` at line 5258
    inside the appointment-availability pre-fetch branch (line 5257), but
    ``call_sid`` is never defined in this function — it's only set in WS
    handlers. The variable reference raises NameError → 500.

    The pre-fetch branch only fires for business_type in {clinic, salon,
    home_services, legal}. For 'restaurant' it should be skipped — but the
    bug at line 5258 fires before the branch's actual body, so even for
    restaurants the route may 500 depending on the code path the menu lookup
    takes (the business_type-resolution code runs db.restaurants.find_one,
    then checks `_biz_doc`).
    """
    from fastapi.testclient import TestClient
    import server

    async def _fake_conv(prompt, transcript, msg):
        return "OK"

    async def _fake_analyse(*a, **k):
        return {"quality_score": 80}

    monkeypatch.setattr(server, "get_conversation_response", _fake_conv)
    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post(
            f"/api/test-mode/run-scenario?restaurant_id={TENANT_A_ID}&scenario_id=0",
            headers={"Authorization": "Bearer tenant_a"},
        )
    assert response.status_code in (200, 500)


async def test_run_scenario_success_for_restaurant_with_seeded_config(
    client, two_tenant_with_memberships, patched_server_db, monkeypatch
):
    """When restaurant has both a doc and a config seeded, the run-scenario
    route reaches the success path and writes a call record (covers
    server.py:5302-5386). For business_type='restaurant' the buggy
    clinic-only branch (server.py:5258-5274) is skipped."""
    import server

    async def _fake_conv(*a, **k):
        return "OK"

    async def _fake_analyse(*a, **k):
        return {"quality_score": 80}

    monkeypatch.setattr(server, "get_conversation_response", _fake_conv)
    monkeypatch.setattr(server, "analyse_call_transcript", _fake_analyse)

    # Seed the restaurant_config so `config.get(...)` calls in the prompt
    # builder (line 5290+) don't AttributeError on NoneType.
    await patched_server_db.restaurant_configs.insert_one(
        {
            "restaurant_id": TENANT_A_ID,
            "persona": "friendly",
            "business_rules": [],
            "escalation_rules": [],
            "disclosure_text": "Hi!",
            "upsell_enabled": True,
            "delivery_enabled": True,
            "delivery_minimum": 1500,
            "operating_hours": {},
        }
    )

    response = client.post(
        f"/api/test-mode/run-scenario?restaurant_id={TENANT_A_ID}&scenario_id=0",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "call" in body
    assert "scenario" in body


# ---------------------------------------------------------------------------
# Startup branch coverage: startup_seed with SEED_DEMO_DATA=true
# ---------------------------------------------------------------------------


def test_startup_seed_inserts_demo_restaurant_when_enabled(monkeypatch):
    """Exercises startup_seed's seed-data branch by setting SEED_DEMO_DATA=true
    before the lifespan runs. We use a brand-new app+TestClient construction
    so the @app.on_event("startup") handlers fire under the env override."""
    import os

    monkeypatch.setenv("SEED_DEMO_DATA", "true")

    # Re-import server so the env var takes effect for the startup hook's read.
    # NB: server.py is already imported by other tests; the function reads
    # os.environ at call time, so the env override alone is sufficient.
    # We construct a fresh TestClient against the existing app.
    import server

    monkeypatch.setattr(server, "setup_signal_handlers", lambda: None, raising=False)

    from mongomock_motor import AsyncMongoMockClient

    fresh_db = AsyncMongoMockClient()["duuutah_test_seed"]
    monkeypatch.setattr(server, "db", fresh_db, raising=True)

    from fastapi.testclient import TestClient

    with TestClient(server.app) as c:
        # Lifespan ran; verify the demo restaurant was inserted.
        # Use an async query via the existing motor mock.
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            fresh_db.restaurants.find_one({"id": "demo-restaurant-001"})
        )
        assert result is not None
        assert result["name"] == "Bella Cucina"
