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
# Pre-warm noisy transitive imports.
#
# pipecat 0.0.104 imports the stdlib `audioop` module at package-load time,
# which emits a `DeprecationWarning` under Python 3.11 (audioop is slated
# for removal in Python 3.13). pyproject.toml has
# `filterwarnings = ["error", ...]`, so any warning fired during a test
# becomes an error.
#
# Importing the noisy chain HERE (at conftest top level, before pytest's
# per-test warning filter is installed) lets us silence the warnings once
# and rely on Python's __warningregistry__ to suppress repeats.
#
# Some transformers (5.2) modules also reference `torch` in class-body
# type annotations and fail at class definition with NameError when torch
# is absent. We catch BaseException so those lazy-loaded module bodies
# don't kill conftest import.
# ---------------------------------------------------------------------------
import warnings as _warnings

with _warnings.catch_warnings():
    _warnings.simplefilter("ignore", DeprecationWarning)
    _warnings.simplefilter("ignore", PendingDeprecationWarning)
    _warnings.simplefilter("ignore", UserWarning)
    for _mod in ("audioop", "pipecat", "server", "gemini_service"):
        try:
            __import__(_mod)
        except BaseException:
            pass

# freezegun's freeze_time() iterates every imported module's attributes
# to monkey-patch any datetime references. transformers (5.2) uses lazy
# loading: touching an attribute triggers a submodule import, and
# ``transformers.models.eomt.image_processing_eomt`` references
# ``torch.Tensor`` in a class-body annotation that crashes with NameError
# when torch is absent. Adding transformers to freezegun's ignore list
# stops it from probing into the lazy-import chain.
try:
    import freezegun as _freezegun

    _freezegun.configure(
        extend_ignore_list=[
            "transformers",
            "huggingface_hub",
            "pipecat",
            "torch",
        ]
    )
except Exception:
    pass


# ---------------------------------------------------------------------------
# Constants used across the test suite. Centralised so individual tests do
# not invent ad-hoc tenant IDs that drift apart over time.
# ---------------------------------------------------------------------------

