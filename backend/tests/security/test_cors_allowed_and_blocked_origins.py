"""CORS allowlist tests.

server.py reads CORS origins from the ``CORS_ORIGINS`` env var (comma-
separated). The pytest-env block sets it to ``http://localhost:3000``.
These tests verify:
- An origin in the allowlist gets ``Access-Control-Allow-Origin`` echoed.
- An origin outside the allowlist does NOT.
- Credentials mode is on (cookies/Authorization headers can be sent).
- The ``allow_origins=["*"]`` default is a high-priority finding if seen.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.security, pytest.mark.integration]


def test_allowed_origin_is_echoed_in_response_headers(client):
    r = client.options(
        "/api/status",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Preflight returns 200; if not, the GET still echoes origin.
    if r.status_code != 200:
        r = client.get("/api/status", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_disallowed_origin_is_not_echoed(client):
    r = client.get(
        "/api/status",
        headers={"Origin": "https://evil.attacker.test"},
    )
    # CORS middleware either omits the header entirely OR echoes the
    # specific allowed origin (never evil.attacker.test).
    allow = r.headers.get("Access-Control-Allow-Origin", "")
    assert "evil.attacker.test" not in allow


def test_credentials_mode_enabled(client):
    r = client.get(
        "/api/status",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.headers.get("Access-Control-Allow-Credentials", "").lower() == "true"


def test_cors_not_using_wildcard_in_test_env(client):
    """Defence-in-depth: if CORS_ORIGINS is set to "*" alongside
    credentials=true the browser will block the request — but we should
    never even attempt that combo. The pyproject env sets a specific origin;
    this test guards against a regression to the wildcard default."""
    origins_env = os.environ.get("CORS_ORIGINS", "")
    assert "*" not in origins_env, "CORS_ORIGINS contains wildcard"
    r = client.get(
        "/api/status",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.headers.get("Access-Control-Allow-Origin") != "*"
