"""
Pipecat + Gemini Live Audio Call Pipeline for RingAI

Handles real-time phone calls:
  Twilio → WebSocket → TwilioFrameSerializer
  → GeminiLiveLLMService (native audio: STT + LLM + TTS in one model, ~200-400ms latency)
  → TwilioFrameSerializer → Twilio

Key improvements in this version:
  - Transcript captured by patching Gemini's internal message handlers directly
  - CallSession: isolated per-call state with real-time order tracking
  - ORDER_CONFIRMED / ESCALATE signal detection in AI speech
  - Kitchen dispatch triggered on confirmation, not just post-call
  - Twilio signature validation enforced on incoming webhook

Requires:
  - GOOGLE_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN env vars
  - pip install 'pipecat-ai[google,websocket,silero]'
"""
import os
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone

# Pre-load pipecat at module startup to eliminate per-call import delay (~15s)
try:
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask, PipelineParams
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketTransport, FastAPIWebsocketParams,
    )
    from pipecat.serializers.twilio import TwilioFrameSerializer
    from pipecat.services.google.gemini_live import GeminiLiveLLMService
    from pipecat.frames.frames import TextFrame
    _PIPECAT_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).warning(f"Pipecat not available: {e}")
    _PIPECAT_AVAILABLE = False

from gemini_service import (
    LiveOrder, OrderState, MenuIndex,
    extract_order_from_transcript,
    send_order_to_kitchen,
    detect_call_signals,
    evaluate_call_quality,
)

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
# VAD configuration
# ---------------------------------------------------------------------------
VAD_STOP_SECS  = float(os.environ.get("VAD_STOP_SECS",  "0.4"))
VAD_START_SECS = float(os.environ.get("VAD_START_SECS", "0.2"))
VAD_MIN_VOLUME = float(os.environ.get("VAD_MIN_VOLUME", "0.3"))


# ---------------------------------------------------------------------------
# CallSession — isolated per-call state (never shared between calls)
# ---------------------------------------------------------------------------

