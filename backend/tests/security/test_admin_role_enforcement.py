"""Admin-role enforcement.

server.py defines two admin-namespaced routes:

- ``POST /api/admin/process-reminders`` (server.py:1796)
- ``GET /api/admin/cost-analytics``      (server.py:4206)

Only ``cost-analytics`` actually compares ``user.id`` against
``ADMIN_USER_ID``. The reminders endpoint accepts ANY authenticated user
— captured here as an xfail strict finding.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security, pytest.mark.integration]


def test_admin_cost_analytics_rejects_non_admin(client, mock_clerk):
    r = client.get(
        "/api/admin/cost-analytics",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 403


def test_admin_cost_analytics_accepts_admin_token(client, mock_clerk):
    r = client.get(
        "/api/admin/cost-analytics",
        headers={"Authorization": "Bearer admin"},
    )
    assert r.status_code == 200


def test_admin_cost_analytics_rejects_unauth(client):
    r = client.get("/api/admin/cost-analytics")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# process-reminders: currently accepts ANY authenticated user — finding.
# ---------------------------------------------------------------------------


def test_admin_process_reminders_rejects_non_admin(client, mock_clerk):
    """/api/admin/process-reminders now enforces admin-id check (FINDINGS resolved)."""
    r = client.post(
        "/api/admin/process-reminders",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 403


def test_admin_process_reminders_rejects_non_admin_expected(client, mock_clerk):
    r = client.post(
        "/api/admin/process-reminders",
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 403
