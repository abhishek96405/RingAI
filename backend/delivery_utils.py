"""
Delivery Utilities for Duuutah AI

Provides:
- Post-call delivery address distance validation via Google Maps
"""
import os
import logging
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")


async def validate_delivery_distance(
    restaurant_address: str,
    delivery_address: str,
    max_radius_miles: float = 5.0,
) -> Dict[str, Any]:
    """
    Validate delivery address is within radius using Google Maps Distance Matrix API.
    Called post-call, not during the call.
    """
    api_key = GOOGLE_MAPS_API_KEY or os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        logger.warning("Google Maps API key not set — skipping distance validation")
        return {"within_radius": True, "distance_miles": None, "reason": "no_api_key"}

    if not restaurant_address or not delivery_address:
        return {"within_radius": True, "distance_miles": None, "reason": "missing_address"}

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
                return {"within_radius": True, "distance_miles": None, "reason": "api_error"}

            data = resp.json()
            rows = data.get("rows", [])
            if not rows or not rows[0].get("elements"):
                return {"within_radius": True, "distance_miles": None, "reason": "no_results"}

            element = rows[0]["elements"][0]
            logger.info(f"Distance Matrix response: origins={data.get('origin_addresses')}, destinations={data.get('destination_addresses')}, element={element}")
            if element.get("status") != "OK":
                logger.warning(f"Distance matrix status: {element.get('status')}")
                return {"within_radius": True, "distance_miles": None, "reason": element.get("status")}

            # Distance in meters → miles
            distance_meters = element["distance"]["value"]
            distance_miles = round(distance_meters / 1609.34, 1)

            within = distance_miles <= max_radius_miles

            logger.info(
                f"Delivery distance: {distance_miles} miles "
                f"(max: {max_radius_miles}) — {'OK' if within else 'OUT OF RANGE'}"
            )

            return {
                "within_radius": within,
                "distance_miles": distance_miles,
                "distance_text": element["distance"]["text"],
                "duration_text": element.get("duration", {}).get("text", ""),
            }

    except Exception as e:
        logger.error(f"Distance validation error: {e}")
        return {"within_radius": True, "distance_miles": None, "reason": str(e)}