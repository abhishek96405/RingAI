"""
Delivery Utilities for Duuutah AI

Provides:
- Delivery eligibility checks (ZIP allowlist + Google Maps distance) for delivery orders.

B5-26/C21-1: this module fails CLOSED. When eligibility cannot be confirmed
(no ZIP allowlist configured AND the distance check is unavailable), the result is
allowed=False with verified=False — the caller must not dispatch a delivery it
could not confirm. A configured delivery_zip_codes allowlist is enforced
deterministically and needs no API.
"""
import os
import re
import logging
import httpx
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")


def _extract_zip(text: str) -> Optional[str]:
    """Return the last US 5-digit ZIP found in `text` (ignoring any +4), or None.

    The ZIP is typically the trailing token of an address ("... Plainfield, IL
    60544"), so we take the LAST 5-digit group to avoid grabbing a street number.
    """
    if not text:
        return None
    matches = re.findall(r"\b(\d{5})(?:-\d{4})?\b", text)
    return matches[-1] if matches else None


def _normalize_zip_allowlist(zips: Optional[List[str]]) -> set:
    """Normalize configured ZIPs to bare 5-digit strings for comparison."""
    out = set()
    for z in (zips or []):
        z5 = _extract_zip(z) or (z or "").strip()
        if z5:
            out.add(z5[:5])
    return out


async def validate_delivery_distance(
    restaurant_address: str,
    delivery_address: str,
    max_radius_miles: float = 5.0,
    delivery_zip_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Decide whether a delivery address is eligible. Called post-call.

    Resolution order:
      1. ZIP allowlist (deterministic, no API). If delivery_zip_codes is set, the
         customer's ZIP must be in it. Authoritative — a restaurant that lists its
         delivery ZIPs needs no distance check.
      2. Distance check via Google Maps (only when no ZIP allowlist is configured).

    Returns:
      allowed:        bool — final decision. FAIL-CLOSED: False whenever we cannot
                      confirm the address is deliverable.
      verified:       bool — True only when the outcome was conclusively determined
                      (ZIP match/mismatch, or a successful distance computation).
                      False means "could not check" — the caller should hold the
                      order for manual review, not dispatch it.
      reason:         str  — machine-readable outcome.
      distance_miles: float | None
      distance_text / duration_text: present on a successful distance check.
    """
    # ── 1. ZIP allowlist (deterministic) ─────────────────────────────────
    allow = _normalize_zip_allowlist(delivery_zip_codes)
    if allow:
        cust_zip = _extract_zip(delivery_address)
        if not cust_zip:
            logger.warning("Delivery ZIP allowlist set but no ZIP in address — failing closed")
            return {"allowed": False, "verified": False, "distance_miles": None, "reason": "zip_unparseable"}
        if cust_zip in allow:
            return {"allowed": True, "verified": True, "distance_miles": None, "reason": "zip_allowed"}
        logger.info(f"Delivery ZIP {cust_zip} not in allowlist {sorted(allow)}")
        return {"allowed": False, "verified": True, "distance_miles": None, "reason": "zip_not_allowed"}

    # ── 2. Distance check (no allowlist configured) ──────────────────────
    api_key = GOOGLE_MAPS_API_KEY or os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        logger.warning("Google Maps API key not set and no ZIP allowlist — cannot verify, failing closed")
        return {"allowed": False, "verified": False, "distance_miles": None, "reason": "no_api_key"}

    if not restaurant_address or not delivery_address:
        return {"allowed": False, "verified": False, "distance_miles": None, "reason": "missing_address"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins": restaurant_address,
                    "destinations": delivery_address.replace(". ", ", ").rstrip("."),
                    "units": "imperial",
                    "key": api_key,
                },
            )

            if resp.status_code != 200:
                logger.error(f"Google Maps API error: {resp.status_code}")
                return {"allowed": False, "verified": False, "distance_miles": None, "reason": "api_error"}

            data = resp.json()
            rows = data.get("rows", [])
            if not rows or not rows[0].get("elements"):
                logger.warning(f"Distance Matrix no rows/elements: {data}")
                return {"allowed": False, "verified": False, "distance_miles": None, "reason": "no_results"}

            element = rows[0]["elements"][0]
            if element.get("status") != "OK":
                logger.warning(f"Distance matrix status: {element.get('status')}")
                return {"allowed": False, "verified": False, "distance_miles": None, "reason": element.get("status")}

            distance_meters = element["distance"]["value"]
            distance_miles = round(distance_meters / 1609.34, 1)
            within = distance_miles <= max_radius_miles

            logger.info(
                f"Delivery distance: {distance_miles} miles "
                f"(max: {max_radius_miles}) — {'OK' if within else 'OUT OF RANGE'}"
            )

            return {
                "allowed": within,
                "verified": True,
                "distance_miles": distance_miles,
                "distance_text": element["distance"]["text"],
                "duration_text": element.get("duration", {}).get("text", ""),
                "reason": "within_radius" if within else "outside_radius",
            }

    except Exception as e:
        logger.error(f"Distance validation error: {e}")
        return {"allowed": False, "verified": False, "distance_miles": None, "reason": str(e)}
