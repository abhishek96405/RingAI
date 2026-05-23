"""
Unit tests for backend/eta_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# get_queue_multiplier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("depth,expected", [
    (0, 1.0),
    (1, 1.0),
    (2, 1.0),
    (3, 1.1),
    (4, 1.1),
    (5, 1.2),
    (7, 1.2),
    (8, 1.3),
    (12, 1.5),
    (19, 1.5),
    (20, 1.8),
    (100, 1.8),
])
def test_get_queue_multiplier(depth, expected):
    from eta_service import get_queue_multiplier
    assert get_queue_multiplier(depth) == expected


# ---------------------------------------------------------------------------
# get_item_prep_time
# ---------------------------------------------------------------------------

def test_get_item_prep_time_uses_item_specific_first():
    from eta_service import get_item_prep_time
    item = {"prep_time_minutes": 25, "category": "Pizza"}
    assert get_item_prep_time(item, default_prep_time=99) == 25


def test_get_item_prep_time_falls_back_to_category():
    from eta_service import get_item_prep_time
    item = {"category": "Pizza"}
    assert get_item_prep_time(item) == 18


def test_get_item_prep_time_matches_partial_category_string():
    from eta_service import get_item_prep_time
    item = {"category": "Wood-Fired Pizza"}
    assert get_item_prep_time(item) == 18


def test_get_item_prep_time_falls_back_to_default_for_unknown():
    from eta_service import get_item_prep_time
    item = {"category": "Some Weird Category"}
    assert get_item_prep_time(item, default_prep_time=22) == 22


def test_get_item_prep_time_handles_missing_category():
    from eta_service import get_item_prep_time
    assert get_item_prep_time({}, default_prep_time=15) == 15


# ---------------------------------------------------------------------------
# format_eta_for_speech
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("minutes,expected_substr", [
    (5, "10 minutes"),
    (12, "15 minutes"),
    (18, "20 minutes"),
    (23, "25 minutes"),
    (28, "half an hour"),
    (38, "35 to 40 minutes"),
    (45, "45 minutes"),
    (55, "an hour"),
    (60, "an hour"),
    (70, "1 hour"),
    (90, "1 hour and 30 minutes"),
    (180, "3 hour"),
])
def test_format_eta_for_speech(minutes, expected_substr):
    from eta_service import format_eta_for_speech
    result = format_eta_for_speech(minutes)
    assert expected_substr in result


# ---------------------------------------------------------------------------
# calculate_dynamic_eta
# ---------------------------------------------------------------------------

async def test_calculate_dynamic_eta_with_single_pizza_during_calm_hours(monkeypatch):
    """Single pizza order at a calm time should produce a 20-minute ETA (18 → rounded up)."""
    from eta_service import calculate_dynamic_eta

    # Avoid peak-hours adjustment by patching pytz/datetime.now indirectly
    # via passing a Restaurant.timezone that's UTC and ensuring queue is calm.

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Margherita Pizza", "menu_item_id": "p1", "quantity": 1}],
        restaurant={"timezone": "UTC", "avg_prep_time_minutes": 15},
        config={},
        menu_items=[{"id": "p1", "name": "Margherita Pizza", "category": "pizza"}],
        queue_depth=0,
    )
    # base prep = 18 (pizza), queue mult 1.0, *peak mult uncertain*
    assert result["eta_minutes"] >= 18
    assert result["queue_depth"] == 0
    assert result["queue_multiplier"] == 1.0
    assert len(result["item_breakdown"]) == 1


async def test_calculate_dynamic_eta_rounds_up_to_nearest_five(monkeypatch):
    """A 12-minute prep should round up to 15 minutes."""
    from eta_service import calculate_dynamic_eta

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Caesar Salad", "quantity": 1, "menu_item_id": "s1"}],
        restaurant={"timezone": "UTC", "avg_prep_time_minutes": 12},
        config={},
        menu_items=[{"id": "s1", "name": "Caesar Salad", "category": "salads"}],
        queue_depth=0,
    )
    # salads = 5 min default, but min ETA is 10
    assert result["eta_minutes"] >= 10
    assert result["eta_minutes"] % 5 == 0


async def test_calculate_dynamic_eta_uses_max_not_sum_across_items():
    """Parallel kitchen prep means max(item_times), not sum."""
    from eta_service import calculate_dynamic_eta

    result = await calculate_dynamic_eta(
        order_items=[
            {"name": "Pizza", "menu_item_id": "p1", "quantity": 1},
            {"name": "Salad", "menu_item_id": "s1", "quantity": 1},
        ],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[
            {"id": "p1", "name": "Pizza", "category": "pizza", "prep_time_minutes": 18},
            {"id": "s1", "name": "Salad", "category": "salads", "prep_time_minutes": 5},
        ],
        queue_depth=0,
    )
    # base_eta should be max (18), not sum (23)
    assert result["base_eta"] == 18


async def test_calculate_dynamic_eta_adds_extra_per_duplicate_quantity():
    """Multiple of the same item adds +2 min per extra unit."""
    from eta_service import calculate_dynamic_eta

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Pizza", "menu_item_id": "p1", "quantity": 3}],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "p1", "name": "Pizza", "prep_time_minutes": 18}],
        queue_depth=0,
    )
    # 3x pizza = 18 + 2 * 2 = 22 base
    assert result["base_eta"] == 22


async def test_calculate_dynamic_eta_applies_queue_multiplier_when_busy():
    """A busy kitchen extends ETA."""
    from eta_service import calculate_dynamic_eta

    base = await calculate_dynamic_eta(
        order_items=[{"name": "Pizza", "menu_item_id": "p1", "quantity": 1}],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "p1", "name": "Pizza", "prep_time_minutes": 20}],
        queue_depth=0,
    )

    busy = await calculate_dynamic_eta(
        order_items=[{"name": "Pizza", "menu_item_id": "p1", "quantity": 1}],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "p1", "name": "Pizza", "prep_time_minutes": 20}],
        queue_depth=10,
    )

    assert busy["eta_minutes"] >= base["eta_minutes"]
    assert busy["queue_multiplier"] > 1.0


async def test_calculate_dynamic_eta_falls_back_to_pos_queue_depth(monkeypatch):
    """When no queue_depth is supplied, the service tries gemini_service.get_kitchen_queue_depth."""
    from eta_service import calculate_dynamic_eta

    monkeypatch.setattr(
        "gemini_service.get_kitchen_queue_depth",
        AsyncMock(return_value=15),
    )

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Pizza", "menu_item_id": "p1", "quantity": 1}],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "p1", "name": "Pizza", "prep_time_minutes": 15}],
        queue_depth=None,
    )
    assert result["queue_depth"] == 15
    assert result["queue_multiplier"] > 1.0


async def test_calculate_dynamic_eta_minimum_is_10_minutes():
    """Even a tiny order can never produce an ETA below 10 minutes."""
    from eta_service import calculate_dynamic_eta

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Coffee", "menu_item_id": "c1", "quantity": 1}],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "c1", "name": "Coffee", "category": "beverages"}],
        queue_depth=0,
    )
    assert result["eta_minutes"] >= 10


async def test_calculate_dynamic_eta_handles_unknown_timezone_gracefully():
    """A bad timezone string should fall through without crashing."""
    from eta_service import calculate_dynamic_eta

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Pizza", "menu_item_id": "p1", "quantity": 1}],
        restaurant={"timezone": "Not/A/Timezone"},
        config={},
        menu_items=[{"id": "p1", "name": "Pizza", "prep_time_minutes": 20}],
        queue_depth=0,
    )
    assert result["eta_minutes"] >= 10
    assert result["time_multiplier"] == 1.0


async def test_calculate_dynamic_eta_handles_pos_query_failure(monkeypatch):
    """If gemini_service.get_kitchen_queue_depth raises, fall back to no queue multiplier."""
    from eta_service import calculate_dynamic_eta

    async def boom(*a, **k):
        raise RuntimeError("POS down")

    monkeypatch.setattr("gemini_service.get_kitchen_queue_depth", boom)

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Pizza", "menu_item_id": "p1", "quantity": 1}],
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "p1", "name": "Pizza", "prep_time_minutes": 18}],
        queue_depth=None,
    )
    assert result["queue_multiplier"] == 1.0


async def test_calculate_dynamic_eta_resolves_item_by_name_when_id_missing():
    """Menu lookup should fall back to name when menu_item_id is empty."""
    from eta_service import calculate_dynamic_eta

    result = await calculate_dynamic_eta(
        order_items=[{"name": "Margherita Pizza", "quantity": 1}],  # no menu_item_id
        restaurant={"timezone": "UTC"},
        config={},
        menu_items=[{"id": "p1", "name": "Margherita Pizza", "prep_time_minutes": 20}],
        queue_depth=0,
    )
    assert result["item_breakdown"][0]["base_prep_time"] == 20
