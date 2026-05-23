"""
Unit tests for backend/delivery_utils.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.

Note on HTTP mocking: see ``tests/FINDINGS.md`` 2026-05-22 for why we
patch ``httpx.AsyncClient.get`` directly rather than using respx_mock.
"""
from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.unit


def _patch_get(monkeypatch, response_factory):
    """Patch httpx.AsyncClient.get to return whatever ``response_factory(request)`` produces.

    ``response_factory`` may either be a callable taking the request URL/params
    and returning an httpx.Response, or a fixed Response (or callable raising).
    """
    async def fake_get(self, url, **kwargs):
        req = httpx.Request("GET", url, params=kwargs.get("params"))
        if callable(response_factory):
            result = response_factory(req)
            if isinstance(result, BaseException):
                raise result
            return result
        return response_factory

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


# ---------------------------------------------------------------------------
# validate_delivery_distance — env-var gating
# ---------------------------------------------------------------------------

async def test_validate_delivery_distance_returns_within_when_api_key_missing(monkeypatch):
    """If no Google Maps API key is configured, validation is skipped optimistically."""
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="456 Oak St",
    )
    assert result["within_radius"] is True
    assert result["reason"] == "no_api_key"


async def test_validate_delivery_distance_returns_within_when_address_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="",
        delivery_address="456 Oak St",
    )
    assert result["within_radius"] is True
    assert result["reason"] == "missing_address"

    result2 = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="",
    )
    assert result2["within_radius"] is True


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_within_radius_returns_true_when_under_max(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    # 4827 meters = ~3.0 miles → under default max 5.0
    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{
            "status": "OK",
            "distance": {"value": 4827, "text": "3.0 mi"},
            "duration": {"value": 600, "text": "10 mins"},
        }]}],
        "origin_addresses": ["123 Main St"],
        "destination_addresses": ["456 Oak St"],
    }))

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="456 Oak St",
        max_radius_miles=5.0,
    )
    assert result["within_radius"] is True
    assert result["distance_miles"] == 3.0
    assert result["distance_text"] == "3.0 mi"
    assert result["duration_text"] == "10 mins"


async def test_within_radius_returns_false_when_over_max(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{
            "status": "OK",
            "distance": {"value": 16093, "text": "10 mi"},  # ~10 miles
            "duration": {"value": 1200, "text": "20 mins"},
        }]}],
    }))

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A",
        delivery_address="B",
        max_radius_miles=5.0,
    )
    assert result["within_radius"] is False
    assert result["distance_miles"] == 10.0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

async def test_handles_non_200_response(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    _patch_get(monkeypatch, httpx.Response(500, text="server error"))

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B"
    )
    assert result["within_radius"] is True
    assert result["reason"] == "api_error"


async def test_handles_empty_rows(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    _patch_get(monkeypatch, httpx.Response(200, json={"rows": []}))

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B"
    )
    assert result["within_radius"] is True
    assert result["reason"] == "no_results"


@pytest.mark.parametrize("element_status", ["NOT_FOUND", "ZERO_RESULTS", "MAX_ELEMENTS_EXCEEDED"])
async def test_handles_element_level_failure(monkeypatch, element_status):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    _patch_get(monkeypatch, httpx.Response(200, json={
        "rows": [{"elements": [{"status": element_status}]}],
    }))

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B"
    )
    assert result["within_radius"] is True
    assert result["reason"] == element_status


async def test_handles_network_exception(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

    async def boom(self, *args, **kwargs):
        raise httpx.ConnectError("net down")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)

    result = await delivery_utils.validate_delivery_distance(
        restaurant_address="A", delivery_address="B"
    )
    # Function catches all exceptions and returns within_radius=True with reason.
    assert result["within_radius"] is True
    assert "reason" in result


# ---------------------------------------------------------------------------
# Delivery address normalisation — sanity-check the ". " → ", " hack
# ---------------------------------------------------------------------------

async def test_delivery_address_normalisation(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    import importlib
    import delivery_utils
    importlib.reload(delivery_utils)

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

    # ". " inside the address should be normalised to ", " before being sent.
    await delivery_utils.validate_delivery_distance(
        restaurant_address="123 Main St",
        delivery_address="456 Oak St. Apt 5.",
    )

    # Trailing dot stripped, ". " → ", "
    assert captured["destinations"] == "456 Oak St, Apt 5"
