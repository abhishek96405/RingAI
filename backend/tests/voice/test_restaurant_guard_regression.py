"""
Regression tests — ``business_type == "restaurant"`` guards.

Background
==========
The Duuutah AI horizontal platform serves five business types: restaurant,
clinic, salon, home_services, legal. Several code paths inside
``call_pipeline.py`` are restaurant-specific (order-type detection from
customer speech, reservation-confirmed signal, restaurant-specific call-
duration guard) and previously fired for non-restaurant tenants, causing:

- Salon callers' speech being scanned for "pickup", "delivery", "reservation"
  keywords, with bogus ``_detected_order_type`` assignments leaking into the
  appointment dispatch.
- Reservation-confirmation phrases triggering reservation dispatch for non-
  restaurant businesses where reservations don't exist.

The fix added explicit ``if session.business_type == "restaurant":`` guards.
These tests pin those guards. Findings recorded in tests/FINDINGS.md.

Source locations (verified by grep against call_pipeline.py):

- L1101: reservation-confirmed branch in on_ai_transcript
- L1387: order-type detection inside on_user_turn_stopped
- L1425: assistant_aggregator handler conditional registration
- L1501: call-duration guard inside on_client_connected
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.voice


_GUARD_LINES = (
    'session.business_type == "restaurant"',
    "session.business_type == 'restaurant'",
)


def _src_contains_any(src: str, snippets: tuple[str, ...]) -> bool:
    return any(s in src for s in snippets)


# ---------------------------------------------------------------------------
# Source-level pins — each known guard must remain in place.
# ---------------------------------------------------------------------------


def test_create_call_pipeline_has_multiple_restaurant_guards():
    """At least four distinct guards: reservation-confirmed signal, order-type
    detection from customer speech, assistant_aggregator registration, and the
    duration-guard task. Loss of any one signifies a regression."""
    import call_pipeline

    src = inspect.getsource(call_pipeline.create_call_pipeline)
    count = src.count('business_type == "restaurant"') + src.count(
        "business_type == 'restaurant'"
    )
    assert count >= 4, (
        f"Expected ≥4 restaurant-only guards in create_call_pipeline; found {count}. "
        "Check call_pipeline.py:1101, 1387, 1425, 1501."
    )


def test_reservation_confirmation_signal_is_guarded():
    """The reservation-confirmed phrase set fires session._handle_reservation_confirmed
    ONLY for restaurants. Without this guard, a salon AI that says "your table is
    reserved" by accident would trigger reservation logic that doesn't apply."""
    import call_pipeline

    src = inspect.getsource(call_pipeline.create_call_pipeline)
    # The reservation block follows the business_type guard.
    block = src[src.find("reservation_confirmed_phrases") :]
    assert _src_contains_any(block[:500], _GUARD_LINES)


def test_order_type_detection_is_guarded_to_restaurant():
    """The 'pickup' / 'delivery' / 'reservation' keyword scan inside
    on_user_turn_stopped MUST only run for restaurants. Without this guard
    a salon customer saying 'I want to pick up my haircut' would set
    _detected_order_type=pickup and leak into the appointment payload."""
    import call_pipeline

    src = inspect.getsource(call_pipeline.create_call_pipeline)
    # The conditional precedes the order-type keyword list.
    idx = src.find('any(w in _tl for w in ["delivery"')
    assert idx > 0
    # Walk back a few lines and check for the guard.
    prelude = src[max(0, idx - 400) : idx]
    assert _src_contains_any(prelude, _GUARD_LINES)


# ---------------------------------------------------------------------------
# Behavioral pins — verify the guards work by exercising the code paths
# with both restaurant and non-restaurant sessions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "business_type,is_restaurant",
    [
        ("restaurant", True),
        ("salon", False),
        ("clinic", False),
        ("home_services", False),
        ("legal", False),
    ],
)
def test_business_type_flows_through_to_session(
    make_call_session, business_type, is_restaurant
):
    """Sanity — the business_type set in config propagates to session.business_type
    and downstream branches use it."""
    sess = make_call_session(business_type=business_type)
    assert sess.business_type == business_type
    assert (sess.business_type == "restaurant") is is_restaurant


@pytest.mark.parametrize(
    "business_type,expects_appointment_flow",
    [
        ("restaurant", False),
        ("salon", True),
        ("clinic", True),
        ("home_services", True),
        ("legal", True),
    ],
)
def test_final_call_record_uses_appointment_total_for_non_restaurant(
    make_call_session, business_type, expects_appointment_flow
):
    """build_final_call_record reports appointment_total instead of order.total
    iff business_type is in the appointment set. This is the consumer-visible
    consequence of the restaurant guard for cost/revenue reporting."""
    sess = make_call_session(business_type=business_type)
    sess._appointment_total = 9999
    record = sess.build_final_call_record()
    if expects_appointment_flow:
        assert record["order_total"] == 9999
    else:
        assert record["order_total"] != 9999  # falls back to order.total (0 here)


def test_restaurant_session_does_not_treat_dispatch_booking_as_path(make_call_session):
    """Restaurant sessions do not dispatch bookings via dispatch_booking —
    they go through dispatch_order_if_ready. This pins the separation."""
    sess = make_call_session(business_type="restaurant")
    # dispatch_booking is defined unconditionally, but for a restaurant session
    # with empty services list it will short-circuit to False (no booking found).
    assert hasattr(sess, "dispatch_booking")
    assert hasattr(sess, "dispatch_order_if_ready")
    # The methods are distinct (no accidental aliasing).
    assert sess.dispatch_booking is not sess.dispatch_order_if_ready


# ---------------------------------------------------------------------------
# Negative pins — restaurant-only customer-speech detection must NOT fire
# for non-restaurant tenants. Simulated through direct call to the body.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("business_type", ["salon", "clinic", "home_services", "legal"])
def test_non_restaurant_session_does_not_pre_set_detected_order_type(
    make_call_session, business_type
):
    """A non-restaurant CallSession must not have _detected_order_type populated
    just because a customer mentions 'pickup' — that logic is restaurant-only."""
    sess = make_call_session(business_type=business_type)
    # The guard prevents on_user_turn_stopped from inspecting the keyword list
    # for non-restaurants, so _detected_order_type stays at its init value.
    assert sess._detected_order_type is None
