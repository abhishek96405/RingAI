#!/usr/bin/env python3
"""
Square park-order smoke test.

Decides INCLUDE_FULFILLMENT in gemini_service._park_to_square.

A "parked" order should appear in the seller's Orders list for a human to open,
WITHOUT being routed to the kitchen/KDS. _park_to_square creates an OPEN order
with NO fulfillments by default (INCLUDE_FULFILLMENT=False). But the A7-2 note
says fulfillment-less REST orders may not surface at all. This script creates
one order of each kind so you can see which shows up, and where, in YOUR setup.

Usage:
    export SQUARE_ACCESS_TOKEN=...      # sandbox token
    export SQUARE_LOCATION_ID=...       # sandbox location id
    export SQUARE_ENVIRONMENT=sandbox   # optional, defaults to sandbox
    python backend/scripts/square_park_smoketest.py

Then open Square Dashboard > Orders (and your KDS / Square for Restaurants if
you use one) and note which of the two test orders appear and where:
  - NO-FULFILLMENT order shows in Orders (ideally NOT on the KDS):
        keep INCLUDE_FULFILLMENT = False   (clean: parked, not fired)
  - Only the WITH-FULFILLMENT order shows:
        set INCLUDE_FULFILLMENT = True     (accept it may also hit the KDS)
"""
import os
import sys
import uuid

import httpx

TOKEN = os.environ.get("SQUARE_ACCESS_TOKEN")
LOCATION = os.environ.get("SQUARE_LOCATION_ID")
ENV = os.environ.get("SQUARE_ENVIRONMENT", "sandbox")
BASE = (
    "https://connect.squareupsandbox.com"
    if ENV == "sandbox"
    else "https://connect.squareup.com"
)

if not TOKEN or not LOCATION:
    sys.exit("Set SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID (sandbox) first.")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Square-Version": "2024-01-18",
    "Content-Type": "application/json",
}

LINE_ITEMS = [
    {"name": "SMOKETEST — Park Item A", "quantity": "1",
     "base_price_money": {"amount": 500, "currency": "USD"}},
    {"name": "SMOKETEST — Park Item B", "quantity": "2",
     "base_price_money": {"amount": 750, "currency": "USD"}},
]


def make_order(with_fulfillment: bool) -> httpx.Response:
    order = {
        "location_id": LOCATION,
        "source": {"name": "Duuutah AI — Park SMOKETEST"},
        "state": "OPEN",
        "line_items": LINE_ITEMS,
    }
    if with_fulfillment:
        order["fulfillments"] = [{
            "type": "PICKUP",
            "state": "PROPOSED",
            "pickup_details": {
                "schedule_type": "ASAP",
                "recipient": {"display_name": "Smoke Test"},
            },
        }]
    body = {"idempotency_key": str(uuid.uuid4()), "order": order}
    return httpx.post(f"{BASE}/v2/orders", json=body, headers=HEADERS, timeout=15.0)


def main() -> None:
    for label, wf in [
        ("NO fulfillment  (INCLUDE_FULFILLMENT=False)", False),
        ("WITH fulfillment (INCLUDE_FULFILLMENT=True)", True),
    ]:
        r = make_order(wf)
        if r.status_code == 200:
            oid = r.json().get("order", {}).get("id", "")
            print(f"[OK]   {label}: order_id={oid}")
        else:
            print(f"[FAIL] {label}: {r.status_code} {r.text}")
    print(
        "\nOpen Square Dashboard > Orders (and your KDS if used) and note which "
        "orders appear and where, then set INCLUDE_FULFILLMENT in "
        "gemini_service._park_to_square accordingly."
    )


if __name__ == "__main__":
    main()
