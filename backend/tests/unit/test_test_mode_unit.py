"""
Unit tests for backend/test_mode.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# IntegrationStatus._check_gemini
# ---------------------------------------------------------------------------

def test_check_gemini_returns_sandbox_when_key_set(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    s = IntegrationStatus()
    assert s.integrations["gemini"]["status"] == TestModeStatus.SANDBOX
    assert s.integrations["gemini"]["configured"] is True


def test_check_gemini_falls_back_to_genai_key(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_API_KEY", "fake-key")
    s = IntegrationStatus()
    assert s.integrations["gemini"]["status"] == TestModeStatus.SANDBOX


def test_check_gemini_returns_simulation_without_keys(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    s = IntegrationStatus()
    assert s.integrations["gemini"]["status"] == TestModeStatus.SIMULATION
    assert s.integrations["gemini"]["configured"] is False


# ---------------------------------------------------------------------------
# IntegrationStatus._check_telnyx
# ---------------------------------------------------------------------------

def test_check_telnyx_live_when_fully_configured(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("TELNYX_API_KEY", "KEY_real")
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")
    s = IntegrationStatus()
    assert s.integrations["telnyx"]["status"] == TestModeStatus.LIVE


def test_check_telnyx_simulation_when_missing_phone(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("TELNYX_API_KEY", "KEY_real")
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "")
    s = IntegrationStatus()
    assert s.integrations["telnyx"]["status"] == TestModeStatus.SIMULATION


# ---------------------------------------------------------------------------
# IntegrationStatus._check_stripe — all branches
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,expected_status", [
    ("sk_test_abc", "sandbox"),
    ("sk_live_abc", "live"),
    ("", "simulation"),
    ("not_a_real_key", "simulation"),
])
def test_check_stripe_branches(monkeypatch, key, expected_status):
    from test_mode import IntegrationStatus
    monkeypatch.setenv("STRIPE_SECRET_KEY", key)
    s = IntegrationStatus()
    assert s.integrations["stripe"]["status"] == expected_status


def test_check_stripe_includes_test_cards_in_sandbox(monkeypatch):
    from test_mode import IntegrationStatus
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    s = IntegrationStatus()
    cards = s.integrations["stripe"]["test_cards"]
    assert cards["success"] == "4242424242424242"
    assert cards["decline"] == "4000000000000002"


# ---------------------------------------------------------------------------
# IntegrationStatus._check_clerk
# ---------------------------------------------------------------------------

def test_check_clerk_sandbox_when_test_keys(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_abc")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc")
    s = IntegrationStatus()
    assert s.integrations["clerk"]["status"] == TestModeStatus.SANDBOX


def test_check_clerk_live_when_live_keys(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_live_abc")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_live_abc")
    s = IntegrationStatus()
    assert s.integrations["clerk"]["status"] == TestModeStatus.LIVE


def test_check_clerk_simulation_for_mixed_or_empty_keys(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "")
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    s = IntegrationStatus()
    assert s.integrations["clerk"]["status"] == TestModeStatus.SIMULATION


# ---------------------------------------------------------------------------
# get_overall_mode aggregates
# ---------------------------------------------------------------------------

def test_overall_mode_live_when_any_integration_live(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    s = IntegrationStatus()
    assert s.get_overall_mode() == TestModeStatus.LIVE


def test_overall_mode_sandbox_when_no_live_but_some_sandbox(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "")
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    monkeypatch.setenv("TELNYX_API_KEY", "")
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "")
    s = IntegrationStatus()
    assert s.get_overall_mode() == TestModeStatus.SANDBOX


def test_overall_mode_simulation_when_nothing_configured(monkeypatch):
    from test_mode import IntegrationStatus, TestModeStatus
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "")
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    monkeypatch.setenv("TELNYX_API_KEY", "")
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "")
    s = IntegrationStatus()
    assert s.get_overall_mode() == TestModeStatus.SIMULATION


def test_to_dict_includes_required_fields(monkeypatch):
    from test_mode import IntegrationStatus
    s = IntegrationStatus()
    out = s.to_dict()
    assert "mode" in out
    assert "integrations" in out
    assert "timestamp" in out
    assert set(out["integrations"].keys()) == {"gemini", "telnyx", "stripe", "clerk"}


# ---------------------------------------------------------------------------
# get_test_mode_status / is_sandbox_mode
# ---------------------------------------------------------------------------

def test_get_test_mode_status_refreshes_state(monkeypatch):
    from test_mode import get_test_mode_status
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    out = get_test_mode_status()
    assert out["integrations"]["stripe"]["status"] == "sandbox"


def test_is_sandbox_mode_true_when_sandbox(monkeypatch):
    from test_mode import is_sandbox_mode, get_test_mode_status
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    monkeypatch.setenv("TELNYX_API_KEY", "")
    get_test_mode_status()  # refresh
    assert is_sandbox_mode() is True


def test_is_sandbox_mode_false_when_live(monkeypatch):
    from test_mode import is_sandbox_mode, get_test_mode_status
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    get_test_mode_status()
    assert is_sandbox_mode() is False


# ---------------------------------------------------------------------------
# Test scenarios — well-formedness
# ---------------------------------------------------------------------------

def test_get_test_scenarios_returns_six():
    from test_mode import get_test_scenarios, SAMPLE_CUSTOMER_SCENARIOS
    scenarios = get_test_scenarios()
    assert len(scenarios) == len(SAMPLE_CUSTOMER_SCENARIOS) == 6


def test_get_test_scenarios_each_has_required_fields():
    from test_mode import get_test_scenarios
    required = {"id", "name", "caller_name", "message_count", "order_type", "expected_items"}
    for s in get_test_scenarios():
        assert required.issubset(s.keys())


def test_get_test_scenarios_ids_are_unique_and_sequential():
    from test_mode import get_test_scenarios
    scenarios = get_test_scenarios()
    ids = [s["id"] for s in scenarios]
    assert ids == list(range(len(scenarios)))


def test_get_test_scenarios_message_counts_match_underlying():
    from test_mode import get_test_scenarios, SAMPLE_CUSTOMER_SCENARIOS
    for scenario, raw in zip(get_test_scenarios(), SAMPLE_CUSTOMER_SCENARIOS):
        assert scenario["message_count"] == len(raw["messages"])


def test_get_scenario_by_id_returns_full_scenario():
    from test_mode import get_scenario_by_id
    scenario = get_scenario_by_id(0)
    assert scenario is not None
    assert "messages" in scenario
    assert scenario["name"] == "Simple Pickup Order"


def test_get_scenario_by_id_returns_none_for_out_of_range():
    from test_mode import get_scenario_by_id
    assert get_scenario_by_id(99) is None
    assert get_scenario_by_id(-1) is None


@pytest.mark.parametrize("expected_type", ["pickup", "delivery", "reservation", "escalation"])
def test_scenarios_cover_expected_order_types(expected_type):
    from test_mode import get_test_scenarios
    order_types = {s["order_type"] for s in get_test_scenarios()}
    assert expected_type in order_types
