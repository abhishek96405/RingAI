"""
telnyx_service.py — Telnyx SMS, voice, and number provisioning helpers for Duuutah AI.
All credentials read exclusively from environment variables — never hardcoded.
"""

import os
import base64
import logging
import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, List

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

TELNYX_API_BASE = "https://api.telnyx.com/v2"

# Single switch for the whole Telnyx<->Gemini audio path. "L16" = uncompressed
# 16-bit PCM at 16kHz (Gemini Live's native rate). "PCMU" = mu-law at 8kHz,
# the old narrowband PSTN default. call_pipeline.py reads this same env var
# independently for its TelnyxFrameSerializer construction (and for the
# Gemini/pipeline internal sample rates), so setting AUDIO_CODEC=PCMU rolls
# the entire pipeline back to the pre-upgrade behavior without touching code.
AUDIO_CODEC = os.environ.get("AUDIO_CODEC", "L16")
AUDIO_SAMPLE_RATE = 8000 if AUDIO_CODEC == "PCMU" else 16000


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['TELNYX_API_KEY']}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────────────────────────────────
# SMS — production layer
# ─────────────────────────────────────────────────────────────────────────

# Module-level persister callback (DI). Set during app startup via set_sms_persister().
# Keeps telnyx_service decoupled from the MongoDB client.
_sms_persister: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

# E.164: + followed by 8-15 digits
_E164_RE = re.compile(r"^\+\d{8,15}$")

# Telnyx SMS body cap
_TELNYX_SMS_MAX_LEN = 1600


@dataclass(frozen=True)
class SMSResult:
    """Result of an SMS send attempt. Truthy on success — backward-compatible
    with callers that do `if not send_sms(...): logger.warning(...)`.
    """
    success: bool
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def __bool__(self) -> bool:
        return self.success


