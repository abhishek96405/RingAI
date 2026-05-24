"""
Tests for upsell behavior during the voice-call flow.

The upsell open issue is documented in detail in
``backend/tests/unit/test_gemini_service_upsell_decision.py`` and
``tests/FINDINGS.md`` (2026-05-22 entry "Upsell logic lacks a structured
decision function"). That module covers the prompt-assembly side.

This module covers the **voice-pipeline side** of the same issue: at the
``CallSession`` layer, there is no decision function that the post-call
extraction or kitchen dispatch can inspect to know what was suggested or
why. The xfail test below captures the expected future contract from
within the call-pipeline test surface so a future fix lights up two test
modules at once.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.voice


def test_call_session_has_no_decide_upsell_method_today(make_call_session):
    """CallSession does not expose any upsell-decision method today —
    pin this fact so adding one is a conscious decision."""
    sess = make_call_session()
    assert not hasattr(sess, "decide_upsell")
    assert not hasattr(sess, "generate_upsell")
    assert not hasattr(sess, "upsell_suggestion")


def test_call_session_does_not_record_upsell_acceptance_today(make_call_session):
    """The final call record makes no claim about upsell — no acceptance flag,
    no suggested-item id. Cross-channel attribution is therefore impossible."""
    sess = make_call_session()
    record = sess.build_final_call_record()
    assert "upsell_offered" not in record
    assert "upsell_accepted" not in record
    assert "upsell_item_id" not in record


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Upsell logic is a prompt-level flag (upsell_enabled), not a structured "
        "decision function. The call pipeline cannot inspect or record what was "
        "suggested. See FINDINGS.md 2026-05-22 — Upsell logic lacks a structured "
        "decision function."
    ),
)
def test_call_session_should_expose_upsell_decision_for_dispatch_expected(
    make_call_session,
):
    """Expected future behavior: post-extraction code can ask the session
    what was suggested so kitchen dispatch / analytics can attribute revenue.
    """
    sess = make_call_session()
    # The expected API — a structured decision per cart state.
    sess.order.items.append(
        type(
            "OI",
            (),
            {
                "name": "Chicken Biryani",
                "menu_item_id": "m_biryani",
                "category": "Mains",
                "unit_price": 1699,
                "quantity": 1,
                "modifiers": [],
                "special_instructions": "",
                "allergens": [],
                "subtotal": 1699,
            },
        )()
    )
    suggestion = sess.decide_upsell()  # AttributeError today
    assert suggestion["cuisine"] == "indian"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "decide_upsell does not exist; build_final_call_record cannot include "
        "upsell attribution fields. See FINDINGS.md 2026-05-22."
    ),
)
def test_final_call_record_should_include_upsell_attribution_expected(
    make_call_session,
):
    """Expected: when an upsell is offered the call record reports the
    suggested item id and whether the customer accepted it."""
    sess = make_call_session()
    record = sess.build_final_call_record()
    assert "upsell_offered" in record
    assert "upsell_accepted" in record
    assert "upsell_item_id" in record
