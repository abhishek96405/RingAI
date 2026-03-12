"""
Pipecat + Gemini Live Audio Call Pipeline for RingAI

Handles real-time phone calls:
  Twilio → WebSocket → TwilioFrameSerializer
  → GeminiLiveLLMService (native audio: STT + LLM + TTS in one model, ~200-400ms latency)
  → TwilioFrameSerializer → Twilio

CHANGES IN THIS VERSION:
  - Auto-hangup: after ORDER_CONFIRMED, Twilio call is terminated via REST API
    after a short delay to let the farewell phrase finish playing
  - Pipeline teardown: task.cancel() called after hangup to stop Gemini Live
    and close the WebSocket, preventing continued Twilio/Gemini billing
  - Escalation hangup: same auto-hangup logic fires after ESCALATE_TO_HUMAN
  - Dispatch is now triggered immediately on ORDER_CONFIRMED signal (not just
    on disconnect) so orders are saved even if customer hangs up first
  - Retry loop in dispatch_order_if_ready: up to 3 attempts with backoff
  - Transcript patching unchanged from previous version

Requires:
  - GOOGLE_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN env vars
  - pip install 'pipecat-ai[google,websocket,silero]'
"""
import os
import asyncio
import base64
import logging
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone

import httpx

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
    from pipecat.frames.frames import TextFrame, EndFrame
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

# How long (seconds) to wait after AI says farewell before hanging up.
# Long enough for TTS to finish playing, short enough not to leave dead air.
HANGUP_DELAY_SECS = float(os.environ.get("HANGUP_DELAY_SECS", "3.5"))


# ---------------------------------------------------------------------------
# Twilio REST hangup — terminates the call programmatically
# ---------------------------------------------------------------------------