class CallSession:
    """One instance per call. Tracks order state, transcript, and dispatch."""

    def __init__(
        self,
        call_sid: str,
        restaurant_id: str,
        caller_number: str,
        restaurant: Dict[str, Any],
        config: Dict[str, Any],
        menu_items: List[Dict[str, Any]],
    ):
        self.call_sid = call_sid
        self.restaurant_id = restaurant_id
        self.caller_number = caller_number
        self.restaurant = restaurant
        self.config = config
        self.menu_index = MenuIndex(menu_items)
        self.transcript: List[Dict] = []
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.order = LiveOrder(
            restaurant_id=restaurant_id,
            call_sid=call_sid,
            caller_number=caller_number,
        )
        self._order_dispatched = False
        self._escalated = False

    def add_transcript_entry(self, role: str, text: str):
        self.transcript.append({
            "role": role, "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if role == "ai":
            signals = detect_call_signals(text)
            if signals["order_confirmed"] and not self._order_dispatched:
                logger.info(f"[{self.call_sid}] ORDER_CONFIRMED signal detected")
                self.order.transition(OrderState.CONFIRMED, "confirmed via AI signal")
                self.order.confirmed_at = datetime.now(timezone.utc).isoformat()
            if signals["escalate_to_human"] and not self._escalated:
                logger.info(f"[{self.call_sid}] ESCALATE signal detected")
                self.order.transition(OrderState.ESCALATED, "escalation via AI signal")
                self._escalated = True

    async def dispatch_order_if_ready(self) -> bool:
        if self._order_dispatched:
            return False
        if self.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED):
            return False
        if not self.order.items:
            extracted = await extract_order_from_transcript(self.transcript, self.menu_index)
            if not extracted:
                logger.warning(f"[{self.call_sid}] Confirmed but no items extracted")
                return False
            extracted.restaurant_id = self.restaurant_id
            extracted.call_sid = self.call_sid
            extracted.caller_number = self.caller_number
            self.order = extracted

        self._order_dispatched = True
        result = await send_order_to_kitchen(self.order, self.restaurant)
        if result["success"]:
            self.order.kitchen_order_id = result["order_id"]
            self.order.transition(OrderState.COMPLETED, f"{result['method']}: {result['order_id']}")
            logger.info(f"[{self.call_sid}] Order sent: {result['order_id']} via {result['method']}")
        else:
            logger.error(f"[{self.call_sid}] Kitchen dispatch failed: {result}")
            self.order.transition(OrderState.COMPLETED, "dispatch failed — logged to DB")
        return True

    def build_final_call_record(self) -> Dict[str, Any]:
        quality = evaluate_call_quality(
            self.transcript,
            order_confirmed=self.order.state in (OrderState.CONFIRMED, OrderState.COMPLETED),
            escalated=self._escalated,
        )
        return {
            "call_sid": self.call_sid,
            "restaurant_id": self.restaurant_id,
            "caller_number": self.caller_number,
            "started_at": self.started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "status": "ESCALATED" if self._escalated else "COMPLETED",
            "contained_by_ai": not self._escalated,
            "escalated_to_human": self._escalated,
            "transcript": self.transcript,
            "order": self.order.to_dict() if self.order.items else None,
            "order_total": self.order.total,
            "kitchen_order_id": self.order.kitchen_order_id,
            "quality_eval": quality,
        }


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------

async def create_call_pipeline(
    websocket,
    system_prompt: str,
    restaurant_id: str,
    call_sid: str,
    stream_sid: str = "",
    on_call_complete: Optional[Callable] = None,
    session: Optional[CallSession] = None,
):
    if not is_pipeline_available():
        logger.warning("[Pipeline] Not available — missing API keys")
        return None

    if not _PIPECAT_AVAILABLE:
        logger.error("[Pipeline] Pipecat not available — check installation")
        return None

    try:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY")
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview")
        voice = os.environ.get("GEMINI_VOICE", "Aoede")

        logger.info(f"[{call_sid}] Starting pipeline | model={model} voice={voice}")

        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                serializer=TwilioFrameSerializer(
                    stream_sid=stream_sid or call_sid,
                    account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
                    auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
                    call_sid=call_sid,
                ),
            ),
        )

        gemini_live = GeminiLiveLLMService(
            api_key=api_key,
            model=f"models/{model}",
            system_instruction=system_prompt,
            voice=voice,
            transcribe_user_audio=True,
            transcribe_model_output=True,
        )

        # Patch Gemini's internal message handlers to capture transcript.
        # We do this because in pipecat 0.0.104, GeminiLiveLLMService processes
        # audio natively and does not emit frames downstream to the pipeline.
        if session:
            # Buffer to accumulate AI speech chunks into complete turns
            _ai_buffer = []

            # --- Flush buffer on turn complete ---
            original_turn_complete = gemini_live._handle_msg_turn_complete

            async def patched_turn_complete(message, *args, **kwargs):
                if _ai_buffer:
                    full_text = "".join(_ai_buffer).strip()
                    _ai_buffer.clear()
                    if full_text:
                        logger.info(f"[{call_sid}] AI: {full_text}")
                        session.add_transcript_entry("ai", full_text)
                        asyncio.ensure_future(session.dispatch_order_if_ready())
                return await original_turn_complete(message, *args, **kwargs)

            gemini_live._handle_msg_turn_complete = patched_turn_complete

            # --- Accumulate AI output chunks (don't save yet) ---
            original_push_output = gemini_live._push_output_transcription_text_frames

            async def patched_push_output(*args, **kwargs):
                if args and args[0]:
                    _ai_buffer.append(str(args[0]))
                return await original_push_output(*args, **kwargs)

            gemini_live._push_output_transcription_text_frames = patched_push_output

            # --- Customer transcription (already arrives as full sentences) ---
            original_push_user = gemini_live._push_user_transcription

            async def patched_push_user(*args, **kwargs):
                if args and args[0] and str(args[0]).strip():
                    text = str(args[0]).strip()
                    logger.info(f"[{call_sid}] CUSTOMER: {text}")
                    session.add_transcript_entry("customer", text)
                return await original_push_user(*args, **kwargs)

            gemini_live._push_user_transcription = patched_push_user

        pipeline = Pipeline([
            transport.input(),
            gemini_live,
            transport.output(),
        ])

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                audio_out_sample_rate=8000,
            ),
        )

        # Trigger AI to speak first when client connects
        from pipecat.processors.aggregators.llm_response import LLMMessagesAppendFrame

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            await asyncio.sleep(0.5)
            await task.queue_frame(LLMMessagesAppendFrame(
                messages=[{"role": "user", "content": "BEGIN_CALL"}],
                run_llm=True,
            ))

        # Call end handler
        @transport.event_handler("on_client_disconnected")
        async def on_disconnect(transport, client):
            logger.info(f"[{call_sid}] Disconnected — post-call processing")
            try:
                if session:
                    if session.order.state == OrderState.CONFIRMED:
                        await session.dispatch_order_if_ready()
                    if not session.order.items and session.transcript:
                        extracted = await extract_order_from_transcript(
                            session.transcript, session.menu_index
                        )
                        if extracted:
                            extracted.restaurant_id = restaurant_id
                            extracted.call_sid = call_sid
                            extracted.caller_number = session.caller_number
                            session.order = extracted
                            result = await send_order_to_kitchen(extracted, session.restaurant)
                            if result["success"]:
                                session.order.kitchen_order_id = result["order_id"]

                if on_call_complete:
                    t = session.transcript if session else []
                    await on_call_complete(
                        call_sid=call_sid,
                        restaurant_id=restaurant_id,
                        transcript=t,
                        session=session,
                    )
            except Exception as e:
                logger.error(f"[{call_sid}] Post-call error: {e}", exc_info=True)

        runner = PipelineRunner()
        await runner.run(task)
        return task

    except ImportError as e:
        logger.error(f"[Pipeline] Import error: {e}")
        logger.error("Run: pip install 'pipecat-ai[google,websocket,silero]'")
        return None
    except Exception as e:
        logger.error(f"[Pipeline] Error: {e}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# TwiML generator
# ---------------------------------------------------------------------------

def generate_twiml_stream_response(websocket_url: str, call_sid: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}">
            <Parameter name="callSid" value="{call_sid}" />
        </Stream>
    </Connect>
</Response>"""


# ---------------------------------------------------------------------------
# Twilio helpers
# ---------------------------------------------------------------------------

def get_twilio_client():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        return None
    from twilio.rest import Client
    return Client(sid, token)


async def provision_phone_number(area_code: str = "415") -> Optional[str]:
    client = get_twilio_client()
    if not client:
        import random
        return f"+1555{random.randint(1000000,9999999)}"
    try:
        available = client.available_phone_numbers("US").local.list(area_code=area_code, limit=1)
        if not available:
            return None
        purchased = client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            voice_url=os.environ.get("TWILIO_WEBHOOK_URL", "https://your-domain/api/twilio/incoming"),
            voice_method="POST",
        )
        return purchased.phone_number
    except Exception as e:
        logger.error(f"Twilio provisioning failed: {e}")
        return None


def validate_twilio_request(url: str, params: dict, signature: str) -> bool:
    """Validate that a request is genuinely from Twilio."""
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not token:
        return True
    try:
        from twilio.request_validator import RequestValidator
        return RequestValidator(token).validate(url, params, signature)
    except Exception:
        return False