def set_sms_persister(fn: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
    """Register an async callable invoked with each SMS attempt record."""
    global _sms_persister
    _sms_persister = fn


def _validate_e164(number: str) -> bool:
    return bool(_E164_RE.match(number or ""))


async def _persist(record: Dict[str, Any]) -> None:
    """Best-effort persistence — never raises."""
    if _sms_persister is None:
        return
    try:
        await _sms_persister(record)
    except Exception as e:
        logger.warning(f"[Telnyx SMS] persister failed (non-fatal): {e}")


async def send_sms(
    to: str,
    body: str,
    *,
    idempotency_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> SMSResult:
    """Send an SMS via Telnyx. E.164 validated, idempotent, retries on 5xx/429/network.

    Args:
        to: Recipient phone in E.164 format (e.g. '+15551234567').
        body: Message text. Non-empty, <= 1600 chars.
        idempotency_key: Optional client dedup key (24h window). Auto UUID4 if omitted.
        metadata: Arbitrary dict persisted with the SMS record (restaurant_id, purpose, etc.)
        max_retries: Total attempt count for retryable errors. Default 3.

    Returns:
        SMSResult — truthy on success, with message_id for status callback correlation.
    """
    metadata = dict(metadata or {})
    now_iso = lambda: datetime.now(timezone.utc).isoformat()

    # Validation
    if not _validate_e164(to):
        msg = f"Invalid phone format (must be E.164): {to!r}"
        logger.error(f"[Telnyx SMS] {msg}")
        await _persist({
            "to": to, "body": body, "status": "failed",
            "error_code": "INVALID_PHONE", "error_message": msg,
            "metadata": metadata, "created_at": now_iso(), "updated_at": now_iso(),
        })
        return SMSResult(success=False, error_code="INVALID_PHONE", error_message=msg)

    if not body or not body.strip():
        return SMSResult(success=False, error_code="EMPTY_BODY", error_message="Empty SMS body")

    if len(body) > _TELNYX_SMS_MAX_LEN:
        msg = f"SMS body length {len(body)} exceeds Telnyx max ({_TELNYX_SMS_MAX_LEN})"
        logger.error(f"[Telnyx SMS] {msg}")
        await _persist({
            "to": to, "body": body[:200] + "...[truncated]", "status": "failed",
            "error_code": "BODY_TOO_LONG", "error_message": msg,
            "metadata": metadata, "created_at": now_iso(), "updated_at": now_iso(),
        })
        return SMSResult(success=False, error_code="BODY_TOO_LONG", error_message=msg)

    from_number = os.environ.get("TELNYX_PHONE_NUMBER")
    if not from_number:
        return SMSResult(success=False, error_code="NO_FROM_NUMBER",
                         error_message="TELNYX_PHONE_NUMBER env var not set")

    messaging_profile_id = os.environ.get("TELNYX_MESSAGING_PROFILE_ID")
    idem_key = idempotency_key or str(uuid.uuid4())

    payload: Dict[str, Any] = {"from": from_number, "to": to, "text": body}
    if messaging_profile_id:
        payload["messaging_profile_id"] = messaging_profile_id

    headers = {**_auth_headers(), "Idempotency-Key": idem_key}

    last_error_code: Optional[str] = None
    last_error_msg: Optional[str] = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.post(
                    f"{TELNYX_API_BASE}/messages",
                    headers=headers,
                    json=payload,
                )
            except httpx.RequestError as e:
                last_error_code = "NETWORK_ERROR"
                last_error_msg = str(e)
                logger.warning(f"[Telnyx SMS] attempt {attempt}/{max_retries} network error to {to}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue

            if resp.status_code in (200, 201):
                data = resp.json().get("data", {})
                message_id = data.get("id")
                await _persist({
                    "message_id": message_id,
                    "idempotency_key": idem_key,
                    "to": to, "from": from_number, "body": body,
                    "status": "sent",
                    "cost_cents": None,
                    "error_code": None, "error_message": None,
                    "metadata": metadata,
                    "created_at": now_iso(), "updated_at": now_iso(),
                })
                logger.info(f"[Telnyx SMS] sent to {to[-4:]} (id={message_id}, attempt={attempt})")
                return SMSResult(success=True, message_id=message_id)

            # Error envelope: {"errors": [{"code": "...", "title": "..."}]}
            try:
                err_data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
            except Exception:
                err_data = {}
            errors = err_data.get("errors") or []
            err_code = str(errors[0].get("code")) if errors else f"HTTP_{resp.status_code}"
            err_msg = errors[0].get("title", resp.text[:200]) if errors else resp.text[:200]
            last_error_code = err_code
            last_error_msg = err_msg

            if resp.status_code >= 500 or resp.status_code == 429:
                logger.warning(f"[Telnyx SMS] attempt {attempt}/{max_retries} retryable {resp.status_code}: {err_code}: {err_msg}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue

            # Non-retryable 4xx
            logger.error(f"[Telnyx SMS] non-retryable {resp.status_code} to {to}: {err_code}: {err_msg}")
            await _persist({
                "idempotency_key": idem_key,
                "to": to, "from": from_number, "body": body,
                "status": "failed",
                "error_code": err_code, "error_message": err_msg,
                "metadata": metadata,
                "created_at": now_iso(), "updated_at": now_iso(),
            })
            return SMSResult(success=False, error_code=err_code, error_message=err_msg)

    # Retries exhausted
    final_code = last_error_code or "RETRIES_EXHAUSTED"
    final_msg = last_error_msg or f"Exhausted {max_retries} retries"
    logger.error(f"[Telnyx SMS] retries exhausted for {to}: {final_code}: {final_msg}")
    await _persist({
        "idempotency_key": idem_key,
        "to": to, "from": from_number, "body": body,
        "status": "failed",
        "error_code": "RETRIES_EXHAUSTED", "error_message": final_msg,
        "metadata": metadata,
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    return SMSResult(success=False, error_code="RETRIES_EXHAUSTED", error_message=final_msg)


# ---------------------------------------------------------------------------
# Call control
# ---------------------------------------------------------------------------

async def hang_up_call(call_control_id: str) -> bool:
    """Hang up an active call via Telnyx Call Control API.

    Returns True for both fresh hangups and the "call already ended" case
    (Telnyx error code 90018). Both outcomes leave the call in the desired
    state; callers should not retry on either. Returns False only on
    unexpected errors.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/hangup",
                headers=_auth_headers(),
                json={},
                timeout=10.0,
            )
            if resp.status_code == 200:
                logger.info(f"[Telnyx] Hung up call {call_control_id}")
                return True
            if resp.status_code == 422:
                try:
                    body = resp.json()
                    if any(err.get("code") == "90018" for err in body.get("errors", [])):
                        logger.debug(f"[Telnyx] Call {call_control_id} already ended (90018)")
                        return True
                except Exception:
                    pass
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Hang up failed for {call_control_id}: {e}")
        return False


async def stop_streaming(call_control_id: str) -> bool:
    """Stop the media WebSocket stream for an active call.

    The call leg itself stays connected — Telnyx just stops forwarding
    audio over our WebSocket. Used right after initiating a transfer so
    the AI side stops receiving customer audio (which keeps Gemini Live
    idle) while Telnyx bridges A↔B audio internally.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/streaming_stop",
                headers=_auth_headers(),
                json={},
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Stopped streaming for call {call_control_id}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Stop streaming failed for {call_control_id}: {e}")
        return False


async def transfer_call(
    call_control_id: str,
    to_number: str,
    timeout_secs: int = 30,
) -> bool:
    """Transfer an active call to a PSTN number via Telnyx Call Control API.

    Args:
        call_control_id: A-leg call_control_id (the customer's leg).
        to_number: E.164 destination number for the B-leg dial.
        timeout_secs: Seconds Telnyx waits for the destination to answer
            before giving up. Defaults to 30. Telnyx fires call.hangup on
            the B-leg with cause indicating timeout when this elapses.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/transfer",
                headers=_auth_headers(),
                json={"to": to_number, "timeout_secs": timeout_secs},
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Transferred call {call_control_id} to {to_number} (timeout={timeout_secs}s)")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Transfer failed for {call_control_id} -> {to_number}: {e}")
        return False


async def answer_call(call_control_id: str, client_state: Optional[str] = None) -> bool:
    """Answer an incoming call via Telnyx Call Control API.

    Args:
        call_control_id: Telnyx call_control_id for the inbound call.
        client_state: Optional base64-encoded string. Telnyx echoes this back in
            the client_state field of every subsequent webhook event for this
            call, enabling stateless per-call routing logic (e.g. IVR language
            selection) without server-side session storage.
    """
    body: Dict[str, Any] = {}
    if client_state:
        body["client_state"] = client_state
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/answer",
                headers=_auth_headers(),
                json=body,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Answered call {call_control_id}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Answer failed for {call_control_id}: {e}")
        return False


async def speak_text(call_control_id: str, text: str, voice: str = "female", language: str = "en-US") -> bool:
    """Play a TTS message on an active call."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/speak",
                headers=_auth_headers(),
                json={
                    "payload": text,
                    "voice": voice,
                    "language": language,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Speaking on {call_control_id}: {text[:60]}...")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Speak failed for {call_control_id}: {e}")
        return False
    
async def start_streaming(
    call_control_id: str,
    stream_url: str,
    codec: str = AUDIO_CODEC,
    sample_rate: int = AUDIO_SAMPLE_RATE,
    client_state: Optional[str] = None,
) -> bool:
    """
    Start bidirectional media streaming on an answered call.
    Telnyx will open a WebSocket to stream_url and exchange audio frames there.

    Defaults come from the AUDIO_CODEC env var (default "L16"/16kHz), matching
    Gemini Live's native audio format — no downsample-then-upsample round trip
    through narrowband PCMU. Telnyx bills media streaming per-minute
    regardless of codec, so this costs nothing extra over the old PCMU/8kHz
    setup.

    To restore the old narrowband behavior, set AUDIO_CODEC=PCMU in the
    environment rather than passing codec="PCMU" here directly — call_pipeline.py's
    serializer construction and Gemini/pipeline sample rates read the same env
    var, so the env var is the one switch that rolls back the whole pipeline
    consistently. Passing codec explicitly still works for one-off calls but
    won't flip those other pieces.
    """
    body: Dict[str, Any] = {
        "stream_url": stream_url,
        "stream_track": "inbound_track",
        "stream_bidirectional_mode": "rtp",
        "stream_bidirectional_codec": codec,
        "stream_bidirectional_sampling_rate": sample_rate,
    }
    if client_state:
        body["client_state"] = client_state
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/streaming_start",
                headers=_auth_headers(),
                json=body,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(
                f"[Telnyx] Streaming started for {call_control_id} -> {stream_url} "
                f"(codec={codec}, sample_rate={sample_rate})"
            )
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Streaming start failed for {call_control_id}: {e}")
        return False


async def gather_using_speak(
    call_control_id: str,
    payload: str,
    *,
    valid_digits: str = "0123456789",
    minimum_digits: int = 1,
    maximum_digits: int = 1,
    inter_digit_timeout_secs: int = 5,
    timeout_millis: int = 10000,
    voice: str = "female",
    language: str = "en-US",
    client_state: Optional[str] = None,
) -> bool:
    """
    Play a TTS prompt and collect DTMF digits from the caller.

    On completion (digit pressed OR timeout), Telnyx fires a call.gather.ended
    webhook with the collected digits and the client_state echoed back.

    Note on multilingual IVR prompts: Telnyx's English voice handles short
    multi-language strings passably for digit prompts. For higher quality in a
    Phase 2 polish, switch to gather_using_audio with pre-recorded MP3s.
    """
    body: Dict[str, Any] = {
        "payload": payload,
        "valid_digits": valid_digits,
        "minimum_digits": minimum_digits,
        "maximum_digits": maximum_digits,
        "inter_digit_timeout_secs": inter_digit_timeout_secs,
        "timeout_millis": timeout_millis,
        "voice": voice,
        "language": language,
    }
    if client_state:
        body["client_state"] = client_state
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/gather_using_speak",
                headers=_auth_headers(),
                json=body,
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(
                f"[Telnyx] Gather started on {call_control_id} "
                f"(valid={valid_digits}, max={maximum_digits})"
            )
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Gather failed for {call_control_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Webhook signature verification (Ed25519)
# ---------------------------------------------------------------------------

def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    timestamp_header: str,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Verify a Telnyx webhook request using Ed25519.

    Telnyx sends two headers on every webhook:
      telnyx-signature-ed25519 — base64-encoded Ed25519 signature
      telnyx-timestamp          — Unix timestamp (string)

    The signed message is: f"{timestamp}|".encode() + raw_payload_bytes

    Args:
        payload:           Raw request body bytes (before any JSON parsing).
        signature_header:  Value of the 'telnyx-signature-ed25519' header.
        timestamp_header:  Value of the 'telnyx-timestamp' header.
        tolerance_seconds: Reject webhooks older than this many seconds (replay protection).

    Returns True if signature is valid and timestamp is within tolerance, else False.
    """
    import time

    try:
        # Replay-attack guard
        ts = int(timestamp_header)
        if abs(time.time() - ts) > tolerance_seconds:
            logger.warning(f"[Telnyx] Webhook timestamp out of tolerance: {ts}")
            return False

        # Decode public key (raw 32-byte Ed25519 key, base64-encoded in env var)
        public_key_bytes = base64.b64decode(os.environ["TELNYX_PUBLIC_KEY"])
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # Decode signature
        signature = base64.b64decode(signature_header)

        # Reconstruct the signed message
        message = f"{timestamp_header}|".encode() + payload

        # Raises InvalidSignature if verification fails
        public_key.verify(signature, message)
        return True

    except Exception as e:
        logger.warning(f"[Telnyx] Webhook signature verification failed: {e}")
        return False
    

# ─────────────────────────────────────────────────────────────────────────
# Phone number provisioning
# ─────────────────────────────────────────────────────────────────────────

def _get_voice_app_id() -> Optional[str]:
    """Telnyx Voice API Application ID (used as connection_id for voice routing)."""
    return (
        os.environ.get("TELNYX_VOICE_APP_ID")
        or os.environ.get("TELNYX_CONNECTION_ID")
        or os.environ.get("TELNYX_TEXML_APP_ID")  # legacy name from Phase 1
    )


def _get_messaging_profile_id() -> Optional[str]:
    return os.environ.get("TELNYX_MESSAGING_PROFILE_ID")


async def search_available_numbers(
    *,
    country_code: str = "US",
    area_code: Optional[str] = None,
    features: Optional[List[str]] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search Telnyx for available phone numbers (voice + SMS capable by default)."""
    features = features or ["voice", "sms"]
    params: Dict[str, Any] = {
        "filter[country_code]": country_code,
        "filter[limit]": str(min(max(limit, 1), 100)),
        "filter[features][]": features,
    }
    if area_code:
        params["filter[national_destination_code]"] = area_code

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{TELNYX_API_BASE}/available_phone_numbers",
            headers=_auth_headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def create_number_order(
    phone_numbers: List[str],
    *,
    connection_id: Optional[str] = None,
    messaging_profile_id: Optional[str] = None,
    customer_reference: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a number order. Numbers are assigned to voice + messaging at order time.

    Orders are usually async — completion in seconds. Use wait_for_order_completion().
    """
    payload: Dict[str, Any] = {
        "phone_numbers": [{"phone_number": pn} for pn in phone_numbers],
    }
    if connection_id:
        payload["connection_id"] = connection_id
    if messaging_profile_id:
        payload["messaging_profile_id"] = messaging_profile_id
    if customer_reference:
        payload["customer_reference"] = customer_reference

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{TELNYX_API_BASE}/number_orders",
            headers=_auth_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})


async def get_number_order(order_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{TELNYX_API_BASE}/number_orders/{order_id}",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json().get("data", {})


async def wait_for_order_completion(
    order_id: str,
    *,
    timeout_seconds: int = 30,
    poll_interval_seconds: float = 1.5,
) -> Dict[str, Any]:
    """Poll an order until it reaches a terminal state. Raises TimeoutError if not done in time."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while True:
        order = await get_number_order(order_id)
        status = (order.get("status") or "").lower()
        if status in ("success", "failure"):
            return order
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(f"Order {order_id} did not complete in {timeout_seconds}s (last status={status!r})")
        await asyncio.sleep(poll_interval_seconds)


async def list_phone_numbers(
    *,
    phone_number: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List phone numbers owned by the account. Optionally filter by exact E.164."""
    params: Dict[str, Any] = {"page[size]": str(min(max(limit, 1), 250))}
    if phone_number:
        params["filter[phone_number]"] = phone_number
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{TELNYX_API_BASE}/phone_numbers",
            headers=_auth_headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def get_phone_number_details(phone_number_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{TELNYX_API_BASE}/phone_numbers/{phone_number_id}",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json().get("data", {})


async def update_phone_number(
    phone_number_id: str,
    *,
    connection_id: Optional[str] = None,
    messaging_profile_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    customer_reference: Optional[str] = None,
) -> Dict[str, Any]:
    """Update voice connection, messaging profile, tags, or customer_reference on a number."""
    payload: Dict[str, Any] = {}
    if connection_id is not None:
        payload["connection_id"] = connection_id
    if messaging_profile_id is not None:
        payload["messaging_profile_id"] = messaging_profile_id
    if tags is not None:
        payload["tags"] = tags
    if customer_reference is not None:
        payload["customer_reference"] = customer_reference

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            f"{TELNYX_API_BASE}/phone_numbers/{phone_number_id}",
            headers=_auth_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})


async def release_phone_number(phone_number_id: str) -> bool:
    """Release a phone number from the account (cannot be undone)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(
                f"{TELNYX_API_BASE}/phone_numbers/{phone_number_id}",
                headers=_auth_headers(),
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Released phone number {phone_number_id}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Release failed for {phone_number_id}: {e}")
        return False