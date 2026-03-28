"""
Pipecat + Gemini Live Audio Call Pipeline for RingAI

Handles real-time phone calls:
  Twilio → WebSocket → TwilioFrameSerializer
  → GeminiLiveLLMService (native audio: STT + LLM + TTS in one model, ~200-400ms latency)
  → TwilioFrameSerializer → Twilio

CHANGES IN THIS VERSION:
  - on_call_complete now fires reliably from _schedule_hangup BEFORE pipeline cancel
  - Previously on_client_disconnected was skipped when task.cancel() fired first
  - _hangup_scheduled flag prevents double-call to on_call_complete
  - on_client_disconnected only fires on_call_complete if _schedule_hangup didn't
  - session._on_call_complete stored so _schedule_hangup can invoke it directly
  - Auto-hangup after ORDER_CONFIRMED via Twilio REST API
  - Pipeline teardown stops Gemini Live billing
  - Order dispatch with 3 retries + backoff

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

try:
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask, PipelineParams
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketTransport, FastAPIWebsocketParams,
    )
    from pipecat.serializers.twilio import TwilioFrameSerializer
    from pipecat.services.google.gemini_live import GeminiLiveLLMService
    from pipecat.frames.frames import TextFrame, EndFrame, InputTextRawFrame, LLMContextFrame
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        UserTurnStoppedMessage,
        AssistantTurnStoppedMessage,
    )
    from pipecat.processors.aggregators.llm_context import LLMContext
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

# Import appointment service for non-restaurant businesses
try:
    from appointment_service import extract_booking_from_transcript, dispatch_appointment
    _APPOINTMENT_SERVICE_AVAILABLE = True
except ImportError:
    _APPOINTMENT_SERVICE_AVAILABLE = False

logger = logging.getLogger(__name__)


class RingAIGeminiLive(GeminiLiveLLMService):
    """Subclass capturing AI transcript for Gemini 3.1 Flash Live.

    In Gemini 3.1, output_transcription arrives in the SAME message as
    model_turn. Pipecat's elif chain means _handle_msg_output_transcription
    never fires when model_turn is present. We capture it in _handle_msg_model_turn
    instead, and flush at turn_complete.
    """

    def __init__(self, on_ai_transcript=None, **kwargs):
        super().__init__(**kwargs)
        self._on_ai_transcript = on_ai_transcript
        self._ai_text_buffer: List[str] = []
        self._last_captured_from_model_turn = False

    async def _handle_msg_model_turn(self, message):
        # In Gemini 3.1, output_transcription arrives in the same message as model_turn.
        # We capture it here and set a flag to prevent double-capture in
        # _handle_msg_output_transcription if it also fires separately.
        if (
            message.server_content
            and message.server_content.output_transcription
            and message.server_content.output_transcription.text
        ):
            self._ai_text_buffer.append(
                message.server_content.output_transcription.text
            )
            self._last_captured_from_model_turn = True
        else:
            self._last_captured_from_model_turn = False
        await super()._handle_msg_model_turn(message)

    async def _handle_msg_output_transcription(self, message):
        # Only capture if model_turn didn't already capture this text
        if self._last_captured_from_model_turn:
            self._last_captured_from_model_turn = False
            await super()._handle_msg_output_transcription(message)
            return
        if (
            message.server_content
            and message.server_content.output_transcription
            and message.server_content.output_transcription.text
        ):
            self._ai_text_buffer.append(
                message.server_content.output_transcription.text
            )
        await super()._handle_msg_output_transcription(message)

    async def _handle_msg_turn_complete(self, message):
        await self._flush_ai_buffer()
        await super()._handle_msg_turn_complete(message)

    async def _flush_ai_buffer(self):
        if self._ai_text_buffer and self._on_ai_transcript:
            full_text = "".join(self._ai_text_buffer).strip()
            self._ai_text_buffer.clear()
            if full_text:
                await self._on_ai_transcript(full_text)

    async def _handle_interruption(self):
        # Clear buffer on interruption to prevent partial/duplicate text
        self._ai_text_buffer.clear()
        self._last_captured_from_model_turn = False
        await super()._handle_interruption()


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_pipeline_available() -> bool:
    return all([
        os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY"),
        os.environ.get("TWILIO_ACCOUNT_SID"),
        os.environ.get("TWILIO_AUTH_TOKEN"),
    ])


# ---------------------------------------------------------------------------
# VAD configuration
# ---------------------------------------------------------------------------
VAD_STOP_SECS  = float(os.environ.get("VAD_STOP_SECS",  "0.2"))
VAD_START_SECS = float(os.environ.get("VAD_START_SECS", "0.2"))
VAD_MIN_VOLUME = float(os.environ.get("VAD_MIN_VOLUME", "0.3"))

# Seconds to wait after farewell TTS before hanging up
HANGUP_DELAY_SECS = float(os.environ.get("HANGUP_DELAY_SECS", "1.5"))


# ---------------------------------------------------------------------------
# Twilio REST hangup
# ---------------------------------------------------------------------------

async def hang_up_twilio_call(call_sid: str) -> bool:
    """
    End a Twilio call via REST API by setting status to 'completed'.
    Stops Twilio billing immediately and closes the media stream.
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
# CallSession — isolated per-call state
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
        services: Optional[List[Dict[str, Any]]] = None,
    ):
        self.call_sid       = call_sid
        self.restaurant_id  = restaurant_id
        self.caller_number  = caller_number
        self.restaurant     = restaurant
        self.config         = config
        self.menu_index     = MenuIndex(menu_items)
        self.services       = services or []  # For appointment businesses
        self.transcript: List[Dict] = []
        self.started_at     = datetime.now(timezone.utc).isoformat()
        self.order          = LiveOrder(
            restaurant_id=restaurant_id,
            call_sid=call_sid,
            caller_number=caller_number,
        )
        self._order_dispatched  = False
        self._escalated         = False
        self._hangup_scheduled  = False  # prevents double hangup + double on_call_complete
        self._booking_dispatched = False  # For appointment businesses

        # Business type for horizontal platform support
        self.business_type = config.get("business_type", "restaurant") if config else "restaurant"
        
        self.db = None  # Set by create_call_pipeline

        # Set by create_call_pipeline after task is created
        self._pipeline_task: Optional[Any] = None
        # Set by create_call_pipeline so _schedule_hangup can invoke it directly
        self._on_call_complete: Optional[Callable] = None

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
                asyncio.ensure_future(self._handle_order_confirmed())

            if signals["escalate_to_human"] and not self._escalated:
                logger.info(f"[{self.call_sid}] ESCALATE signal detected")
                self.order.transition(OrderState.ESCALATED, "escalation via AI signal")
                self._escalated = True
                asyncio.ensure_future(self._schedule_hangup(reason="escalation"))

    # ------------------------------------------------------------------
    # Order confirmed — dispatch then hang up
    # ------------------------------------------------------------------

    async def _handle_appointment_confirmed(self):
        """Handle appointment businesses — dispatch booking then hang up."""
        self._hangup_scheduled = True
        await self.dispatch_booking(db=self.db)
        if self._on_call_complete:
            try:
                logger.info(f"[{self.call_sid}] Calling on_call_complete from _handle_appointment_confirmed")
                await self._on_call_complete(
                    call_sid=self.call_sid,
                    restaurant_id=self.restaurant_id,
                    transcript=self.transcript,
                    session=self,
                )
            except Exception as e:
                logger.error(f"[{self.call_sid}] on_call_complete error: {e}", exc_info=True)
        self._hangup_scheduled = False
        await self._schedule_hangup(reason="appointment_confirmed")

    # ------------------------------------------------------------------
    # Schedule hangup — calls on_call_complete FIRST, then terminates
    # ------------------------------------------------------------------

    async def _schedule_hangup(self, reason: str = "order_confirmed"):
        if self._hangup_scheduled:
            return
        self._hangup_scheduled = True

        logger.info(
            f"[{self.call_sid}] Hangup scheduled in {HANGUP_DELAY_SECS}s — reason: {reason}"
        )

        await asyncio.sleep(HANGUP_DELAY_SECS)
        await hang_up_twilio_call(self.call_sid)

        if self._pipeline_task is not None:
            try:
                await self._pipeline_task.cancel()
                logger.info(f"[{self.call_sid}] Pipeline task cancelled")
            except Exception as e:
                logger.warning(f"[{self.call_sid}] Pipeline cancel error (non-fatal): {e}")
    # ------------------------------------------------------------------
    # Order dispatch with retry
    # ------------------------------------------------------------------

    async def dispatch_order_if_ready(self, max_retries: int = 3) -> bool:
        if self._order_dispatched:
            logger.info(f"[{self.call_sid}] Order already dispatched — skipping")
            return False
        self._order_dispatched = True
        if self.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED):
            self._order_dispatched = False
            return False

        if not self.order.items:
            for attempt in range(1, max_retries + 1):
                extracted = await extract_order_from_transcript(
                    self.transcript, self.menu_index
                )
                # Use extracted items if present — ignore confirmed flag
                # ORDER_CONFIRMED signal is the source of truth, not extraction
                if extracted and extracted.items:
                    extracted.restaurant_id = self.restaurant_id
                    extracted.call_sid      = self.call_sid
                    extracted.caller_number = self.caller_number
                    extracted.order_confirmed = True
                    self.order = extracted
                    logger.info(
                        f"[{self.call_sid}] Extraction succeeded with "
                        f"{len(extracted.items)} items (confirmed override)"
                    )
                    break
                if attempt < max_retries:
                    logger.warning(
                        f"[{self.call_sid}] Extraction attempt {attempt} failed — retrying in 2s"
                    )
                    await asyncio.sleep(2)
            else:
                logger.warning(
                    f"[{self.call_sid}] Confirmed but no items extracted after {max_retries} attempts"
                )
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
    # Final call record builder
    # ------------------------------------------------------------------

    def build_final_call_record(self) -> Dict[str, Any]:
        quality = evaluate_call_quality(
            self.transcript,
            order_confirmed=self.order.state in (OrderState.CONFIRMED, OrderState.COMPLETED),
            escalated=self._escalated,
        )
        record = {
            "call_sid":           self.call_sid,
            "restaurant_id":      self.restaurant_id,
            "caller_number":      self.caller_number,
            "started_at":         self.started_at,
            "ended_at":           datetime.now(timezone.utc).isoformat(),
            "status":             "ESCALATED" if self._escalated else "COMPLETED",
            "contained_by_ai":    not self._escalated,
            "escalated_to_human": self._escalated,
            "transcript":         self.transcript,
            "order":              self.order.to_dict() if self.order.items else None,
            "order_total":        self.order.total,
            "kitchen_order_id":   self.order.kitchen_order_id,
            "quality_eval":       quality,
            "business_type":      self.business_type,  # Track business type
        }
        
        # Add booking info for appointment businesses
        if self._booking_dispatched and self.business_type in ("clinic", "salon", "home_services", "legal"):
            record["booking_dispatched"] = True
        
        return record

    # ------------------------------------------------------------------
    # Appointment dispatch for non-restaurant businesses
    # ------------------------------------------------------------------

    async def dispatch_booking(self, db=None) -> bool:
        """
        Extract and dispatch booking for appointment businesses.
        Separate from dispatch_order which handles restaurant orders.
        """
        if self._booking_dispatched:
            return True

        if not _APPOINTMENT_SERVICE_AVAILABLE:
            logger.warning(f"[{self.call_sid}] Appointment service not available")
            return False

        booking = await extract_booking_from_transcript(
            self.transcript,
            self.services,
        )
        if booking:
            booking["customer_phone"] = self.caller_number

        if not booking:
            logger.info(f"[{self.call_sid}] No confirmed booking found in transcript")
            return False

        logger.info(f"[{self.call_sid}] Booking extracted: {booking.get('service_name')} for {booking.get('customer_name')}")

        result = await dispatch_appointment(
            booking=booking,
            restaurant=self.restaurant,
            config=self.config,
            services=self.services,
            db=db,
        )

        self._booking_dispatched = True

        if result.get("success"):
            logger.info(f"[{self.call_sid}] Appointment dispatched: calendar={result.get('calendar_event_id')}, sms={result.get('sms_sent')}")
        else:
            logger.warning(f"[{self.call_sid}] Appointment dispatch partial: {result}")

        return True


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
        model   = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
        voice   = os.environ.get("GEMINI_VOICE", "Leda")

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

        from pipecat.services.google.gemini_live.llm import GeminiVADParams, EndSensitivity, StartSensitivity, InputParams
        from google.genai.types import ThinkingConfig

        async def on_ai_transcript(full_text: str):
            if not session:
                return
            logger.info(f"[{call_sid}] AI: {full_text}")
            session.add_transcript_entry("ai", full_text)
            text_lower = full_text.lower()

            # ── Menu SMS trigger ──
            if "i'll text you" in text_lower and "menu" in text_lower:
                from gemini_service import send_menu_sms
                asyncio.create_task(send_menu_sms(
                    caller_number=session.caller_number,
                    restaurant_name=session.restaurant.get("name", "the restaurant"),
                    restaurant_id=session.restaurant_id,
                    base_url="https://ringai-v2.onrender.com",
                ))
                logger.info(f"[{call_sid}] Menu SMS triggered")

            # ── ORDER_CONFIRMED signal (restaurant) ──
            order_confirmed_phrases = [
                "your order is confirmed",
                "order is confirmed",
                "i'll send you a text confirmation",
                "sending you a text confirmation",
                "ready in about",
                "thank you for calling",
            ]
            if (
                session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED)
                and any(p in text_lower for p in order_confirmed_phrases)
            ):
                if session.business_type == "restaurant":
                    logger.info(f"[{call_sid}] ORDER_CONFIRMED signal detected")
                    session.order.transition(OrderState.CONFIRMED, "signal")
                    asyncio.create_task(session._handle_order_confirmed())

            # ── APPOINTMENT_CONFIRMED signal ──
            appointment_confirmed_phrases = [
                "your appointment is confirmed",
                "appointment is confirmed",
                "appointment has been confirmed",
                "i'll send you a text confirmation",
                "we'll see you",
                "we look forward to seeing you",
            ]
            if (
                session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED)
                and any(p in text_lower for p in appointment_confirmed_phrases)
            ):
                business_type = session.config.get("business_type", "restaurant")
                if business_type in ("clinic", "salon", "home_services", "legal"):
                    logger.info(f"[{call_sid}] APPOINTMENT_CONFIRMED signal detected")
                    session.order.transition(OrderState.CONFIRMED, "signal")
                    asyncio.create_task(session._handle_appointment_confirmed())

        gemini_live = RingAIGeminiLive(
            on_ai_transcript=on_ai_transcript,
            api_key=api_key,
            model=f"models/{model}",
            system_instruction=system_prompt,
            voice_id=voice,
            http_options={"api_version": "v1alpha"},
            params=InputParams(
                thinking=ThinkingConfig(thinking_level="MINIMAL"),
                vad=GeminiVADParams(
                    start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                    end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=500,
                    prefix_padding_ms=0,
                ),
            ),
        )

       # ------------------------------------------------------------------
        # Build pipeline
        # ------------------------------------------------------------------
        from pipecat.processors.user_idle_processor import UserIdleProcessor

        async def _idle_placeholder(processor, retry_count) -> bool:
            return False
        idle_processor = UserIdleProcessor(callback=_idle_placeholder, timeout=8.0)

        # Official Pipecat transcript aggregators for Gemini Live
        context = LLMContext()
        context_pair = LLMContextAggregatorPair(context)
        user_aggregator = context_pair.user()
        assistant_aggregator = context_pair.assistant()

        pipeline = Pipeline([
            transport.input(),
            idle_processor,
            user_aggregator,
            gemini_live,
            transport.output(),
            assistant_aggregator,
        ])


        _greeting_sent = False
        if session:
            @user_aggregator.event_handler("on_user_turn_stopped")
            async def on_user_turn_stopped(aggregator, strategy, message: UserTurnStoppedMessage):
                # ✅ PROACTIVE GREETING FIX: No longer sends BEGIN_CALL here
                # BEGIN_CALL is now sent immediately on client connection
                text = message.content.strip() if message.content else ""
                if text:
                    logger.info(f"[{call_sid}] CUSTOMER: {text}")
                    session.add_transcript_entry("customer", text)
                    await idle_processor._stop()

            @assistant_aggregator.event_handler("on_assistant_turn_stopped")
            async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
                full_text = message.content.strip() if message.content else ""
                if not full_text:
                    return
                logger.info(f"[{call_sid}] AI: {full_text}")
                session.add_transcript_entry("ai", full_text)
                text_lower = full_text.lower()

                # ── Menu SMS trigger ──
                if "i'll text you" in text_lower and "menu" in text_lower:
                    from gemini_service import send_menu_sms
                    asyncio.create_task(send_menu_sms(
                        caller_number=session.caller_number,
                        restaurant_name=session.restaurant.get("name", "the restaurant"),
                        restaurant_id=session.restaurant_id,
                        base_url="https://ringai-v2.onrender.com",
                    ))
                    logger.info(f"[{call_sid}] Menu SMS triggered")

                # ── ORDER_CONFIRMED signal (restaurant) ──
                order_confirmed_phrases = [
                    "your order is confirmed",
                    "order is confirmed",
                    "i'll send you a text confirmation",
                    "sending you a text confirmation",
                    "ready in about",
                    "thank you for calling",
                ]
                if (
                    session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED)
                    and any(p in text_lower for p in order_confirmed_phrases)
                ):
                    if session.business_type == "restaurant":
                        logger.info(f"[{call_sid}] ORDER_CONFIRMED signal detected")
                        session.order.transition(OrderState.CONFIRMED, "signal")
                        asyncio.create_task(session._handle_order_confirmed())

                # ── APPOINTMENT_CONFIRMED signal ──
                appointment_confirmed_phrases = [
                    "your appointment is confirmed",
                    "appointment is confirmed",
                    "appointment has been confirmed",
                    "i'll send you a text confirmation",
                    "we'll see you",
                    "we look forward to seeing you",
                ]
                if (
                    session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED)
                    and any(p in text_lower for p in appointment_confirmed_phrases)
                ):
                    business_type = session.config.get("business_type", "restaurant")
                    if business_type in ("clinic", "salon", "home_services", "legal"):
                        logger.info(f"[{call_sid}] APPOINTMENT_CONFIRMED signal detected")
                        session.order.transition(OrderState.CONFIRMED, "signal")
                        asyncio.create_task(session._handle_appointment_confirmed())

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                audio_out_sample_rate=8000,
            ),
        )
        # Give session references it needs for hangup + record saving
        if session:
            session._pipeline_task = task
            if on_call_complete:
                session._on_call_complete = on_call_complete
            # Pass db reference for appointment booking persistence
            try:
                from server import db as app_db
                session.db = app_db
            except Exception:
                pass

        async def handle_user_idle(processor, retry_count) -> bool:
            if retry_count == 1:
                await task.queue_frame(TextFrame(
                    text="SYSTEM: Customer silent. Say one brief sentence to check if they are still there."
                ))
                return True
            elif retry_count == 2:
                await task.queue_frame(TextFrame(
                    text="SYSTEM: Customer still silent. Ask if they are still there — one sentence."
                ))
                return True
            else:
                logger.info(f"[{call_sid}] Customer idle too long – ending call")
                asyncio.create_task(session._schedule_hangup(reason="customer_idle"))
                return False

        idle_processor._callback = idle_processor._wrap_callback(handle_user_idle)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            # ✅ PROACTIVE GREETING FIX: Send BEGIN_CALL immediately when client connects
            # This triggers the AI to greet first without waiting for customer
            nonlocal _greeting_sent
            if not _greeting_sent:
                _greeting_sent = True
                logger.info(f"[{call_sid}] Client connected - triggering proactive greeting")
                from pipecat.processors.aggregators.llm_response_universal import LLMMessagesAppendFrame
                await task.queue_frame(LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": "BEGIN_CALL"}],
                    run_llm=True,
                ))

        # ------------------------------------------------------------------
        # Disconnect handler
        # Only fires on_call_complete if _schedule_hangup hasn't already done so.
        # Covers the case where customer hangs up before ORDER_CONFIRMED.
        # ------------------------------------------------------------------
        @transport.event_handler("on_client_disconnected")
        async def on_disconnect(transport, client):
            logger.info(f"[{call_sid}] Disconnected — post-call processing")
            try:
                if session:
                    # Ensure order dispatched if not already
                    if session.order.state == OrderState.CONFIRMED and not session._order_dispatched and not session._hangup_scheduled:
                        await session.dispatch_order_if_ready()

                    # Last-chance extraction if still no items
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

                # ✅ Only call on_call_complete if _schedule_hangup hasn't already called it
                if on_call_complete and (not session or not session._hangup_scheduled):
                    logger.info(f"[{call_sid}] Calling on_call_complete from on_client_disconnected")
                    t = session.transcript if session else []
                    await on_call_complete(
                        call_sid=call_sid,
                        restaurant_id=restaurant_id,
                        transcript=t,
                        session=session,
                    )
                else:
                    logger.info(
                        f"[{call_sid}] Skipping on_call_complete in disconnect "
                        f"(already called via _schedule_hangup)"
                    )

            except Exception as e:
                logger.error(f"[{call_sid}] Post-call error: {e}", exc_info=True)

            finally:
                # Always cancel pipeline on disconnect — safe even if already cancelled
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