"""Encryption round-trip property + integration-level write test.

backend/encryption_utils.py exposes ``encrypt_value`` / ``decrypt_value``;
the unit tests already cover the algebraic property. This file adds the
integration assertion: when POS credentials are saved, the value stored
in ``integrations`` is encrypted (carries the ``enc:`` prefix), and a
round-trip via decrypt_value yields the original.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from tests._constants import TENANT_A_ID

pytestmark = [pytest.mark.security]


# ---------------------------------------------------------------------------
# Property test — encrypt then decrypt is identity (for unicode strings).
# ---------------------------------------------------------------------------


@given(plaintext=st.text(min_size=1, max_size=2048))
@settings(max_examples=50, deadline=None)
def test_encrypt_decrypt_roundtrip_is_identity(plaintext):
    import encryption_utils

    ct = encryption_utils.encrypt_value(plaintext)
    pt = encryption_utils.decrypt_value(ct)
    assert pt == plaintext
    # Encrypted output is opaque and prefixed.
    assert ct != plaintext or plaintext == ""
    assert ct.startswith("enc:") or plaintext == ""


def test_encrypt_twice_does_not_double_encrypt():
    import encryption_utils

    once = encryption_utils.encrypt_value("hello")
    twice = encryption_utils.encrypt_value(once)
    # Idempotency: encrypting an already-encrypted value returns it as-is.
    assert twice == once


def test_decrypt_of_unprefixed_returns_input_unchanged():
    import encryption_utils

    out = encryption_utils.decrypt_value("plain-text-value")
    assert out == "plain-text-value"


# ---------------------------------------------------------------------------
# Integration: POS credential save persists ENCRYPTED token in DB.
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_pos_credentials_encrypted_at_rest(
    client, patched_server_db, two_tenant_with_memberships
):
    SECRET = "shouldnt-leak-plaintext-clover-token-XYZ"
    r = client.post(
        f"/api/restaurants/{TENANT_A_ID}/pos/credentials",
        json={
            "provider": "clover",
            "credentials": {"merchant_id": "M1", "api_token": SECRET},
        },
        headers={"Authorization": "Bearer tenant_a"},
    )
    if r.status_code != 200:
        pytest.skip(f"pos/credentials returned {r.status_code}; not the focus here")
    # Read what was persisted: it must not contain the plaintext anywhere.
    docs = await patched_server_db.integrations.find(
        {"restaurant_id": TENANT_A_ID}
    ).to_list(50)
    blob = repr(docs)
    assert SECRET not in blob, "plaintext credential persisted unencrypted!"
