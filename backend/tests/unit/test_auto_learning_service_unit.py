"""
Unit tests for backend/auto_learning_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# get_learning_service singleton
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    import auto_learning_service
    monkeypatch.setattr(auto_learning_service, "_learning_service", None)
    yield


def test_get_learning_service_returns_singleton(async_db):
    from auto_learning_service import get_learning_service
    s1 = get_learning_service(async_db)
    s2 = get_learning_service(async_db)
    assert s1 is s2


# ---------------------------------------------------------------------------
# _parse_menu_suggestion
# ---------------------------------------------------------------------------

def test_parse_menu_suggestion_add_alias_pattern(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    parsed = svc._parse_menu_suggestion("Add 'coke' as alias for Coca-Cola")
    assert parsed["alias"] == "coke"
    assert parsed["target"] == "coca-cola"


def test_parse_menu_suggestion_should_map_pattern(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    parsed = svc._parse_menu_suggestion("'kung pao' should map to 'Kung Pao Chicken'")
    assert parsed["alias"] == "kung pao"
    assert parsed["target"] == "kung pao chicken"


def test_parse_menu_suggestion_customer_said_pattern(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    parsed = svc._parse_menu_suggestion("Customer said 'wings', matched to 'Buffalo Wings'")
    assert parsed["alias"] == "wings"
    assert parsed["target"] == "buffalo wings"


def test_parse_menu_suggestion_arrow_pattern(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    parsed = svc._parse_menu_suggestion("'soda' → 'Sprite'")
    assert parsed is not None
    assert "soda" in parsed["alias"].lower()


def test_parse_menu_suggestion_returns_none_for_garbage(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    assert svc._parse_menu_suggestion("just some random text") is None


# ---------------------------------------------------------------------------
# _process_menu_suggestion — first occurrence vs threshold
# ---------------------------------------------------------------------------

async def test_first_occurrence_stores_record(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    out = await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "bowl of fish", "resolved_as": "Apollo Fish"},
        call_id="call_1",
    )
    assert out is not None
    assert out["auto_applied"] is False

    doc = await async_db.learning_suggestions.find_one({
        "restaurant_id": "rest_a", "alias_term": "bowl of fish",
    })
    assert doc["occurrence_count"] == 1


async def test_increments_occurrence_count_on_repeat(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    for i in range(3):
        await svc._process_menu_suggestion(
            restaurant_id="rest_a",
            suggestion={"said": "bowl of fish", "resolved_as": "Apollo Fish"},
            call_id=f"call_{i}",
        )
    doc = await async_db.learning_suggestions.find_one({
        "restaurant_id": "rest_a", "alias_term": "bowl of fish",
    })
    assert doc["occurrence_count"] == 3
    assert doc.get("applied") is not True  # below threshold


async def test_threshold_no_longer_auto_applies(async_db):
    """B5-38: past the old MENU_ALIAS_THRESHOLD, aliases are NOT auto-applied.

    They stay pending (applied=False) and the menu item is untouched until a
    human approves via approve_alias_suggestion.
    """
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.menu_items.insert_one({
        "restaurant_id": "rest_a",
        "name": "Apollo Fish",
        "aliases": [],
    })

    for i in range(6):  # past the old threshold of 5
        out = await svc._process_menu_suggestion(
            restaurant_id="rest_a",
            suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
            call_id=f"call_{i}",
        )

    assert out["auto_applied"] is False
    doc = await async_db.learning_suggestions.find_one({
        "restaurant_id": "rest_a", "alias_term": "fish bowl",
    })
    assert doc.get("applied") is not True
    assert doc["occurrence_count"] == 6
    item = await async_db.menu_items.find_one({"name": "Apollo Fish"})
    assert "fish bowl" not in item.get("aliases", [])


async def test_approve_alias_suggestion_applies_and_marks(async_db):
    """Approving a pending alias applies it to the menu and marks it applied."""
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.menu_items.insert_one({
        "restaurant_id": "rest_a", "name": "Apollo Fish", "aliases": [],
    })
    await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
        call_id="c1",
    )
    pending = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})

    result = await svc.approve_alias_suggestion("rest_a", str(pending["_id"]))
    assert result is not None and result["applied"] is True

    item = await async_db.menu_items.find_one({"name": "Apollo Fish"})
    assert "fish bowl" in item["aliases"]
    doc = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})
    assert doc["applied"] is True
    out = await svc.get_pending_suggestions("rest_a")
    assert all(a["alias_term"] != "fish bowl" for a in out["pending_aliases"])
    learned = await svc.get_learned_aliases("rest_a")
    assert any(a["alias_term"] == "fish bowl" for a in learned)
    stats = await async_db.learning_stats.find_one({"restaurant_id": "rest_a"})
    assert stats["aliases_learned"] == 1


async def test_approve_alias_suggestion_invalid_id_returns_none(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    assert await svc.approve_alias_suggestion("rest_a", "not-an-objectid") is None


async def test_approve_alias_suggestion_wrong_tenant_returns_none(async_db):
    """Tenant isolation: can't approve another restaurant's suggestion."""
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
        call_id="c1",
    )
    pending = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})
    assert await svc.approve_alias_suggestion("rest_b", str(pending["_id"])) is None


async def test_reject_alias_suggestion_marks_and_hides(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
        call_id="c1",
    )
    pending = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})

    assert await svc.reject_alias_suggestion("rest_a", str(pending["_id"])) is True
    doc = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})
    assert doc["rejected"] is True
    assert doc.get("applied") is not True
    out = await svc.get_pending_suggestions("rest_a")
    assert all(a["alias_term"] != "fish bowl" for a in out["pending_aliases"])


async def test_rejected_suggestion_not_resurfaced(async_db):
    """A rejected term isn't re-counted or resurfaced on later calls."""
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
        call_id="c1",
    )
    pending = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})
    await svc.reject_alias_suggestion("rest_a", str(pending["_id"]))

    out = await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
        call_id="c2",
    )
    assert out is None
    doc = await async_db.learning_suggestions.find_one({"alias_term": "fish bowl"})
    assert doc["occurrence_count"] == 1


