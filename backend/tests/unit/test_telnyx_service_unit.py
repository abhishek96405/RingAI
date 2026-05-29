"""
Unit tests for backend/telnyx_service.py.

These tests have no network I/O, no real Mongo, no filesystem writes
(except via tmp_path). All external collaborators are mocked.

Coverage target for this module: >= 85%.
"""
from __future__ import annotations

import base64
import time

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

pytestmark = pytest.mark.unit


def _resp(status_code, json=None, text=None, headers=None, url="https://api.telnyx.com/v2/x"):
    """Build an httpx.Response with a request attached so raise_for_status works."""
    return httpx.Response(
        status_code=status_code,
        json=json,
        text=text,
        headers=headers or {},
        request=httpx.Request("POST", url),
    )


# ---------------------------------------------------------------------------
# _validate_e164
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("number,expected", [
    ("+15551234567", True),
    ("+447946000000", True),
    ("+1234567890", True),
    ("+12345678901234", True),  # 14 digits, max
    ("", False),
    ("5551234567", False),
    ("+1", False),  # too short
    ("+1234567890123456789", False),  # too long
    ("+notdigits", False),
    (None, False),
])
def test_validate_e164(number, expected):
    from telnyx_service import _validate_e164
    assert _validate_e164(number) is expected


# ---------------------------------------------------------------------------
# SMSResult
# ---------------------------------------------------------------------------

def test_sms_result_truthy_when_success():
    from telnyx_service import SMSResult
    assert bool(SMSResult(success=True, message_id="m"))


def test_sms_result_falsy_when_failure():
    from telnyx_service import SMSResult
    assert not bool(SMSResult(success=False, error_code="X", error_message="boom"))


# ---------------------------------------------------------------------------
# set_sms_persister
# ---------------------------------------------------------------------------

def test_set_sms_persister_registers_callable():
    import telnyx_service

    async def fake_persister(record):
        pass

    telnyx_service.set_sms_persister(fake_persister)
    assert telnyx_service._sms_persister is fake_persister

    # Cleanup
    telnyx_service.set_sms_persister(None)
    assert telnyx_service._sms_persister is None


# ---------------------------------------------------------------------------
# send_sms — validation paths
# ---------------------------------------------------------------------------

async def test_send_sms_rejects_invalid_e164(monkeypatch):
    from telnyx_service import send_sms

    result = await send_sms(to="5551234567", body="hi")
    assert result.success is False
    assert result.error_code == "INVALID_PHONE"


async def test_send_sms_rejects_empty_body():
    from telnyx_service import send_sms
    result = await send_sms(to="+15551234567", body="")
    assert result.success is False
    assert result.error_code == "EMPTY_BODY"


async def test_send_sms_rejects_overlong_body():
    from telnyx_service import send_sms
    result = await send_sms(to="+15551234567", body="x" * 2000)
    assert result.success is False
    assert result.error_code == "BODY_TOO_LONG"


async def test_send_sms_requires_from_number(monkeypatch):
    from telnyx_service import send_sms
    monkeypatch.delenv("TELNYX_PHONE_NUMBER", raising=False)

    result = await send_sms(to="+15551234567", body="hi")
    assert result.success is False
    assert result.error_code == "NO_FROM_NUMBER"


# ---------------------------------------------------------------------------
# send_sms — happy path & retry
# ---------------------------------------------------------------------------

