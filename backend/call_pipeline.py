"""
Pipecat + Gemini Live Audio Call Pipeline for RingAI

This module handles real-time phone calls using:
  Twilio (phone) -> Pipecat (audio bridge) -> Gemini 2.5 Flash Live Audio API

Pipecat automatically handles:
  - mulaw 8kHz (Twilio) <-> PCM 16kHz (Gemini) audio conversion
  - Voice Activity Detection (VAD)
  - Turn management
  - Streaming in both directions

Requires:
  - GOOGLE_API_KEY env var
  - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN env vars
  - pipecat-ai[google,websocket] package
"""
import os
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_pipeline_available() -> bool:
    """Check if all required services are configured."""
    return all([
        os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY"),
        os.environ.get("TWILIO_ACCOUNT_SID"),
        os.environ.get("TWILIO_AUTH_TOKEN"),
    ])


# ---------------------------------------------------------------------------
# Pipeline Factory
# ---------------------------------------------------------------------------

async def create_call_pipeline(
    websocket,
    system_prompt: str,
    restaurant_id: str,
    call_sid: str,
    on_call_complete: Optional[callable] = None,
):
    """
    Create and return a Pipecat pipeline for a live phone call.

    Flow:
        Twilio audio (mulaw 8kHz)
          -> TwilioFrameSerializer (decode)
            -> Gemini Live Audio (STT + LLM + TTS in one model)
              -> TwilioFrameSerializer (encode)
                -> Twilio audio out

    Args:
        websocket: FastAPI WebSocket connection from Twilio
        system_prompt: Full system prompt for the AI agent
        restaurant_id: For logging and DB writes
        call_sid: Twilio Call SID for tracking
        on_call_complete: Callback with (call_sid, transcript, order_json)
    """
    if not is_pipeline_available():
        logger.warning("Pipeline not available — missing API keys")
        return None

    try:
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineTask, PipelineParams
        from pipecat.transports.services.fastapi_websocket import (
            FastAPIWebsocketTransport,
            FastAPIWebsocketParams,
        )
        from pipecat.serializers.twilio import TwilioFrameSerializer
        from pipecat.services.google.gemini_live import (
            GeminiLiveLLMService,
        )
        from pipecat.processors.transcript_processor import TranscriptProcessor

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview")

        # --- Transport: Twilio WebSocket with mulaw serialiser ---
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                serializer=TwilioFrameSerializer(
                    stream_sid=call_sid,
                ),
            ),
        )

        # --- Gemini Live: single model for STT + LLM + TTS ---
        gemini_live = GeminiLiveLLMService(
            api_key=api_key,
            model=f"models/{model}",
            system_instruction=system_prompt,
            voice="Puck",  # Gemini native voice
        )

        # --- Transcript collector (for post-call saving) ---
        transcript_collector = TranscriptProcessor()

        # --- Build pipeline ---
        pipeline = Pipeline([
            transport.input(),
            gemini_live,
            transcript_collector,
            transport.output(),
        ])

        task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
        )

        # --- On call end, save transcript ---
        @transport.event_handler("on_client_disconnected")
        async def on_disconnect(transport, client):
            logger.info(f"Call {call_sid} disconnected")
            if on_call_complete:
                transcript = transcript_collector.get_transcript()
                await on_call_complete(
                    call_sid=call_sid,
                    restaurant_id=restaurant_id,
                    transcript=transcript,
                )

        runner = PipelineRunner()
        await runner.run(task)

        return task

    except ImportError as e:
        logger.error(f"Pipecat import error: {e}. Install with: pip install 'pipecat-ai[google,websocket]'")
        return None
    except Exception as e:
        logger.error(f"Pipeline creation error: {e}")
        return None


# ---------------------------------------------------------------------------
# TwiML Generator
# ---------------------------------------------------------------------------

def generate_twiml_stream_response(websocket_url: str, call_sid: str) -> str:
    """
    Generate TwiML XML that tells Twilio to open a WebSocket media stream.

    Args:
        websocket_url: Full WSS URL to stream audio to
        call_sid: Twilio Call SID for tracking
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}">
            <Parameter name="callSid" value="{call_sid}" />
        </Stream>
    </Connect>
</Response>"""


# ---------------------------------------------------------------------------
# Twilio Phone Number Management
# ---------------------------------------------------------------------------

def get_twilio_client():
    """Get an authenticated Twilio REST client."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        return None
    from twilio.rest import Client
    return Client(sid, token)


async def provision_phone_number(area_code: str = "415") -> Optional[str]:
    """
    Purchase a Twilio phone number for a restaurant.
    Returns the phone number string or None.
    """
    client = get_twilio_client()
    if not client:
        logger.warning("Twilio not configured — returning mock number")
        import random
        return f"+1555{random.randint(1000000,9999999)}"

    try:
        available = client.available_phone_numbers("US").local.list(
            area_code=area_code, limit=1,
        )
        if not available:
            logger.error(f"No numbers available in area code {area_code}")
            return None

        purchased = client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            voice_url=os.environ.get("TWILIO_WEBHOOK_URL", "https://your-domain/api/twilio/incoming"),
            voice_method="POST",
        )
        logger.info(f"Provisioned Twilio number: {purchased.phone_number}")
        return purchased.phone_number
    except Exception as e:
        logger.error(f"Twilio number provisioning failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Validate Twilio Request (webhook security)
# ---------------------------------------------------------------------------

def validate_twilio_request(url: str, params: dict, signature: str) -> bool:
    """Validate that an incoming request is genuinely from Twilio."""
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not token:
        return True  # Skip validation in dev
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(token)
        return validator.validate(url, params, signature)
    except Exception:
        return False