async def hang_up_twilio_call(call_sid: str) -> bool:
    """
    End a Twilio call via the REST API by setting its status to 'completed'.
    This stops Twilio billing immediately and closes the media stream.
    Returns True on success.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token  = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        logger.warning(f"[{call_sid}] Cannot hang up — missing Twilio credentials")
        return False

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                data={"Status": "completed"},
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if resp.status_code in (200, 204):
                logger.info(f"[{call_sid}] ✅ Twilio call terminated via REST API")
                return True
            else:
                logger.error(f"[{call_sid}] Twilio hangup failed: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"[{call_sid}] Twilio hangup error: {e}")
        return False


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
        self.call_sid       = call_sid
        self.restaurant_id  = restaurant_id
        self.caller_number  = caller_number
        self.restaurant     = restaurant
        self.config         = config
        self.menu_index     = MenuIndex(menu_items)
        self.transcript: List[Dict] = []
        self.started_at     = datetime.now(timezone.utc).isoformat()
        self.order          = LiveOrder(
            restaurant_id=restaurant_id,
            call_sid=call_sid,
            caller_number=caller_number,
        )
        self._order_dispatched = False
        self._escalated        = False
        self._hangup_scheduled = False   # prevent double-hangup

        # Set by create_call_pipeline so session can trigger pipeline teardown
        self._pipeline_task: Optional[Any] = None

    # ------------------------------------------------------------------
    # Transcript + signal handling
    # ------------------------------------------------------------------

    def add_transcript_entry(self, role: str, text: str):
        self.transcript.append({
            "role": role,
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if role == "ai":
            signals = detect_call_signals(text)

            if signals["order_confirmed"] and not self._order_dispatched:
                logger.info(f"[{self.call_sid}] ORDER_CONFIRMED signal detected")
                self.order.transition(OrderState.CONFIRMED, "confirmed via AI signal")
                self.order.confirmed_at = datetime.now(timezone.utc).isoformat()
                # Dispatch order immediately, don't wait for disconnect
                asyncio.ensure_future(self._handle_order_confirmed())

            if signals["escalate_to_human"] and not self._escalated:
                logger.info(f"[{self.call_sid}] ESCALATE signal detected")
                self.order.transition(OrderState.ESCALATED, "escalation via AI signal")
                self._escalated = True
                # Schedule hangup after escalation phrase finishes
                asyncio.ensure_future(self._schedule_hangup(reason="escalation"))

    # ------------------------------------------------------------------
    # Order confirmed handler — dispatch + schedule hangup
    # ------------------------------------------------------------------

    async def _handle_order_confirmed(self):
        """Dispatch the order then hang up after farewell TTS finishes."""
        # 1. Dispatch order to kitchen / DB
        await self.dispatch_order_if_ready()

        # 2. Wait for farewell TTS to finish playing before hanging up
        await self._schedule_hangup(reason="order_confirmed")

    async def _schedule_hangup(self, reason: str = "order_confirmed"):
        """Wait HANGUP_DELAY_SECS then terminate the Twilio call + pipeline."""
        if self._hangup_scheduled:
            return
        self._hangup_scheduled = True

        logger.info(
            f"[{self.call_sid}] Hangup scheduled in {HANGUP_DELAY_SECS}s — reason: {reason}"
        )
        await asyncio.sleep(HANGUP_DELAY_SECS)

        # Terminate Twilio call (stops billing)
        await hang_up_twilio_call(self.call_sid)

        # Stop Pipecat pipeline (closes Gemini Live WebSocket + stops Gemini billing)
        if self._pipeline_task is not None:
            try:
                await self._pipeline_task.cancel()
                logger.info(f"[{self.call_sid}] Pipeline task cancelled")
            except Exception as e:
                logger.warning(f"[{self.call_sid}] Pipeline cancel error (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Order dispatch (with retry)
    # ------------------------------------------------------------------

    async def dispatch_order_if_ready(self, max_retries: int = 3) -> bool:
        if self._order_dispatched:
            return False
        if self.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED):
            return False

        # Extract items from transcript if not already populated
        if not self.order.items:
            for attempt in range(1, max_retries + 1):
                extracted = await extract_order_from_transcript(
                    self.transcript, self.menu_index
                )
                if extracted:
                    extracted.restaurant_id = self.restaurant_id
                    extracted.call_sid      = self.call_sid
                    extracted.caller_number = self.caller_number
                    self.order = extracted
                    break
                if attempt < max_retries:
                    logger.warning(
                        f"[{self.call_sid}] Extraction attempt {attempt} failed — retrying in 2s"
                    )
                    await asyncio.sleep(2)
            else:
                logger.warning(f"[{self.call_sid}] Confirmed but no items extracted after {max_retries} attempts")
                return False

        self._order_dispatched = True
        result = await send_order_to_kitchen(self.order, self.restaurant)
        if result["success"]:
            self.order.kitchen_order_id = result["order_id"]
            self.order.transition(
                OrderState.COMPLETED,
                f"{result['method']}: {result['order_id']}",
            )
            logger.info(
                f"[{self.call_sid}] Order sent: {result['order_id']} via {result['method']}"
            )
        else:
            logger.error(f"[{self.call_sid}] Kitchen dispatch failed: {result}")
            self.order.transition(OrderState.COMPLETED, "dispatch failed — logged to DB")
        return True

    # ------------------------------------------------------------------
    # Final call record
    # ------------------------------------------------------------------

    def build_final_call_record(self) -> Dict[str, Any]:
        quality = evaluate_call_quality(
            self.transcript,
            order_confirmed=self.order.state in (OrderState.CONFIRMED, OrderState.COMPLETED),
            escalated=self._escalated,
        )
        return {
            "call_sid":            self.call_sid,
            "restaurant_id":       self.restaurant_id,
            "caller_number":       self.caller_number,
            "started_at":          self.started_at,
            "ended_at":            datetime.now(timezone.utc).isoformat(),
            "status":              "ESCALATED" if self._escalated else "COMPLETED",
            "contained_by_ai":     not self._escalated,
            "escalated_to_human":  self._escalated,
            "transcript":          self.transcript,
            "order":               self.order.to_dict() if self.order.items else None,
            "order_total":         self.order.total,
            "kitchen_order_id":    self.order.kitchen_order_id,
            "quality_eval":        quality,
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
        model   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview")
        voice   = os.environ.get("GEMINI_VOICE", "Aoede")

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

        # ------------------------------------------------------------------
        # Patch Gemini's internal handlers to capture transcript.
        # pipecat 0.0.104: GeminiLiveLLMService processes audio natively
        # and does not emit transcript frames into the pipeline.
        # ------------------------------------------------------------------
        if session:
            _ai_buffer: List[str] = []

            # Flush buffer → full AI turn on turn_complete
            original_turn_complete = gemini_live._handle_msg_turn_complete

            async def patched_turn_complete(message, *args, **kwargs):
                if _ai_buffer:
                    full_text = "".join(_ai_buffer).strip()
                    _ai_buffer.clear()
                    if full_text:
                        logger.info(f"[{call_sid}] AI: {full_text}")
                        session.add_transcript_entry("ai", full_text)
                return await original_turn_complete(message, *args, **kwargs)

            gemini_live._handle_msg_turn_complete = patched_turn_complete

            # Accumulate AI output text chunks (word-by-word from Gemini Live)
            original_push_output = gemini_live._push_output_transcription_text_frames

            async def patched_push_output(*args, **kwargs):
                if args and args[0]:
                    _ai_buffer.append(str(args[0]))
                return await original_push_output(*args, **kwargs)

            gemini_live._push_output_transcription_text_frames = patched_push_output

            # Customer transcription (arrives as full sentences from Gemini)
            original_push_user = gemini_live._push_user_transcription

            async def patched_push_user(*args, **kwargs):
                if args and args[0] and str(args[0]).strip():
                    text = str(args[0]).strip()
                    logger.info(f"[{call_sid}] CUSTOMER: {text}")
                    session.add_transcript_entry("customer", text)
                return await original_push_user(*args, **kwargs)

            gemini_live._push_user_transcription = patched_push_user

        # ------------------------------------------------------------------
        # Build pipeline
        # ------------------------------------------------------------------
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

        # Give session a reference to the task so it can cancel it on hangup
        if session:
            session._pipeline_task = task

        # Trigger AI greeting when Twilio connects
        from pipecat.processors.aggregators.llm_response import LLMMessagesAppendFrame

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            await asyncio.sleep(0.5)
            await task.queue_frame(LLMMessagesAppendFrame(
                messages=[{"role": "user", "content": "BEGIN_CALL"}],
                run_llm=True,
            ))

        # ------------------------------------------------------------------
        # Disconnect handler — post-call cleanup
        # Called when:
        #   (a) Customer hangs up first, OR
        #   (b) Our hang_up_twilio_call() fires above
        # Either way we ensure order is dispatched and record is saved.
        # ------------------------------------------------------------------
        @transport.event_handler("on_client_disconnected")
        async def on_disconnect(transport, client):
            logger.info(f"[{call_sid}] Disconnected — post-call processing")
            try:
                if session:
                    # Ensure order is dispatched if not already done
                    if session.order.state == OrderState.CONFIRMED and not session._order_dispatched:
                        await session.dispatch_order_if_ready()

                    # Last-chance extraction: if still no items, try once more
                    if not session.order.items and session.transcript:
                        extracted = await extract_order_from_transcript(
                            session.transcript, session.menu_index
                        )
                        if extracted:
                            extracted.restaurant_id = restaurant_id
                            extracted.call_sid      = call_sid
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

            finally:
                # Always cancel pipeline on disconnect to stop Gemini billing.
                # Safe to call even if already cancelled via _schedule_hangup.
                try:
                    await task.cancel()
                except Exception:
                    pass
                logger.info(f"[{call_sid}] Pipeline fully torn down")

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
    sid   = os.environ.get("TWILIO_ACCOUNT_SID")
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
        available = client.available_phone_numbers("US").local.list(
            area_code=area_code, limit=1
        )
        if not available:
            return None
        purchased = client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            voice_url=os.environ.get(
                "TWILIO_WEBHOOK_URL", "https://your-domain/api/twilio/incoming"
            ),
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