# Re-exported from tests._constants so individual test modules can import the
# same identifiers via a stable, non-conftest path (importing from a conftest
# under pytest 9's importlib mode is unreliable, and the repo root cannot be
# made importable because backend/ has no __init__.py).
from tests._constants import (  # noqa: E402
    TENANT_A_ID,
    TENANT_B_ID,
    TENANT_A_USER_ID,
    TENANT_B_USER_ID,
    TENANT_A_ORG_ID,
    TENANT_B_ORG_ID,
    ADMIN_USER_ID,
)

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
def app(patched_server_db, monkeypatch):
    """The in-process FastAPI app with db swapped to the in-memory store.

    ``server.setup_signal_handlers`` is patched to a no-op for the test
    lifespan: Starlette's TestClient drives the FastAPI lifespan on a worker
    thread, and ``asyncio.add_signal_handler`` refuses to register handlers
    on a non-main-thread event loop, raising ``RuntimeError: set_wakeup_fd
    only works in main thread of the main interpreter``. The production
    issue is logged in tests/FINDINGS.md.
    """
    server = pytest.importorskip("server")
    monkeypatch.setattr(server, "setup_signal_handlers", lambda: None, raising=False)
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
        "id": TENANT_A_USER_ID,
        "sub": TENANT_A_USER_ID,
        "org_id": TENANT_A_ORG_ID,
        "email": "owner@tenant-a.test",
        "restaurant_id": TENANT_A_ID,
    },
    "tenant_b": {
        "id": TENANT_B_USER_ID,
        "sub": TENANT_B_USER_ID,
        "org_id": TENANT_B_ORG_ID,
        "email": "owner@tenant-b.test",
        "restaurant_id": TENANT_B_ID,
    },
    "admin": {
        "id": ADMIN_USER_ID,
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
        token = authorization[len("Bearer ") :].strip()
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
# Membership seeding for integration tests.
# ensure_restaurant_access requires a db.memberships row tying the calling
# user to the restaurant — without it, every authenticated route returns 403.
# The base two_tenant_setup fixture only seeds restaurant docs; this helper
# adds the matching memberships so calling tenant_a's token actually
# resolves to access on TENANT_A_ID's restaurant.
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_tenant_with_memberships(two_tenant_setup):
    """two_tenant_setup + owner memberships for each tenant's user.

    Returns the same dict structure as two_tenant_setup.
    """
    import server  # patched_server_db has already rebound server.db

    await server.db.memberships.insert_one(
        {
            "id": "membership_a",
            "user_id": TENANT_A_USER_ID,
            "restaurant_id": TENANT_A_ID,
            "role": "owner",
            "business_type": "restaurant",
        }
    )
    await server.db.memberships.insert_one(
        {
            "id": "membership_b",
            "user_id": TENANT_B_USER_ID,
            "restaurant_id": TENANT_B_ID,
            "role": "owner",
            "business_type": "restaurant",
        }
    )
    return two_tenant_setup


# ---------------------------------------------------------------------------
# External SDK monkeypatches that work around the autouse
# _block_unknown_outbound_http guard documented in FINDINGS.
# These patch the SDK surface (stripe.checkout.Session.create, telnyx_service
# helpers) directly so tests never reach httpx at all.
# ---------------------------------------------------------------------------


@pytest.fixture
def stripe_sdk_mock(monkeypatch):
    """Stub the Stripe SDK methods server.py exercises.

    Returns a dict the test can inspect to verify what was called.
    Default behavior covers the happy path; tests that need failures override.
    """
    import stripe

    calls: dict = {
        "customer_create": [],
        "checkout_create": [],
        "portal_create": [],
        "invoice_list": [],
        "invoiceitem_create": [],
        "refund_create": [],
        "oauth_token": [],
        "oauth_deauthorize": [],
        "webhook_construct": [],
    }

    class _Obj(dict):
        def __getattr__(self, item):  # pragma: no cover - convenience
            try:
                return self[item]
            except KeyError as exc:
                raise AttributeError(item) from exc

    def _make_customer(**kw):
        calls["customer_create"].append(kw)
        return _Obj(id="cus_test_123", **kw)

    def _make_checkout(**kw):
        calls["checkout_create"].append(kw)
        return _Obj(
            id="cs_test_123", url="https://stripe.test/checkout/cs_test_123", **kw
        )

    def _make_portal(**kw):
        calls["portal_create"].append(kw)
        return _Obj(
            id="bps_test_123", url="https://stripe.test/portal/bps_test_123", **kw
        )

    def _list_invoices(**kw):
        calls["invoice_list"].append(kw)
        return _Obj(auto_paging_iter=lambda: iter([]))

    def _make_invoice_item(**kw):
        calls["invoiceitem_create"].append(kw)
        return _Obj(id="ii_test_123", **kw)

    def _make_refund(**kw):
        calls["refund_create"].append(kw)
        return _Obj(id="re_test_123", **kw)

    def _oauth_token(**kw):
        calls["oauth_token"].append(kw)
        return _Obj(stripe_user_id="acct_test_123")

    def _oauth_deauthorize(**kw):
        calls["oauth_deauthorize"].append(kw)
        return _Obj(stripe_user_id=kw.get("stripe_user_id"))

    def _construct_event(payload, sig_header, secret):
        calls["webhook_construct"].append({"payload": payload, "sig": sig_header})
        import json as _json

        try:
            return (
                _json.loads(payload) if isinstance(payload, (bytes, str)) else payload
            )
        except Exception:
            return {"type": "ping", "data": {"object": {}}}

    monkeypatch.setattr(stripe.Customer, "create", _make_customer, raising=False)
    monkeypatch.setattr(
        stripe.checkout.Session, "create", _make_checkout, raising=False
    )
    monkeypatch.setattr(
        stripe.billing_portal.Session, "create", _make_portal, raising=False
    )
    monkeypatch.setattr(stripe.Invoice, "list", _list_invoices, raising=False)
    monkeypatch.setattr(stripe.InvoiceItem, "create", _make_invoice_item, raising=False)
    monkeypatch.setattr(stripe.Refund, "create", _make_refund, raising=False)
    monkeypatch.setattr(stripe.OAuth, "token", _oauth_token, raising=False)
    monkeypatch.setattr(stripe.OAuth, "deauthorize", _oauth_deauthorize, raising=False)
    monkeypatch.setattr(
        stripe.Webhook, "construct_event", _construct_event, raising=False
    )

    # Ensure stripe.api_key is non-empty so routes don't 400 with "not configured".
    monkeypatch.setattr(stripe, "api_key", "sk_test_fake", raising=False)
    import server as _server

    monkeypatch.setattr(_server.stripe, "api_key", "sk_test_fake", raising=False)

    return calls


@pytest.fixture
def telnyx_sdk_mock(monkeypatch):
    """Stub telnyx_service module-level helpers used by server.py routes.

    Returns a dict the test can inspect.
    """
    import telnyx_service

    calls: dict = {
        "search": [],
        "create_order": [],
        "wait_for_order": [],
        "list_phone_numbers": [],
        "update_phone_number": [],
        "release_phone_number": [],
        "get_number_order": [],
        "hang_up_call": [],
        "answer_call": [],
        "gather_using_speak": [],
        "start_streaming": [],
        "send_sms": [],
    }

    async def _search(country_code="US", area_code=None, limit=5):
        calls["search"].append(
            {"country_code": country_code, "area_code": area_code, "limit": limit}
        )
        return [
            {
                "phone_number": "+15555550100",
                "vanity_format": "(555) 555-0100",
                "region_information": [{"region_name": "California"}],
                "cost_information": {"monthly_cost": "1.00"},
                "features": [{"name": "voice"}, {"name": "sms"}],
            }
        ]

    async def _create_order(
        phone_numbers, connection_id, messaging_profile_id=None, customer_reference=None
    ):
        calls["create_order"].append(
            {
                "phone_numbers": phone_numbers,
                "connection_id": connection_id,
                "customer_reference": customer_reference,
            }
        )
        return {"id": "ord_test_123", "status": "pending"}

    async def _wait_for_order(order_id, timeout_seconds=30):
        calls["wait_for_order"].append({"order_id": order_id})
        return {
            "id": order_id,
            "status": "success",
            "phone_numbers": [{"id": "pn_test_123", "phone_number": "+15555550100"}],
        }

    async def _list_numbers(phone_number=None):
        calls["list_phone_numbers"].append({"phone_number": phone_number})
        return [{"id": "pn_existing_123", "phone_number": phone_number}]

    async def _update_pn(phone_number_id, **kw):
        calls["update_phone_number"].append({"id": phone_number_id, **kw})
        return {"id": phone_number_id}

    async def _release_pn(phone_number_id):
        calls["release_phone_number"].append({"id": phone_number_id})
        return True

    async def _get_order(order_id):
        calls["get_number_order"].append({"id": order_id})
        return {"id": order_id, "status": "success"}

    async def _hangup(call_id):
        calls["hang_up_call"].append(call_id)

    async def _answer(call_id, client_state=None):
        calls["answer_call"].append({"call_id": call_id, "client_state": client_state})

    async def _gather(call_control_id, **kw):
        calls["gather_using_speak"].append({"call_id": call_control_id, **kw})

    async def _stream(call_id, ws_url):
        calls["start_streaming"].append({"call_id": call_id, "ws_url": ws_url})

    class _SmsResult:
        def __init__(self):
            self.success = True
            self.message_id = "msg_test_123"
            self.error_code = None
            self.error_message = None

    async def _send_sms(**kw):
        calls["send_sms"].append(kw)
        return _SmsResult()

    monkeypatch.setattr(
        telnyx_service, "search_available_numbers", _search, raising=False
    )
    monkeypatch.setattr(
        telnyx_service, "create_number_order", _create_order, raising=False
    )
    monkeypatch.setattr(
        telnyx_service, "wait_for_order_completion", _wait_for_order, raising=False
    )
    monkeypatch.setattr(
        telnyx_service, "list_phone_numbers", _list_numbers, raising=False
    )
    monkeypatch.setattr(
        telnyx_service, "update_phone_number", _update_pn, raising=False
    )
    monkeypatch.setattr(
        telnyx_service, "release_phone_number", _release_pn, raising=False
    )
    monkeypatch.setattr(telnyx_service, "get_number_order", _get_order, raising=False)
    monkeypatch.setattr(telnyx_service, "hang_up_call", _hangup, raising=False)
    monkeypatch.setattr(telnyx_service, "answer_call", _answer, raising=False)
    monkeypatch.setattr(telnyx_service, "gather_using_speak", _gather, raising=False)
    monkeypatch.setattr(telnyx_service, "start_streaming", _stream, raising=False)
    monkeypatch.setattr(telnyx_service, "send_sms", _send_sms, raising=False)
    monkeypatch.setattr(
        telnyx_service, "_get_voice_app_id", lambda: "voice_app_test", raising=False
    )
    monkeypatch.setattr(
        telnyx_service,
        "_get_messaging_profile_id",
        lambda: "msg_profile_test",
        raising=False,
    )
    monkeypatch.setattr(
        telnyx_service, "verify_webhook_signature", lambda *a, **k: True, raising=False
    )
    return calls


@pytest.fixture
def disable_outbound_http_guard(monkeypatch):
    """Disable the autouse _block_unknown_outbound_http guard for a test.

    Use this in tests that explicitly mock httpx via monkeypatch and would
    otherwise be blocked. Per FINDINGS, the guard is incompatible with respx.
    """
    import httpx

    # Restore unwrapped send so test-level patches can take effect.
    # We do this by setting send back to the underlying method object.
    real_async = httpx.AsyncClient.__dict__.get("send")
    real_sync = httpx.Client.__dict__.get("send")
    if real_async is not None:
        monkeypatch.setattr(httpx.AsyncClient, "send", real_async, raising=False)
    if real_sync is not None:
        monkeypatch.setattr(httpx.Client, "send", real_sync, raising=False)


# ---------------------------------------------------------------------------
# Plan-aware seeding — many routes gate features on the restaurant's plan
# (auto-learning, multi-voice, upsell). PRO is the most-featureful plan.
# ---------------------------------------------------------------------------


@pytest.fixture
async def pro_plan_tenant_a(two_tenant_with_memberships):
    """Bump tenant A's restaurant to PRO so plan-gated routes are exercisable."""
    import server

    await server.db.restaurants.update_one(
        {"id": TENANT_A_ID},
        {"$set": {"plan": "PRO", "is_active": True}},
    )
    return two_tenant_with_memberships


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


# ---------------------------------------------------------------------------
# Pre-warm pipecat / server imports.
#
# pipecat 0.0.104 imports the stdlib `audioop` module at package load time
# under Python 3.11, which emits a `DeprecationWarning: 'audioop' is
# deprecated and slated for removal in Python 3.13`. pyproject.toml has
# `filterwarnings = ["error", ...]`, so when this warning fires during a
# test it becomes an error. The warning fires only once per process
# (Python suppresses repeats via __warningregistry__), so we import the
# transitive chain at session start — before pytest's warning filter
# captures per-test warnings — and explicitly swallow it here.
# ---------------------------------------------------------------------------
