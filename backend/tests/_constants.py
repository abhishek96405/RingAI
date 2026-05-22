"""
Tenant identifiers and other shared constants used across the test suite.

These live in a dedicated module (not in conftest.py) so that test files can
import them with a stable, unambiguous path without triggering pytest's
conftest-loading machinery.

A leading underscore in the filename signals "test-internal" and prevents
pytest from trying to collect tests from this file.
"""
from __future__ import annotations


TENANT_A_ID = "tenant_a_restaurant"
TENANT_B_ID = "tenant_b_restaurant"

TENANT_A_USER_ID = "user_tenant_a"
TENANT_B_USER_ID = "user_tenant_b"

TENANT_A_ORG_ID = "org_tenant_a"
TENANT_B_ORG_ID = "org_tenant_b"

ADMIN_USER_ID = "user_admin"
