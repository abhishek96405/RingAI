"""Duuutah AI — application-security tests (C4).

The tenant-isolation matrix is the centerpiece: every tenant-keyed
collection is exercised against the eight scenarios documented in the C4
spec (cross-tenant GET 404, LIST scope, UNAUTH 401, UPDATE/DELETE 404,
mass-assignment defence, aggregation scope, WebSocket scope, integration
token isolation).

Other files cover orthogonal security surfaces: auth enforcement on every
protected route, admin-role gates, rate limiting, input validation, CORS,
encryption round-trip, secret-leak protection, demo-mode isolation, OAuth
state token security.

Production code is never modified — bugs go to ``tests/FINDINGS.md`` and
expected behaviour is captured as ``@pytest.mark.xfail(strict=True)``.
"""
