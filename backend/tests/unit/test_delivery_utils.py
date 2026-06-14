"""
Unit tests for backend/delivery_utils.py.

No network I/O, no real Mongo, no filesystem writes. All external collaborators
are mocked.

B5-26/C21-1: validate_delivery_distance now FAILS CLOSED and enforces the
delivery_zip_codes allowlist. Contract is {allowed, verified, reason,
distance_miles}: allowed is the dispatch decision (False when unconfirmable),
verified distinguishes a conclusive out-of-area result from a "couldn't check".

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.unit


def _patch_get(monkeypatch, response_factory):
    async def fake_get(self, url, **kwargs):
        req = httpx.Request("GET", url, params=kwargs.get("params"))
        if callable(response_factory):
            result = response_factory(req)
            if isinstance(result, BaseException):
                raise result
            return result
        return response_factory

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def _reload():
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)
    return delivery_utils


# ---------------------------------------------------------------------------
# ZIP allowlist — deterministic, no API
# ---------------------------------------------------------------------------

async def test_zip_in_allowlist_is_allowed_without_api(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    delivery_utils = _reload()
    # No HTTP patch — must NOT call the API when the ZIP allowlist resolves it.
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="456 Oak St, Plainfield, IL 60544",
        delivery_zip_codes=["60544", "60540"],
    )
    assert result["allowed"] is True
    assert result["verified"] is True
    assert result["reason"] == "zip_allowed"


async def test_zip_not_in_allowlist_is_rejected_and_verified(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    delivery_utils = _reload()
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="9 Far Away Rd, Chicago, IL 60601",
        delivery_zip_codes=["60544", "60540"],
    )
    assert result["allowed"] is False
    assert result["verified"] is True
    assert result["reason"] == "zip_not_allowed"


async def test_zip_allowlist_set_but_no_zip_in_address_fails_closed(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    delivery_utils = _reload()
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="the blue house on the corner",
        delivery_zip_codes=["60544"],
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert result["reason"] == "zip_unparseable"


async def test_zip_allowlist_normalizes_plus_four_and_spacing(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    delivery_utils = _reload()
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="456 Oak St, Naperville, IL 60540-1234",
        delivery_zip_codes=[" 60540 ", "60544"],
    )
    assert result["allowed"] is True
    assert result["reason"] == "zip_allowed"


# ---------------------------------------------------------------------------
# Distance check (no allowlist) — fail CLOSED on every error
# ---------------------------------------------------------------------------

async def test_no_api_key_and_no_allowlist_fails_closed(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    delivery_utils = _reload()
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St", delivery_address="456 Oak St",
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert result["reason"] == "no_api_key"


async def test_missing_address_fails_closed(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="", delivery_address="456 Oak St",
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert result["reason"] == "missing_address"


async def test_within_radius_allowed(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{
            "status": "OK",
            "distance": {"value": 4827, "text": "3.0 mi"},   # ~3.0 miles
            "duration": {"value": 600, "text": "10 mins"},
        }]}],
    }))
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St", delivery_address="456 Oak St", max_radius_miles=5.0,
    )
    assert result["allowed"] is True
    assert result["verified"] is True
    assert result["distance_miles"] == 3.0
    assert result["distance_text"] == "3.0 mi"
    assert result["duration_text"] == "10 mins"
    assert result["reason"] == "within_radius"


async def test_over_radius_rejected_and_verified(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{
            "status": "OK",
            "distance": {"value": 16093, "text": "10 mi"},   # ~10 miles
            "duration": {"value": 1200, "text": "20 mins"},
        }]}],
    }))
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B", max_radius_miles=5.0,
    )
    assert result["allowed"] is False
    assert result["verified"] is True
    assert result["distance_miles"] == 10.0
    assert result["reason"] == "outside_radius"


async def test_non_200_fails_closed(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    _patch_get(monkeypatch, httpx.Response(500, text="server error"))
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B",
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert result["reason"] == "api_error"


async def test_empty_rows_fails_closed(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    _patch_get(monkeypatch, httpx.Response(200, json={"rows": []}))
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B",
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert result["reason"] == "no_results"


@pytest.mark.parametrize("element_status", ["NOT_FOUND", "ZERO_RESULTS", "MAX_ELEMENTS_EXCEEDED"])
async def test_element_level_failure_fails_closed(monkeypatch, element_status):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{"status": element_status}]}],
    }))
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B",
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert result["reason"] == element_status


async def test_network_exception_fails_closed(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()

    async def boom(self, *args, **kwargs):
        raise httpx.ConnectError("net down")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B",
    )
    assert result["allowed"] is False
    assert result["verified"] is False
    assert "reason" in result


async def test_empty_allowlist_falls_through_to_distance(monkeypatch):
    """An empty/None allowlist must NOT short-circuit — distance check runs."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{
            "status": "OK",
            "distance": {"value": 1609, "text": "1.0 mi"},
            "duration": {"value": 120, "text": "2 mins"},
        }]}],
    }))
    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B 60540", delivery_zip_codes=[],
    )
    assert result["allowed"] is True
    assert result["reason"] == "within_radius"


# ---------------------------------------------------------------------------
# Delivery address normalisation — sanity-check the ". " → ", " hack
# ---------------------------------------------------------------------------

async def test_delivery_address_normalisation(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    delivery_utils = _reload()
    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["destinations"] = (kwargs.get("params") or {}).get("destinations")
        return httpx.Response(200, json={
            "rows": [{"elements": [{
                "status": "OK",
                "distance": {"value": 1000, "text": "0.6 mi"},
                "duration": {"value": 120, "text": "2 mins"},
            }]}],
        })

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St", delivery_address="456 Oak St. Apt 5.",
    )
    assert captured["destinations"] == "456 Oak St, Apt 5"
