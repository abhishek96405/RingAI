"""
Root conftest for Duuutah AI backend tests.

Responsibilities:
- Set up an in-memory MongoDB (mongomock-motor) so the in-process FastAPI
  app reads and writes a fresh database per test.
- Provide TestClient and httpx.AsyncClient instances bound to the in-process
  FastAPI app — no network reach to a deployed backend.
- Provide tenant identity headers backed by patched Clerk JWT verification.
- Expose hooks for mocking each external service (Gemini, Telnyx, Stripe,
  Clerk, Google Calendar, Google Maps, Square, Clover). Concrete handlers
  are added by later commits; this file only wires the seams.
- Apply the `live` marker to the two pre-existing test files that hit a
  deployed backend, and exclude them from default collection. Pass
  ``--run-live`` to collect and run them (and only them).

Production code is never modified. Test isolation is achieved entirely
through fixture-level patching and FastAPI dependency overrides.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest

# Make `backend/` importable so `import server`, `import gemini_service`, etc.
# resolve regardless of where pytest is launched from.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ---------------------------------------------------------------------------
# Constants used across the test suite. Centralised so individual tests do
# not invent ad-hoc tenant IDs that drift apart over time.
# ---------------------------------------------------------------------------

TENANT_A_ID = "tenant_a_restaurant"
TENANT_B_ID = "tenant_b_restaurant"

TENANT_A_USER_ID = "user_tenant_a"
TENANT_B_USER_ID = "user_tenant_b"

TENANT_A_ORG_ID = "org_tenant_a"
TENANT_B_ORG_ID = "org_tenant_b"

ADMIN_USER_ID = "user_admin"


# ---------------------------------------------------------------------------
# Custom CLI flag for running live tests against a deployed backend.
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help=(
            "Run only the pre-existing live tests in test_ringai_api.py and "
            "test_test_mode.py against a deployed backend (REACT_APP_BACKEND_URL). "
            "Default test runs exclude these files."
        ),
    )


_LIVE_TEST_FILES = ("test_ringai_api.py", "test_test_mode.py")


def pytest_ignore_collect(collection_path, config: pytest.Config):
    """Skip legacy live-test files at the file-discovery layer.

    Modifying collection later (via ``pytest_collection_modifyitems``) is too
    late — those files import ``requests`` and may fail at import time. We
    ignore them before they are imported.

    Default mode: drop the two legacy files; everything else is collected.
    ``--run-live`` mode: invert — keep ONLY legacy files; everything else
    is ignored.
    """
    name = collection_path.name
    is_live = name in _LIVE_TEST_FILES
    if config.getoption("--run-live"):
        if not collection_path.is_file():
            return False
        if name == "conftest.py":
            return False
        if name.startswith("test_") and not is_live:
            return True
        return False
    return is_live


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Tag any legacy items that made it through with the ``live`` marker."""
    for item in items:
        fpath = str(item.fspath).replace("\\", "/")
        if any(name in fpath for name in _LIVE_TEST_FILES):
            item.add_marker(pytest.mark.live)


# ---------------------------------------------------------------------------
# Async DB — mongomock-motor in-memory replacement for MongoDB.
# Each test gets a fresh database. Production code reads its handle via the
# ``server.db`` module-level binding; the ``patched_server_db`` fixture below
# rebinds it for the lifetime of a test.
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_db():
    """Fresh in-memory async MongoDB instance, isolated per test."""
    pytest.importorskip("mongomock_motor")
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    db = client["duuutah_test"]
    try:
        yield db
    finally:
        # AsyncMongoMockClient has no close(); GC handles it. Drop collections
        # explicitly so subsequent tests cannot observe leftover state if a
        # client instance is unexpectedly reused.
        for name in await db.list_collection_names():
            await db.drop_collection(name)


@pytest.fixture
async def patched_server_db(async_db, monkeypatch):
    """Patch ``server.db`` to point at the in-memory database.

    Yields the same db handle for convenience so tests can assert against it.
    """
    server = pytest.importorskip("server")
    monkeypatch.setattr(server, "db", async_db, raising=True)
    yield async_db


# ---------------------------------------------------------------------------
# App + clients. ``app`` re-imports the FastAPI app and applies dependency
# overrides; ``client`` is a sync TestClient suitable for most route tests;
# ``async_client`` is an httpx.AsyncClient for tests that need async APIs.
# ---------------------------------------------------------------------------

@pytest.fixture
def app(patched_server_db):
    """The in-process FastAPI app with db swapped to the in-memory store."""
    server = pytest.importorskip("server")
    return server.app


