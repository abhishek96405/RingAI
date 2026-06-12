"""Square OAuth token exchange (A5-3)."""
from __future__ import annotations

import httpx
import pytest

pytestmark = [pytest.mark.unit]


async def test_exchange_square_code_happy_path(monkeypatch):
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app")
    monkeypatch.setenv("SQUARE_APPLICATION_SECRET", "secret")
    import pos_sync

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"access_token": "sq_AT", "refresh_token": "sq_RT", "merchant_id": "M1"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    out = await pos_sync.exchange_square_code("the-code", "https://app.test/cb")
    assert out["access_token"] == "sq_AT"
    assert out["merchant_id"] == "M1"


async def test_exchange_square_code_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app")
    monkeypatch.setenv("SQUARE_APPLICATION_SECRET", "secret")
    import pos_sync

    async def fake_post(self, url, **kwargs):
        return httpx.Response(400, text="bad code")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(ValueError):
        await pos_sync.exchange_square_code("bad", "https://app.test/cb")


async def test_exchange_square_code_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SQUARE_APPLICATION_ID", raising=False)
    monkeypatch.delenv("SQUARE_APPLICATION_SECRET", raising=False)
    import pos_sync
    with pytest.raises(ValueError):
        await pos_sync.exchange_square_code("c", "https://x")


async def test_exchange_square_code_uses_sandbox_base_when_env_is_sandbox(monkeypatch):
    monkeypatch.setenv("SQUARE_APPLICATION_ID", "app")
    monkeypatch.setenv("SQUARE_APPLICATION_SECRET", "secret")
    monkeypatch.setenv("SQUARE_ENVIRONMENT", "sandbox")
    import pos_sync

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["url"] = url
        return httpx.Response(200, json={"access_token": "sq_AT", "merchant_id": "M1"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await pos_sync.exchange_square_code("the-code", "https://app.test/cb")
    assert "connect.squareupsandbox.com" in captured["url"]