async def test_send_sms_happy_path(monkeypatch):
    from telnyx_service import send_sms
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={"data": {"id": "msg_abc"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await send_sms(to="+15551234567", body="hi", idempotency_key="k1")
    assert result.success is True
    assert result.message_id == "msg_abc"


async def test_send_sms_retries_on_5xx_then_succeeds(monkeypatch):
    from telnyx_service import send_sms
    import asyncio
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")
    monkeypatch.setattr(asyncio, "sleep", lambda *a, **k: _noop())  # speed up

    calls = []

    async def fake_post(self, url, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            return _resp(503, json={"errors": [{"code": "RATE", "title": "Try later"}]},
                                  headers={"content-type": "application/json"})
        return _resp(200, json={"data": {"id": "msg_after_retry"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await send_sms(to="+15551234567", body="hi", max_retries=3)
    assert result.success is True
    assert len(calls) == 3


async def _noop():
    return None


async def test_send_sms_non_retryable_4xx(monkeypatch):
    from telnyx_service import send_sms
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")

    async def fake_post(self, url, **kwargs):
        return _resp(
            400,
            json={"errors": [{"code": "BAD_REQUEST", "title": "Invalid"}]},
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await send_sms(to="+15551234567", body="hi")
    assert result.success is False
    assert result.error_code == "BAD_REQUEST"


async def test_send_sms_retries_exhausted(monkeypatch):
    from telnyx_service import send_sms
    import asyncio
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")
    monkeypatch.setattr(asyncio, "sleep", lambda *a, **k: _noop())

    async def fake_post(self, url, **kwargs):
        return _resp(503, text="dead")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await send_sms(to="+15551234567", body="hi", max_retries=2)
    assert result.success is False
    assert result.error_code == "RETRIES_EXHAUSTED"


async def test_send_sms_handles_network_error(monkeypatch):
    from telnyx_service import send_sms
    import asyncio
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")
    monkeypatch.setattr(asyncio, "sleep", lambda *a, **k: _noop())

    async def fake_post(self, url, **kwargs):
        raise httpx.RequestError("net down")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await send_sms(to="+15551234567", body="hi", max_retries=2)
    assert result.success is False


# ---------------------------------------------------------------------------
# Call control actions
# ---------------------------------------------------------------------------

async def test_hang_up_call_success(monkeypatch):
    from telnyx_service import hang_up_call

    async def fake_post(self, url, **kwargs):
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await hang_up_call("call_123") is True


async def test_hang_up_call_failure_returns_false(monkeypatch):
    from telnyx_service import hang_up_call

    async def fake_post(self, url, **kwargs):
        return _resp(500, text="boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await hang_up_call("call_123") is False


async def test_transfer_call(monkeypatch):
    from telnyx_service import transfer_call

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    ok = await transfer_call("call_1", "+15551234567")
    assert ok is True
    assert captured["json"]["to"] == "+15551234567"
    # Default Telnyx ring timeout is 30s — server-side durable fallback.
    assert captured["json"]["timeout_secs"] == 30


async def test_transfer_call_custom_timeout(monkeypatch):
    """timeout_secs is configurable per call so the in-process fallback
    watchdog can be tuned alongside it."""
    from telnyx_service import transfer_call

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await transfer_call("call_1", "+15551234567", timeout_secs=45)
    assert captured["json"]["timeout_secs"] == 45


async def test_hang_up_call_already_ended_returns_true(monkeypatch):
    """Telnyx error code 90018 (HTTP 422) means the call already ended —
    treat as success since the desired end-state (call not active) is
    already achieved. Necessary for the auto_hang_up=False world where
    multiple cleanup paths may both try to hang up the same call."""
    from telnyx_service import hang_up_call

    async def fake_post(self, url, **kwargs):
        return _resp(422, json={"errors": [{"code": "90018", "title": "Call has already ended"}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await hang_up_call("call_already_dead") is True


async def test_stop_streaming_success(monkeypatch):
    """stop_streaming hits the actions/streaming_stop endpoint and returns
    True on 200. Used right after a successful transfer to make Gemini
    Live go idle while keeping the call leg alive."""
    from telnyx_service import stop_streaming

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["url"] = url
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await stop_streaming("call_xyz") is True
    assert captured["url"].endswith("/calls/call_xyz/actions/streaming_stop")


async def test_stop_streaming_failure_returns_false(monkeypatch):
    from telnyx_service import stop_streaming

    async def fake_post(self, url, **kwargs):
        return _resp(500, text="boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await stop_streaming("call_xyz") is False


async def test_answer_call_with_client_state(monkeypatch):
    from telnyx_service import answer_call

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await answer_call("call_1", client_state="state-abc")
    assert captured["json"]["client_state"] == "state-abc"


async def test_speak_text(monkeypatch):
    from telnyx_service import speak_text

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await speak_text("call_1", "Hello world")
    assert captured["json"]["payload"] == "Hello world"


async def test_start_streaming(monkeypatch):
    from telnyx_service import start_streaming

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await start_streaming("call_1", "wss://stream.example", codec="PCMU")
    assert captured["json"]["stream_url"] == "wss://stream.example"
    assert captured["json"]["stream_bidirectional_codec"] == "PCMU"


async def test_gather_using_speak(monkeypatch):
    from telnyx_service import gather_using_speak

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await gather_using_speak("call_1", "Press 1 for English", valid_digits="123",
                             minimum_digits=1, maximum_digits=1)
    assert captured["json"]["payload"] == "Press 1 for English"
    assert captured["json"]["valid_digits"] == "123"


# ---------------------------------------------------------------------------
# verify_webhook_signature
# ---------------------------------------------------------------------------

def test_verify_webhook_signature_happy_path(monkeypatch):
    from telnyx_service import verify_webhook_signature

    privkey = Ed25519PrivateKey.generate()
    pubkey_bytes = privkey.public_key().public_bytes_raw()
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", base64.b64encode(pubkey_bytes).decode())

    payload = b'{"event": "call.answered"}'
    timestamp = str(int(time.time()))
    message = f"{timestamp}|".encode() + payload
    signature = base64.b64encode(privkey.sign(message)).decode()

    assert verify_webhook_signature(payload, signature, timestamp) is True


def test_verify_webhook_signature_rejects_tampered_payload(monkeypatch):
    from telnyx_service import verify_webhook_signature

    privkey = Ed25519PrivateKey.generate()
    pubkey_bytes = privkey.public_key().public_bytes_raw()
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", base64.b64encode(pubkey_bytes).decode())

    payload = b'{"event": "call.answered"}'
    timestamp = str(int(time.time()))
    message = f"{timestamp}|".encode() + payload
    signature = base64.b64encode(privkey.sign(message)).decode()

    tampered = b'{"event": "tampered"}'
    assert verify_webhook_signature(tampered, signature, timestamp) is False


def test_verify_webhook_signature_rejects_wrong_pubkey(monkeypatch):
    from telnyx_service import verify_webhook_signature

    privkey = Ed25519PrivateKey.generate()
    other_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "TELNYX_PUBLIC_KEY",
        base64.b64encode(other_key.public_key().public_bytes_raw()).decode(),
    )

    payload = b'{"e": 1}'
    timestamp = str(int(time.time()))
    message = f"{timestamp}|".encode() + payload
    signature = base64.b64encode(privkey.sign(message)).decode()

    assert verify_webhook_signature(payload, signature, timestamp) is False


def test_verify_webhook_signature_rejects_stale_timestamp(monkeypatch):
    from telnyx_service import verify_webhook_signature

    privkey = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "TELNYX_PUBLIC_KEY",
        base64.b64encode(privkey.public_key().public_bytes_raw()).decode(),
    )

    # Timestamp 1 hour ago, tolerance 300s
    timestamp = str(int(time.time()) - 3600)
    payload = b'{}'
    message = f"{timestamp}|".encode() + payload
    signature = base64.b64encode(privkey.sign(message)).decode()

    assert verify_webhook_signature(payload, signature, timestamp, tolerance_seconds=300) is False


def test_verify_webhook_signature_rejects_bad_timestamp_header(monkeypatch):
    from telnyx_service import verify_webhook_signature

    monkeypatch.setenv("TELNYX_PUBLIC_KEY", base64.b64encode(b"x" * 32).decode())
    assert verify_webhook_signature(b'{}', "sig", "not-an-int") is False


# ---------------------------------------------------------------------------
# Phone number provisioning
# ---------------------------------------------------------------------------

async def test_search_available_numbers_passes_params(monkeypatch):
    from telnyx_service import search_available_numbers

    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["params"] = kwargs.get("params")
        return _resp(200, json={"data": [{"phone_number": "+15551234567"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    out = await search_available_numbers(country_code="US", area_code="555", limit=5)
    assert len(out) == 1
    assert captured["params"]["filter[country_code]"] == "US"
    assert captured["params"]["filter[national_destination_code]"] == "555"
    assert captured["params"]["filter[limit]"] == "5"


async def test_create_number_order_sends_full_payload(monkeypatch):
    from telnyx_service import create_number_order

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={"data": {"id": "order_1"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await create_number_order(
        ["+15551234567", "+15551234568"],
        connection_id="conn_1",
        messaging_profile_id="mp_1",
        customer_reference="rest_a",
    )
    assert out["id"] == "order_1"
    assert captured["json"]["phone_numbers"] == [
        {"phone_number": "+15551234567"},
        {"phone_number": "+15551234568"},
    ]
    assert captured["json"]["connection_id"] == "conn_1"
    assert captured["json"]["messaging_profile_id"] == "mp_1"
    assert captured["json"]["customer_reference"] == "rest_a"


async def test_release_phone_number_success(monkeypatch):
    from telnyx_service import release_phone_number

    async def fake_delete(self, url, **kwargs):
        return _resp(200, json={})

    monkeypatch.setattr(httpx.AsyncClient, "delete", fake_delete)
    assert await release_phone_number("phone_1") is True


# ---------------------------------------------------------------------------
# Additional coverage: get_number_order, wait_for_order_completion,
# list_phone_numbers, get_phone_number_details, update_phone_number
# ---------------------------------------------------------------------------

async def test_get_number_order(monkeypatch):
    from telnyx_service import get_number_order

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"data": {"id": "order_1", "status": "success"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    out = await get_number_order("order_1")
    assert out["id"] == "order_1"


async def test_wait_for_order_completion_returns_when_success(monkeypatch):
    from telnyx_service import wait_for_order_completion

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"data": {"id": "order_1", "status": "success"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    out = await wait_for_order_completion("order_1", timeout_seconds=5, poll_interval_seconds=0.01)
    assert out["status"] == "success"


async def test_wait_for_order_completion_times_out(monkeypatch):
    from telnyx_service import wait_for_order_completion

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"data": {"id": "order_1", "status": "pending"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", lambda *a, **k: _noop())

    with pytest.raises(TimeoutError):
        await wait_for_order_completion("order_1", timeout_seconds=0, poll_interval_seconds=0.01)


async def test_list_phone_numbers_with_filter(monkeypatch):
    from telnyx_service import list_phone_numbers

    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["params"] = kwargs.get("params")
        return _resp(200, json={"data": [{"phone_number": "+15551234567"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    out = await list_phone_numbers(phone_number="+15551234567")
    assert len(out) == 1
    assert captured["params"]["filter[phone_number]"] == "+15551234567"


async def test_get_phone_number_details(monkeypatch):
    from telnyx_service import get_phone_number_details

    async def fake_get(self, url, **kwargs):
        return _resp(200, json={"data": {"id": "ph_1", "phone_number": "+15551234567"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    out = await get_phone_number_details("ph_1")
    assert out["id"] == "ph_1"


async def test_update_phone_number(monkeypatch):
    from telnyx_service import update_phone_number

    captured = {}

    async def fake_patch(self, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _resp(200, json={"data": {"id": "ph_1"}})

    monkeypatch.setattr(httpx.AsyncClient, "patch", fake_patch)

    await update_phone_number(
        "ph_1",
        connection_id="conn_1",
        messaging_profile_id="mp_1",
        tags=["x"],
        customer_reference="rest_a",
    )
    assert captured["json"]["connection_id"] == "conn_1"
    assert captured["json"]["messaging_profile_id"] == "mp_1"
    assert captured["json"]["tags"] == ["x"]
    assert captured["json"]["customer_reference"] == "rest_a"


# ---------------------------------------------------------------------------
# Persister callback
# ---------------------------------------------------------------------------

async def test_send_sms_invokes_persister_on_success(monkeypatch):
    from telnyx_service import send_sms, set_sms_persister
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")

    captured = []

    async def persister(record):
        captured.append(record)

    set_sms_persister(persister)
    try:
        async def fake_post(self, url, **kwargs):
            return _resp(200, json={"data": {"id": "msg_1"}})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        await send_sms(to="+15551234567", body="hi")

        assert len(captured) == 1
        assert captured[0]["status"] == "sent"
    finally:
        set_sms_persister(None)


async def test_send_sms_persister_swallows_exceptions(monkeypatch):
    """A persister raising must not break the SMS send."""
    from telnyx_service import send_sms, set_sms_persister
    monkeypatch.setenv("TELNYX_PHONE_NUMBER", "+15555550100")

    async def crashy_persister(record):
        raise RuntimeError("persister down")

    set_sms_persister(crashy_persister)
    try:
        async def fake_post(self, url, **kwargs):
            return _resp(200, json={"data": {"id": "msg_1"}})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        result = await send_sms(to="+15551234567", body="hi")
        assert result.success is True
    finally:
        set_sms_persister(None)


async def test_release_phone_number_returns_false_on_error(monkeypatch):
    from telnyx_service import release_phone_number

    async def fake_delete(self, url, **kwargs):
        return _resp(404, text="not found")

    monkeypatch.setattr(httpx.AsyncClient, "delete", fake_delete)
    assert await release_phone_number("phone_1") is False
