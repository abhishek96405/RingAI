"""
telnyx_service.py — provider-agnostic Telnyx equivalents of Twilio helper calls.
All credentials read exclusively from environment variables — never hardcoded.
"""

import os
import base64
import logging

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

TELNYX_API_BASE = "https://api.telnyx.com/v2"


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['TELNYX_API_KEY']}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

async def send_sms(to_number: str, body: str) -> bool:
    """Send an outbound SMS via Telnyx. Returns True on success."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/messages",
                headers=_auth_headers(),
                json={
                    "from": os.environ["TELNYX_PHONE_NUMBER"],
                    "to": to_number,
                    "text": body,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] SMS sent to {to_number}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] SMS send failed to {to_number}: {e}")
        return False


# ---------------------------------------------------------------------------
# Call control
# ---------------------------------------------------------------------------

async def hang_up_call(call_control_id: str) -> bool:
    """Hang up an active call via Telnyx Call Control API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/hangup",
                headers=_auth_headers(),
                json={},
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Hung up call {call_control_id}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Hang up failed for {call_control_id}: {e}")
        return False


async def transfer_call(call_control_id: str, to_number: str) -> bool:
    """Transfer an active call to a PSTN number via Telnyx Call Control API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/transfer",
                headers=_auth_headers(),
                json={"to": to_number},
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Transferred call {call_control_id} to {to_number}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Transfer failed for {call_control_id} -> {to_number}: {e}")
        return False
    

async def answer_call(call_control_id: str) -> bool:
    """Answer an incoming call via Telnyx Call Control API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/answer",
                headers=_auth_headers(),
                json={},
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
    codec: str = "PCMU",
) -> bool:
    """
    Start bidirectional media streaming on an answered call.
    Telnyx will open a WebSocket to stream_url and exchange audio frames there.
    PCMU = μ-law 8kHz, the standard PSTN codec (matches what Pipecat expects).
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TELNYX_API_BASE}/calls/{call_control_id}/actions/streaming_start",
                headers=_auth_headers(),
                json={
                    "stream_url": stream_url,
                    "stream_track": "inbound_track",
                    "stream_bidirectional_mode": "rtp",
                    "stream_bidirectional_codec": codec,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info(f"[Telnyx] Streaming started for {call_control_id} -> {stream_url}")
            return True
    except Exception as e:
        logger.error(f"[Telnyx] Streaming start failed for {call_control_id}: {e}")
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