@pytest.fixture
def client(app):
    """Sync FastAPI TestClient. Use for synchronous route assertions."""
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client(app) -> AsyncIterator:
    """Async httpx client bound to the in-process app via ASGITransport."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Clerk auth — patch verify_clerk_token to return deterministic claims so
# tests can pass simple tokens like "tenant_a" or "tenant_b" and be treated
# as that user/organisation.
# ---------------------------------------------------------------------------

_TOKEN_TO_CLAIMS: dict[str, dict] = {
    "tenant_a": {
        "sub": TENANT_A_USER_ID,
        "org_id": TENANT_A_ORG_ID,
        "email": "owner@tenant-a.test",
        "restaurant_id": TENANT_A_ID,
    },
    "tenant_b": {
        "sub": TENANT_B_USER_ID,
        "org_id": TENANT_B_ORG_ID,
        "email": "owner@tenant-b.test",
        "restaurant_id": TENANT_B_ID,
    },
    "admin": {
        "sub": ADMIN_USER_ID,
        "org_id": "org_admin",
        "email": "admin@duuutah.test",
        "role": "admin",
    },
}


@pytest.fixture
def mock_clerk(app):
    """Override the FastAPI auth dependency with deterministic claims.

    Tests pass tokens by string key (``tenant_a``, ``tenant_b``, ``admin``)
    in the Authorization header; the override returns the matching claim
    dict directly, bypassing JWKS entirely.

    Why dependency_overrides instead of monkeypatching ``verify_clerk_token``:
    ``server.py`` does ``from auth_helpers import verify_clerk_token`` at
    import time, which binds the function into ``server``'s namespace.
    Patching ``auth_helpers.verify_clerk_token`` afterwards does not affect
    the binding ``server.get_current_user`` already captured. Overriding the
    dependency itself is the idiomatic FastAPI approach and works regardless
    of how the verifier is imported.
    """
    from fastapi import Header, HTTPException

    import server

    async def _fake_get_current_user(authorization: str = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer")
        token = authorization[len("Bearer "):].strip()
        if token in _TOKEN_TO_CLAIMS:
            return dict(_TOKEN_TO_CLAIMS[token])
        raise HTTPException(status_code=401, detail=f"unknown test token: {token}")

    app.dependency_overrides[server.get_current_user] = _fake_get_current_user
    try:
        yield _TOKEN_TO_CLAIMS
    finally:
        app.dependency_overrides.pop(server.get_current_user, None)


@pytest.fixture
def auth_headers_tenant_a(mock_clerk) -> dict[str, str]:
    return {"Authorization": "Bearer tenant_a"}


@pytest.fixture
def auth_headers_tenant_b(mock_clerk) -> dict[str, str]:
    return {"Authorization": "Bearer tenant_b"}


@pytest.fixture
def auth_headers_admin(mock_clerk) -> dict[str, str]:
    return {"Authorization": "Bearer admin"}


# ---------------------------------------------------------------------------
# External-service mock hooks. Each fixture sets up the seam that later test
# files will populate. They are intentionally minimal here — concrete
# response mapping lives in the tests that need it (and in fixtures/*.json).
# ---------------------------------------------------------------------------

@pytest.fixture
def respx_mock():
    """Active respx router for mocking httpx-based outbound calls."""
    import respx

    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def mock_gemini(monkeypatch):
    """Hook for patching Gemini clients. Tests override the returned dict.

    Returns a dict the caller mutates to register fake responses, e.g.::

        mock_gemini["analyse_call_transcript"] = lambda *a, **k: {...}
        monkeypatch.setattr("gemini_service.analyse_call_transcript",
                            mock_gemini["analyse_call_transcript"])
    """
    return {}


@pytest.fixture
def mock_telnyx(respx_mock):
    """Pre-configured respx router scoped to api.telnyx.com.

    Tests register additional routes via ``respx_mock.post(...)`` etc.
    """
    respx_mock.route(host="api.telnyx.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    return respx_mock


@pytest.fixture
def mock_stripe(respx_mock, monkeypatch):
    """Pre-configured respx router scoped to api.stripe.com.

    Stripe 14.x uses ``requests`` for its REST client; tests that rely on
    that path will additionally monkeypatch ``stripe.api_requestor``.
    """
    respx_mock.route(host="api.stripe.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    return respx_mock


@pytest.fixture
def mock_google_calendar(respx_mock):
    """Pre-configured respx router scoped to Google Calendar endpoints."""
    respx_mock.route(host="oauth2.googleapis.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    respx_mock.route(host="www.googleapis.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    return respx_mock


@pytest.fixture
def mock_google_maps(respx_mock):
    respx_mock.route(host="maps.googleapis.com").mock(
        return_value=__import__("httpx").Response(200, json={"results": []})
    )
    return respx_mock


@pytest.fixture
def mock_square(respx_mock):
    respx_mock.route(host="connect.squareup.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    respx_mock.route(host="connect.squareupsandbox.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    return respx_mock


@pytest.fixture
def mock_clover(respx_mock):
    respx_mock.route(host="api.clover.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    respx_mock.route(host="sandbox.dev.clover.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    respx_mock.route(host="apisandbox.dev.clover.com").mock(
        return_value=__import__("httpx").Response(200, json={})
    )
    return respx_mock


# ---------------------------------------------------------------------------
# Time control — freezegun helper that yields the freezer for tick control.
# ---------------------------------------------------------------------------

@pytest.fixture
def frozen_time():
    """Freeze wall clock at a fixed UTC instant; yield the freezer.

    Tests can advance time via ``frozen_time.tick(timedelta(...))``.
    """
    pytest.importorskip("freezegun")
    from freezegun import freeze_time

    with freeze_time("2026-05-21T12:00:00+00:00") as freezer:
        yield freezer


# ---------------------------------------------------------------------------
# Two-tenant fixture — the foundation of tenant-isolation tests. Two
# restaurants are seeded with non-overlapping data so a leak from one to the
# other surfaces as a visible assertion failure.
# ---------------------------------------------------------------------------

@pytest.fixture
async def two_tenant_setup(patched_server_db, mock_clerk):
    """Seed Tenant A and Tenant B with paired, non-overlapping documents.

    Returns a dict with keys ``a`` and ``b``, each carrying the tenant's
    restaurant document plus identifiers used by isolation tests.
    """
    db = patched_server_db

    a_doc = {
        "id": TENANT_A_ID,
        "name": "Tenant A Diner",
        "business_type": "restaurant",
        "owner_user_id": TENANT_A_USER_ID,
        "org_id": TENANT_A_ORG_ID,
    }
    b_doc = {
        "id": TENANT_B_ID,
        "name": "Tenant B Bistro",
        "business_type": "restaurant",
        "owner_user_id": TENANT_B_USER_ID,
        "org_id": TENANT_B_ORG_ID,
    }
    await db.restaurants.insert_one(dict(a_doc))
    await db.restaurants.insert_one(dict(b_doc))

    return {
        "a": {
            "restaurant": a_doc,
            "headers": {"Authorization": "Bearer tenant_a"},
            "user_id": TENANT_A_USER_ID,
            "org_id": TENANT_A_ORG_ID,
        },
        "b": {
            "restaurant": b_doc,
            "headers": {"Authorization": "Bearer tenant_b"},
            "user_id": TENANT_B_USER_ID,
            "org_id": TENANT_B_ORG_ID,
        },
    }


# ---------------------------------------------------------------------------
# Safety net: catch unexpected outbound HTTP. If a test misses a mock and
# tries to reach a real third-party host, we want a loud failure, not a
# silent timeout. Tests that want the network must opt in via ``--run-live``.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _block_unknown_outbound_http(request, monkeypatch):
    """Reject outbound HTTP not explicitly mocked, except for live tests."""
    if request.config.getoption("--run-live"):
        return

    import httpx

    real_send_async = httpx.AsyncClient.send
    real_send_sync = httpx.Client.send

    def _is_in_process(url: httpx.URL) -> bool:
        host = (url.host or "").lower()
        return host in {"testserver", "localhost", "127.0.0.1", ""}

    async def _guarded_async(self, request_obj, *args, **kwargs):
        if not _is_in_process(request_obj.url):
            # respx installs its own transport; if a respx_mock fixture is
            # active, calls go through it instead of here.
            raise RuntimeError(
                f"Unmocked outbound HTTP call to {request_obj.url}. "
                "Add a respx route or use --run-live."
            )
        return await real_send_async(self, request_obj, *args, **kwargs)

    def _guarded_sync(self, request_obj, *args, **kwargs):
        if not _is_in_process(request_obj.url):
            raise RuntimeError(
                f"Unmocked outbound HTTP call to {request_obj.url}. "
                "Add a respx route or use --run-live."
            )
        return real_send_sync(self, request_obj, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", _guarded_async)
    monkeypatch.setattr(httpx.Client, "send", _guarded_sync)