async def test_get_pending_suggestions_exposes_string_id(async_db):
    """Pending suggestions carry a JSON-safe string id (for approve/reject)."""
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "fish bowl", "resolved_as": "Apollo Fish"},
        call_id="c1",
    )
    out = await svc.get_pending_suggestions("rest_a")
    assert len(out["pending_aliases"]) == 1
    item = out["pending_aliases"][0]
    assert isinstance(item["id"], str) and item["id"]
    assert "_id" not in item


async def test_string_format_suggestions_still_parsed(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    out = await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion="Add 'wings' as alias for Buffalo Wings",
        call_id="call_1",
    )
    assert out is not None


async def test_invalid_dict_suggestion_returns_none(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    out = await svc._process_menu_suggestion(
        restaurant_id="rest_a",
        suggestion={"said": "", "resolved_as": ""},
        call_id="call_1",
    )
    assert out is None


# ---------------------------------------------------------------------------
# _apply_menu_alias — DB lookup branches
# ---------------------------------------------------------------------------

async def test_apply_menu_alias_to_exact_match(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.menu_items.insert_one({
        "restaurant_id": "rest_a",
        "name": "Margherita Pizza",
        "aliases": [],
    })

    ok = await svc._apply_menu_alias("rest_a", "marg pizza", "Margherita Pizza")
    assert ok is True

    item = await async_db.menu_items.find_one({"name": "Margherita Pizza"})
    assert "marg pizza" in item["aliases"]


async def test_apply_menu_alias_falls_back_to_global_when_no_match(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    ok = await svc._apply_menu_alias("rest_a", "foo", "Nonexistent Item")
    assert ok is True

    # Stored in menu_aliases instead
    doc = await async_db.menu_aliases.find_one({"restaurant_id": "rest_a", "alias": "foo"})
    assert doc["target"] == "Nonexistent Item"
    assert doc["auto_learned"] is True


async def test_apply_menu_alias_does_not_duplicate_existing(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.menu_items.insert_one({
        "restaurant_id": "rest_a",
        "name": "Latte",
        "aliases": ["coffee"],
    })
    await svc._apply_menu_alias("rest_a", "Coffee", "Latte")  # case-insensitive

    item = await async_db.menu_items.find_one({"name": "Latte"})
    coffee_count = sum(1 for a in item["aliases"] if a.lower() == "coffee")
    assert coffee_count == 1


# ---------------------------------------------------------------------------
# _flag_call_for_review & query methods
# ---------------------------------------------------------------------------

async def test_flag_call_for_review(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await svc._flag_call_for_review(
        restaurant_id="rest_a",
        call_id="call_1",
        analysis={"issues": ["order mismatch"], "order_accuracy": "low"},
        quality_score=60,
    )
    doc = await async_db.flagged_calls.find_one({"call_id": "call_1"})
    assert doc["quality_score"] == 60
    assert doc["reviewed"] is False


async def test_get_flagged_calls_filters_unreviewed_by_default(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.flagged_calls.insert_many([
        {"restaurant_id": "rest_a", "call_id": "c1", "quality_score": 50, "reviewed": False,
         "flagged_at": "2030-01-01T00:00:00"},
        {"restaurant_id": "rest_a", "call_id": "c2", "quality_score": 50, "reviewed": True,
         "flagged_at": "2030-01-01T00:00:00"},
        {"restaurant_id": "rest_b", "call_id": "c3", "quality_score": 50, "reviewed": False,
         "flagged_at": "2030-01-01T00:00:00"},
    ])

    calls = await svc.get_flagged_calls("rest_a")
    call_ids = [c["call_id"] for c in calls]
    assert "c1" in call_ids
    assert "c2" not in call_ids
    assert "c3" not in call_ids  # tenant isolation


async def test_get_flagged_calls_with_include_reviewed(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.flagged_calls.insert_many([
        {"restaurant_id": "rest_a", "call_id": "c1", "reviewed": False,
         "flagged_at": "2030-01-01"},
        {"restaurant_id": "rest_a", "call_id": "c2", "reviewed": True,
         "flagged_at": "2030-01-02"},
    ])
    calls = await svc.get_flagged_calls("rest_a", include_reviewed=True)
    assert len(calls) == 2


async def test_get_learned_aliases_only_returns_applied(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.learning_suggestions.insert_many([
        {"restaurant_id": "rest_a", "type": "menu_alias", "applied": True, "alias_term": "x"},
        {"restaurant_id": "rest_a", "type": "menu_alias", "applied": False, "alias_term": "y"},
    ])
    aliases = await svc.get_learned_aliases("rest_a")
    assert {a["alias_term"] for a in aliases} == {"x"}


async def test_get_pending_suggestions(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.learning_suggestions.insert_many([
        {"restaurant_id": "rest_a", "type": "menu_alias", "applied": False, "alias_term": "x"},
        {"restaurant_id": "rest_a", "type": "rule_suggestion", "flagged": True, "rule_text": "r"},
        {"restaurant_id": "rest_a", "type": "rule_suggestion", "flagged": False, "rule_text": "r2"},
    ])
    out = await svc.get_pending_suggestions("rest_a")
    assert len(out["pending_aliases"]) == 1
    assert len(out["suggested_rules"]) == 1


async def test_get_learning_stats_returns_defaults_when_none(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)
    stats = await svc.get_learning_stats("rest_a")
    assert stats["total_calls_processed"] == 0
    assert stats["aliases_learned"] == 0
    assert stats["calls_flagged"] == 0


async def test_get_learning_stats_returns_stored_when_present(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.learning_stats.insert_one({
        "restaurant_id": "rest_a",
        "total_calls_processed": 17,
        "aliases_learned": 3,
        "calls_flagged": 2,
    })
    stats = await svc.get_learning_stats("rest_a")
    assert stats["total_calls_processed"] == 17


async def test_mark_call_reviewed_updates_doc(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await async_db.flagged_calls.insert_one({
        "restaurant_id": "rest_a",
        "call_id": "c1",
        "reviewed": False,
    })
    await svc.mark_call_reviewed("c1", "correct", "looks good")

    doc = await async_db.flagged_calls.find_one({"call_id": "c1"})
    assert doc["reviewed"] is True
    assert doc["review_action"] == "correct"
    assert doc["review_notes"] == "looks good"


# ---------------------------------------------------------------------------
# process_call_analysis — end-to-end orchestration
# ---------------------------------------------------------------------------

async def test_process_call_analysis_low_quality_flags_call(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    actions = await svc.process_call_analysis(
        restaurant_id="rest_a",
        call_id="call_low",
        analysis={"quality_score": 50, "menu_suggestions": [], "rule_suggestions": [], "issues": ["x"]},
    )
    assert actions["flagged_for_review"] is True

    flagged = await async_db.flagged_calls.find_one({"call_id": "call_low"})
    assert flagged is not None


async def test_process_call_analysis_high_quality_does_not_flag(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    actions = await svc.process_call_analysis(
        restaurant_id="rest_a",
        call_id="call_good",
        analysis={"quality_score": 90, "menu_suggestions": [], "rule_suggestions": []},
    )
    assert actions["flagged_for_review"] is False


async def test_process_call_analysis_records_successes(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await svc.process_call_analysis(
        restaurant_id="rest_a",
        call_id="call_ok",
        analysis={"quality_score": 90, "menu_suggestions": [], "rule_suggestions": []},
        order_completed=True,
        order_total=3500,
    )
    pattern = await async_db.success_patterns.find_one({"call_id": "call_ok"})
    assert pattern["order_total"] == 3500


async def test_process_call_analysis_increments_stats(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await svc.process_call_analysis(
        restaurant_id="rest_a",
        call_id="c1",
        analysis={"quality_score": 80, "menu_suggestions": [], "rule_suggestions": []},
    )
    stats = await async_db.learning_stats.find_one({"restaurant_id": "rest_a"})
    assert stats["total_calls_processed"] == 1


# ---------------------------------------------------------------------------
# Tenant isolation — confirm queries scope to restaurant_id
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _process_rule_suggestion — coverage for rule-suggestion path
# ---------------------------------------------------------------------------

async def test_rule_suggestion_first_occurrence_stores_record(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    result = await svc._process_rule_suggestion(
        restaurant_id="rest_a",
        rule="Customer asked about gluten-free options — not handled",
        call_id="c1",
    )
    # First time: returns None (no flag), record stored
    assert result is None
    doc = await async_db.learning_suggestions.find_one({
        "restaurant_id": "rest_a",
        "type": "rule_suggestion",
    })
    assert doc["occurrence_count"] == 1


async def test_rule_suggestion_flags_after_threshold(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    for i in range(3):
        result = await svc._process_rule_suggestion(
            restaurant_id="rest_a",
            rule="Customer had to repeat order type twice",
            call_id=f"c{i}",
        )

    # 3rd call (RULE_SUGGESTION_THRESHOLD) should flag
    assert result is not None
    assert result["needs_review"] is True
    assert result["occurrences"] == 3


async def test_rule_suggestion_only_flags_once(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    for i in range(5):
        result = await svc._process_rule_suggestion(
            restaurant_id="rest_a",
            rule="Same rule repeated",
            call_id=f"c{i}",
        )

    # After 4th and 5th, already-flagged → returns None
    assert result is None


async def test_process_call_analysis_drives_rule_suggestion_path(async_db):
    """End-to-end through process_call_analysis with rule_suggestions input."""
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    actions = await svc.process_call_analysis(
        restaurant_id="rest_a",
        call_id="c1",
        analysis={
            "quality_score": 85,
            "menu_suggestions": [],
            "rule_suggestions": ["Reminder: add gluten-free options"],
        },
    )
    # First occurrence — no rule_suggestions returned to actions
    assert actions["rules_suggested"] == []


async def test_process_call_analysis_with_menu_and_rule_suggestions(async_db):
    """Both menu and rule suggestions get processed in one call."""
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    actions = await svc.process_call_analysis(
        restaurant_id="rest_a",
        call_id="c1",
        analysis={
            "quality_score": 88,
            "menu_suggestions": [{"said": "fries", "resolved_as": "French Fries"}],
            "rule_suggestions": ["Better greeting needed"],
        },
    )
    assert len(actions["aliases_learned"]) >= 1


async def test_tenant_isolation_on_flagged_calls(async_db):
    from auto_learning_service import AutoLearningService
    svc = AutoLearningService(async_db)

    await svc._flag_call_for_review("rest_a", "ca1", {"quality_score": 50}, 50)
    await svc._flag_call_for_review("rest_b", "cb1", {"quality_score": 50}, 50)

    a_calls = await svc.get_flagged_calls("rest_a")
    b_calls = await svc.get_flagged_calls("rest_b")
    assert {c["call_id"] for c in a_calls} == {"ca1"}
    assert {c["call_id"] for c in b_calls} == {"cb1"}
