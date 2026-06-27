"""PL-17/18: encryption key is dedicated + required, and encrypt fails closed."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_encrypt_decrypt_roundtrip():
    import encryption_utils
    token = "clover-api-token-abc123"
    enc = encryption_utils.encrypt_value(token)
    assert enc.startswith("enc:")
    assert enc != token
    assert encryption_utils.decrypt_value(enc) == token


def test_get_encryption_key_requires_dedicated_key(monkeypatch):
    import encryption_utils
    # Force re-derivation, then remove the dedicated key. monkeypatch restores
    # both the cached global and the env var afterward (pytest-randomly safe).
    monkeypatch.setattr(encryption_utils, "_ENCRYPTION_KEY", None)
    monkeypatch.delenv("ENCRYPTION_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encryption_utils._get_encryption_key()


def test_encrypt_value_fails_closed(monkeypatch):
    import encryption_utils
    # If encryption raises, encrypt_value must propagate — never return plaintext.
    def _boom():
        raise RuntimeError("fernet unavailable")
    monkeypatch.setattr(encryption_utils, "get_fernet", _boom)
    with pytest.raises(RuntimeError):
        encryption_utils.encrypt_value("super-secret")
