"""H1: plan-casing must be case-insensitive — a lowercase/mixed-case stored
plan value must never silently demote a paying Pro customer to STARTER."""
from __future__ import annotations

import pytest

from server import get_plan_features, PLAN_CONFIG

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", ["PRO", "pro", "Pro", "pRo"])
def test_get_plan_features_pro_is_case_insensitive(value):
    assert get_plan_features(value) == PLAN_CONFIG["PRO"]
    # spot-check a Pro-only feature actually unlocks
    assert get_plan_features(value)["reservations_enabled"] is True


@pytest.mark.parametrize("value", ["STARTER", "starter", "Starter"])
def test_get_plan_features_starter_is_case_insensitive(value):
    assert get_plan_features(value) == PLAN_CONFIG["STARTER"]


@pytest.mark.parametrize("value", [None, "", "garbage", "enterprise"])
def test_get_plan_features_unknown_falls_back_to_starter(value):
    assert get_plan_features(value) == PLAN_CONFIG["STARTER"]
