"""
Pipecat + Gemini Live Audio Call Pipeline for RingAI

Handles real-time phone calls via Telnyx:
  Telnyx → WebSocket → TelnyxFrameSerializer
  → GeminiLiveLLMService (native audio: STT + LLM + TTS in one model, ~200-400ms latency)
  → TelnyxFrameSerializer → Telnyx

Behavior:
  - on_call_complete fires exactly once per call via _fire_on_call_complete helper
  - _on_call_complete_fired flag guards against double-fire across all call sites
  - session._on_call_complete stored so any path can invoke it via the helper
  - Hangup via pipeline task cancel (TelnyxFrameSerializer handles WS close)
  - Pipeline teardown stops Gemini Live billing
  - Order dispatch with 3 retries + backoff

Requires:
  - GOOGLE_API_KEY, TELNYX_API_KEY env vars
  - pip install 'pipecat-ai[google,websocket,silero,telnyx]'
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

    try:
        from pipecat.serializers.telnyx import TelnyxFrameSerializer
        _TELNYX_SERIALIZER_AVAILABLE = True
    except ImportError:
        _TELNYX_SERIALIZER_AVAILABLE = False
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

# Ambient background noise (comfort noise) — soft cafe ambience mixed into outbound audio
# so calls feel alive during silent moments. Gated by env var, gracefully degrades.
try:
    from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
    _SOUNDFILE_MIXER_AVAILABLE = True
except Exception as _mixer_import_err:
    SoundfileMixer = None  # type: ignore
    _SOUNDFILE_MIXER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        f"SoundfileMixer unavailable (soundfile package not installed?): {_mixer_import_err}"
    )

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


def _build_ambient_mixer():
    """Construct a SoundfileMixer for cafe ambient noise, or return None.

    Env-gated by AMBIENT_NOISE_ENABLED (default "true"). Gracefully degrades
    to None when the soundfile package is missing, the asset file is missing,
    or construction fails — calls work normally without ambient noise.
    """
    if os.getenv("AMBIENT_NOISE_ENABLED", "true").lower() != "true":
        return None
    if not _SOUNDFILE_MIXER_AVAILABLE:
        return None
    try:
        from pathlib import Path
        _ambient_path = Path(__file__).parent / "assets" / "cafe_ambience_8k_mono.wav"
        if not _ambient_path.exists():
            logger.warning(f"[ambient_noise] asset file not found at {_ambient_path}, disabling")
            return None
        _mixer = SoundfileMixer(
            sound_files={"cafe": str(_ambient_path)},
            default_sound="cafe",
            volume=0.06,   # very quiet — tune via AMBIENT_NOISE_VOLUME env var if needed
            loop=True,
        )
        try:
            _ambient_volume_override = float(os.getenv("AMBIENT_NOISE_VOLUME", "0.06"))
            _mixer._volume = _ambient_volume_override  # apply override before start
        except (TypeError, ValueError):
            pass
        logger.info(f"[ambient_noise] mixer initialized from {_ambient_path}")
        return _mixer
    except Exception as _mixer_init_err:
        logger.error(f"[ambient_noise] failed to initialize mixer: {_mixer_init_err}")
        return None


# ── Gemini Live function-calling tool definition ──────────────────────────
try:
    from google.genai import types as _genai_types

    CHECK_AVAILABILITY_TOOL = _genai_types.Tool(
        function_declarations=[
            _genai_types.FunctionDeclaration(
                name="check_availability",
                description=(
                    "Check available appointment slots for a specific date. "
                    "Call this before confirming any appointment time with the customer."
                ),
                parameters=_genai_types.Schema(
                    type=_genai_types.Type.OBJECT,
                    properties={
                        "date": _genai_types.Schema(
                            type=_genai_types.Type.STRING,
                            description="Date in YYYY-MM-DD format (e.g. '2026-04-15')",
                        ),
                        "service_name": _genai_types.Schema(
                            type=_genai_types.Type.STRING,
                            description="Name of the service the customer wants to book",
                        ),
                    },
                    required=["date"],
                ),
            )
        ]
    )

    COMPUTE_ORDER_TOTAL_TOOL = _genai_types.Tool(
        function_declarations=[
            _genai_types.FunctionDeclaration(
                name="compute_order_total",
                description=(
                    "Compute the exact total price (in dollars) for the order. "
                    "Call this RIGHT BEFORE doing the readback to the customer. "
                    "Always use the returned total_dollars verbatim — never "
                    "compute the total yourself."
                ),
                parameters=_genai_types.Schema(
                    type=_genai_types.Type.OBJECT,
                    properties={
                        "items": _genai_types.Schema(
                            type=_genai_types.Type.ARRAY,
                            items=_genai_types.Schema(
                                type=_genai_types.Type.OBJECT,
                                properties={
                                    "name": _genai_types.Schema(
                                        type=_genai_types.Type.STRING,
                                        description=(
                                            "Exact menu item name as it appears in "
                                            "the menu (e.g. 'Chicken Dum Biryani (Regular)')"
                                        ),
                                    ),
                                    "quantity": _genai_types.Schema(
                                        type=_genai_types.Type.INTEGER,
                                        description="Number of this item ordered (>=1)",
                                    ),
                                },
                                required=["name", "quantity"],
                            ),
                            description="List of items in the order with quantities",
                        ),
                    },
                    required=["items"],
                ),
            )
        ]
    )
    _TOOLS_AVAILABLE = True
except Exception as _tools_err:
    CHECK_AVAILABILITY_TOOL = None
    COMPUTE_ORDER_TOTAL_TOOL = None
    _TOOLS_AVAILABLE = False
    logging.getLogger(__name__).warning(f"Tool definition failed: {_tools_err}")


# Stub base class when pipecat is not available
if not _PIPECAT_AVAILABLE:
    class _PipecatStubBase:
        def __init__(self, **kwargs):
            pass
    GeminiLiveLLMService = _PipecatStubBase


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
        self._user_text_buffer: List[str] = []
        self._last_captured_from_model_turn = False
        # Guards VAD interruption during critical function call window
        self._fn_in_progress = False
        # Guards VAD interruption during opening greeting window
        self._greeting_in_progress = False

    # _handle_interruption is defined below _flush_ai_buffer (single definition)

    async def _run_function_call(self, tool_call, llm_context=None):
        """
        Set _fn_in_progress BEFORE the handler coroutine is scheduled.
        ...
        Note: llm_context made optional — Pipecat 0.0.104 calls this with
        just (tool_call) in some code paths (e.g. mid-turn function calls
        via compute_order_total) and (tool_call, llm_context) in others
        (e.g. check_availability). Forward whatever we received.
        """
        self._fn_in_progress = True
        try:
            if llm_context is not None:
                await super()._run_function_call(tool_call, llm_context)
            else:
                await super()._run_function_call(tool_call)
        finally:
            self._fn_in_progress = False

    async def _cancel_function_call(self, tool_call_id):
        """
        Block cancellation when a function call is actively executing.
        Pipecat calls this from broadcast_interruption which bypasses
        _handle_interruption — so we guard here as a second line of defence.
        """
        if self._fn_in_progress:
            logger.debug(
                f"Function call cancel suppressed — fn_in_progress "
                f"(tool_call_id={tool_call_id})"
            )
            return
        await super()._cancel_function_call(tool_call_id)

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

    async def _handle_msg_input_transcription(self, message):
        if (
            message.server_content
            and message.server_content.input_transcription
            and message.server_content.input_transcription.text
        ):
            self._user_text_buffer.append(
                message.server_content.input_transcription.text
            )
        await super()._handle_msg_input_transcription(message)

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
        """Suppress VAD interruptions during function calls + reset capture flag."""
        self._last_captured_from_model_turn = False
        if self._fn_in_progress:
            logger.debug("VAD interruption suppressed — function call in progress")
            return
        await super()._handle_interruption()

    async def _create_initial_response(self):
        """
        Suppress Pipecat's automatic BEGIN_CALL injection.
        Gemini 3.1 has no proactive audio — customer speaks first,
        AI greets naturally on the first real customer turn.
        TODO: Remove this override when Gemini 3.1 adds proactive audio support.
        """
        pass


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_pipeline_available() -> bool:
    return all([
        os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY"),
        os.environ.get("TELNYX_API_KEY"),
    ])

# ---------------------------------------------------------------------------
# VAD configuration
# ---------------------------------------------------------------------------
VAD_STOP_SECS  = float(os.environ.get("VAD_STOP_SECS",  "0.2"))
VAD_START_SECS = float(os.environ.get("VAD_START_SECS", "0.2"))
VAD_MIN_VOLUME = float(os.environ.get("VAD_MIN_VOLUME", "0.3"))

# Seconds to wait after farewell TTS before hanging up
HANGUP_DELAY_SECS = float(os.environ.get("HANGUP_DELAY_SECS", "1.5"))

# Telnyx-side ring timeout on /actions/transfer — destination has this long to
# answer before Telnyx aborts the outbound dial and fires call.hangup on the
# B-leg. Durable across our backend restarts.
TRANSFER_RING_TIMEOUT_SECS = int(os.environ.get("TRANSFER_RING_TIMEOUT_SECS", "30"))

# In-process safety net — fires slightly later than the Telnyx-side timeout so
# the webhook gets first crack at cleanup. Catches missed/delayed call.hangup
# or call.bridged webhooks.
TRANSFER_FALLBACK_TIMEOUT_SECS = float(os.environ.get("TRANSFER_FALLBACK_TIMEOUT_SECS", "35"))



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
        lang: str = "en",
        restaurant_phone_number: Optional[str] = None,
    ):
        self.call_sid       = call_sid
        self.restaurant_id  = restaurant_id
        self.caller_number  = caller_number
        self.restaurant     = restaurant
        self.config         = config
        self.menu_index     = MenuIndex(menu_items)
        self.services       = services or []  # For appointment businesses
        self.lang           = lang  # ISO 639-1 code; drives signals_for() phrase matching
        # Our AI DID. When set, _transfer_call refuses to dial it (loop guard).
        # None disables the guard — keeps legacy tests/callers working.
        self.restaurant_phone_number = restaurant_phone_number
        self.transcript: List[Dict] = []
        self.started_at     = datetime.now(timezone.utc).isoformat()
        self.order          = LiveOrder(
            restaurant_id=restaurant_id,
            call_sid=call_sid,
            caller_number=caller_number,
        )
        self._order_dispatched  = False
        self._order_confirmed_handled = False  # guards _handle_order_confirmed re-entry
        self._escalated         = False
        self._escalation_deferred = False  # escalation deferred until order completes
        self._hangup_scheduled  = False  # "we've committed to ending this call"
        self._on_call_complete_fired = False  # "call_records insert + dashboard notify has run"
        # Transfer race-fix state — see _schedule_hangup escalation branch
        self._transfer_in_progress = False  # transfer dispatched, awaiting call.bridged or fallback
        self._bridge_succeeded = False       # set by call.bridged webhook handler
        self._transfer_fallback_task: Optional[Any] = None  # 35s safety timeout
        self._booking_dispatched = False  # For appointment businesses
        self._reservation_dispatched = False  # For restaurant reservations — live signal fired
        # Set True ONLY after a reservation is successfully booked (live or
        # post-call). _reservation_dispatched flips the moment the live signal
        # fires (before extraction), so it cannot gate the post-call fallback;
        # this flag does. It also prevents double-booking across both paths.
        self._reservation_booked = False
        self._reservation_lock = asyncio.Lock()  # serializes live + post-call reservation dispatch
        self._reservation_unavailable: Optional[Dict[str, Any]] = None  # last availability failure, for a single end-of-call apology
        self._reservation_notified = False  # guard: at most one reservation-outcome SMS per call
        self._appointment_total  = 0      # price_cents sum for booked services
        self._sms_count         = 0      # number of SMS sent this call (for cost tracking)
        self._detected_order_type = None  # "pickup", "delivery", or "reservation" — locked from conversation
        self._call_timer_task = None     # auto-escalation after max duration
        self._actual_duration_seconds = None  # exact duration from call status callback

        # Business type for horizontal platform support
        self.business_type = config.get("business_type", "restaurant") if config else "restaurant"
        self.is_open = True  # Set by create_call_pipeline after hours check
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
            # Guard: skip if we already handled order confirmation (prevents double-fire
            # from duplicate add_transcript_entry calls for the same AI message)
            if getattr(self, '_last_signal_text', None) == text:
                return
            # Merge the existing English keyword + ESCALATE_TO_HUMAN token detection
            # with per-language phrase triggers. OR-merge: either source can set True.
            from language_prompts import signals_for
            base_signals = detect_call_signals(text)
            lang_signals = signals_for(self.lang, text)
            signals = {
                k: bool(base_signals.get(k)) or bool(lang_signals.get(k))
                for k in (set(base_signals) | set(lang_signals))
            }
            if not any(signals.values()):
                return  # no signals — skip processing
            self._last_signal_text = text  # mark this message as processed

            if signals["order_confirmed"] and not self._hangup_scheduled:
                logger.info(f"[{self.call_sid}] ORDER_CONFIRMED signal detected")
                self.order.transition(OrderState.CONFIRMED, "confirmed via AI signal")
                self.order.confirmed_at = datetime.now(timezone.utc).isoformat()
                if self._escalation_deferred:
                    # Order + deferred escalation: dispatch order, then transfer to human
                    async def _order_then_escalate():
                        await self._handle_order_confirmed()
                        await asyncio.sleep(3.0)
                        if not self._escalated:
                            logger.info(f"[{self.call_sid}] Executing deferred escalation after order completion")
                            self._escalation_deferred = False
                            self._escalated = True
                            await self._schedule_hangup(reason="escalation", _skip_guard=True)
                    asyncio.ensure_future(_order_then_escalate())
                else:
                    asyncio.ensure_future(self._handle_order_confirmed())
                return  # ORDER_CONFIRMED handled — skip ESCALATE in same message

            if signals["escalate_to_human"] and not self._escalated and not self._escalation_deferred:
                # Escalation deferred is already set from customer speech detection —
                # the deferred handler will fire after order confirmation, so skip here
                logger.info(f"[{self.call_sid}] ESCALATE signal detected")
                self.order.transition(OrderState.ESCALATED, "escalation via AI signal")
                self._escalated = True
                asyncio.ensure_future(self._schedule_hangup(reason="escalation"))

    # ------------------------------------------------------------------
    # Order confirmed — dispatch then hang up
    # ------------------------------------------------------------------

    async def _fire_on_call_complete(self) -> None:
        """Fire on_call_complete exactly once per call. All call sites route through here.

        Flag flip is BEFORE the await so a re-entrant invocation during the
        callback is short-circuited. Exceptions in the callback are logged and
        swallowed; the flag stays True (we don't retry analytics/billing).
        """
        if self._on_call_complete_fired:
            return
        self._on_call_complete_fired = True
        if not self._on_call_complete:
            return
        try:
            logger.info(f"[{self.call_sid}] Firing on_call_complete")
            await self._on_call_complete(
                call_sid=self.call_sid,
                restaurant_id=self.restaurant_id,
                transcript=self.transcript,
                session=self,
            )
        except Exception as e:
            logger.error(f"[{self.call_sid}] on_call_complete error: {e}", exc_info=True)

    async def _handle_order_confirmed(self):
        """Handle restaurant orders — dispatch order then hang up."""
        # Re-entry guard: only handle once even if called from multiple detection paths
        if self._order_confirmed_handled:
            logger.info(f"[{self.call_sid}] ORDER_CONFIRMED already handled — skipping duplicate")
            return
        self._order_confirmed_handled = True

        if not self.is_open:
            logger.warning(f"[{self.call_sid}] ORDER_CONFIRMED blocked — restaurant is CLOSED")
            return
        self._hangup_scheduled = True
        if not self._order_dispatched:
            await self.dispatch_order_if_ready()
        # Multi-intent: a table may have been confirmed alongside the order.
        # Book it now, in the same teardown-protected window as the order —
        # not later from on_call_complete, which races call teardown.
        await self._ensure_reservation_booked()
        await self._fire_on_call_complete()
        if self._call_timer_task:
            self._call_timer_task.cancel()
            self._call_timer_task = None
        # If escalation is deferred, let the deferred escalation handle hangup (with transfer)
        if self._escalation_deferred:
            logger.info(f"[{self.call_sid}] Skipping order_confirmed hangup — deferred escalation will handle transfer")
        else:
            await self._schedule_hangup(reason="order_confirmed", _skip_guard=True)

    async def _handle_appointment_confirmed(self):
        """Handle appointment businesses — dispatch booking then hang up."""
        self._hangup_scheduled = True
        await self.dispatch_booking(db=self.db)
        await self._fire_on_call_complete()
        await self._schedule_hangup(reason="appointment_confirmed", _skip_guard=True)

    async def _handle_reservation_confirmed(self):
        """Live RESERVATION_CONFIRMED path — book the reservation, then hang up."""
        logger.info(f"[{self.call_sid}] Processing RESERVATION_CONFIRMED")
        await self._ensure_reservation_booked()
        await self._fire_on_call_complete()
        # Delay so the AI finishes speaking before we tear down.
        await asyncio.sleep(2.0)
        await self._schedule_hangup(reason="reservation_confirmed")

    async def _ensure_reservation_booked(self) -> None:
        """Single source of truth for reservation dispatch (live + post-call).

        Idempotent and concurrency-safe via _reservation_lock + the
        _reservation_booked re-check, so the live-signal path, the
        order-confirmed path, the disconnect handler, and the on_call_complete
        fallback can all call it without double-booking. _reservation_booked is
        set only on a SUCCESSFUL dispatch, so a failed booking is retried by a
        later caller. Runs in the same awaited, teardown-protected sequence as
        the order dispatch — it must NOT be relied on solely from the tail of
        on_call_complete, which runs after the slow analyse_call_transcript and
        races call teardown (that lateness dropped the reservation).
        """
        if self.business_type != "restaurant":
            return
        if self._reservation_booked or not self.transcript:
            return
        # Same toggle build_system_prompt uses; absent → off (opt-in/plan-gated).
        _res_enabled = self.restaurant.get(
            "reservations_enabled",
            (self.config or {}).get("reservations_enabled", False),
        )
        if not _res_enabled:
            return
        async with self._reservation_lock:
            if self._reservation_booked:
                return
            try:
                from reservation_service import (
                    extract_reservation_from_transcript as _extract_reservation,
                    dispatch_reservation as _dispatch_reservation,
                )
                # extract_reservation_from_transcript early-returns None when the
                # transcript has no reservation keywords (no Gemini call), so
                # pickup-only calls don't pay for this.
                _res_data = await _extract_reservation(self.transcript, menu_index=None)
                if not _res_data:
                    return
                _res_data["customer_phone"] = self.caller_number
                _res_data["call_id"] = self.call_sid
                _res_result = await _dispatch_reservation(
                    reservation_data=_res_data,
                    restaurant=self.restaurant,
                    config=self.config or {},
                    db=self.db,
                )
                if _res_result.get("success"):
                    self._reservation_booked = True
                    self._reservation_unavailable = None  # booked — cancel any pending apology
                    logger.info(f"[{self.call_sid}] Reservation booked: {_res_result.get('reservation_id')}")
                elif _res_result.get("reason") != "reservations_disabled":
                    # Remember the failure so the single end-of-call notifier can
                    # apologize once — but only if no later attempt books it.
                    self._reservation_unavailable = {
                        "suggested_times": _res_result.get("suggested_times", []),
                        "reservation_date": _res_result.get("reservation_date", ""),
                        "reservation_time": _res_result.get("reservation_time", ""),
                    }
                    logger.info(f"[{self.call_sid}] Reservation not booked: {_res_result.get('reason')}")
            except Exception as e:
                logger.error(f"[{self.call_sid}] _ensure_reservation_booked error: {e}", exc_info=True)

    async def _notify_reservation_unavailable_if_pending(self) -> None:
        """Send the customer-facing 'couldn't confirm your table' SMS at most ONCE
        per call, and only if a reservation was requested but never booked.

        Called once at the very end of the call (the disconnect handler), AFTER
        every booking attempt — so a reservation that booked on a later retry
        never also gets an apology (mutually exclusive with the confirmation via
        _reservation_booked), and a persistently unavailable one is apologized for
        exactly once, not once per dispatch attempt.
        """
        if self.business_type != "restaurant":
            return
        if self._reservation_booked or self._reservation_notified:
            return
        if not self._reservation_unavailable:
            return
        if not (self.config or {}).get("sms_enabled", True) or not self.caller_number:
            return
        self._reservation_notified = True
        info = self._reservation_unavailable
        try:
            from reservation_service import send_reservation_unavailable_sms
            await send_reservation_unavailable_sms(
                customer_phone=self.caller_number,
                restaurant_name=self.restaurant.get("name", "the restaurant"),
                reservation_date=info.get("reservation_date", ""),
                reservation_time=info.get("reservation_time", ""),
                suggested_times=info.get("suggested_times", []),
            )
            logger.info(f"[{self.call_sid}] Reservation-unavailable SMS sent (single, end-of-call)")
        except Exception as e:
            logger.error(f"[{self.call_sid}] Reservation-unavailable SMS error: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Schedule hangup — calls on_call_complete FIRST, then terminates
    # ------------------------------------------------------------------

    async def _schedule_hangup(self, reason: str = "order_confirmed", _skip_guard: bool = False):
        if not _skip_guard and self._hangup_scheduled:
            return
        self._hangup_scheduled = True
        logger.info(
            f"[{self.call_sid}] Hangup scheduled in {HANGUP_DELAY_SECS}s — reason: {reason}"
        )
        await asyncio.sleep(HANGUP_DELAY_SECS)

        import telnyx_service

        # For escalation — transfer to human if phone number is configured
        if reason == "escalation":
            # Fire on_call_complete in the background. on_call_complete calls
            # analyse_call_transcript, which makes a Gemini API call that can
            # take 12-16s when Gemini 503s and retries. Awaiting it
            # synchronously here delays the actual /actions/transfer by the
            # same amount — the customer hears "Please hold" then dead air
            # while the analytics path retries. The escalation record will
            # be saved asynchronously; the helper is idempotent so any
            # downstream cleanup that also calls it is a no-op.
            asyncio.create_task(self._fire_on_call_complete())
            escalation_phone = self.config.get("escalation_phone_number") if self.config else None
            if escalation_phone:
                transferred = await self._transfer_call(escalation_phone)
                if transferred:
                    # Transfer accepted by Telnyx (200 OK). Telnyx is now
                    # dialing the destination. DO NOT cancel the pipeline or
                    # hang up the A-leg — both would abort the in-progress
                    # outbound dial. Instead:
                    #   1. Stop the media stream so Gemini Live goes idle
                    #      (no input audio = no token billing).
                    #   2. Mark transfer-in-progress so the disconnect path
                    #      and any stray cleanup know to leave the call alone.
                    #   3. Start the fallback safety timer.
                    # The pipeline is cancelled later in _handle_transfer_bridged
                    # (fired by the call.bridged webhook) or _handle_transfer_timeout.
                    self._transfer_in_progress = True
                    await telnyx_service.stop_streaming(self.call_sid)
                    self._transfer_fallback_task = asyncio.create_task(
                        self._transfer_fallback_watchdog()
                    )
                    return
            # Escalation requested but failed to dispatch (no number, or
            # transfer endpoint errored) — fall through to terminate. We
            # explicitly hang up the Telnyx leg since auto_hang_up=False.
            await telnyx_service.hang_up_call(self.call_sid)
        else:
            # Normal hangup paths (order_confirmed, appointment_confirmed,
            # reservation_confirmed, customer_idle, farewell_timeout).
            # Fire on_call_complete synchronously here — for the confirm
            # flows the helper is idempotent (already fired by _handle_*).
            # For customer_idle and farewell_timeout this is the firing
            # point that fixes the latent bug (commit 902411df). Blocking
            # is fine here: customer already heard the goodbye phrase, no
            # transfer is in flight.
            await self._fire_on_call_complete()
            # Explicit hangup required since the serializer no longer does it.
            await telnyx_service.hang_up_call(self.call_sid)

        if self._pipeline_task is not None:
            try:
                await self._pipeline_task.cancel()
                logger.info(f"[{self.call_sid}] Pipeline task cancelled")
            except Exception as e:
                logger.warning(f"[{self.call_sid}] Pipeline cancel error (non-fatal): {e}")

    async def _transfer_fallback_watchdog(self) -> None:
        """Backstop in case the call.bridged or B-leg call.hangup webhook
        never arrives — sleeps TRANSFER_FALLBACK_TIMEOUT_SECS, then forces
        teardown. If the webhook fires first, the handler cancels this task."""
        try:
            await asyncio.sleep(TRANSFER_FALLBACK_TIMEOUT_SECS)
        except asyncio.CancelledError:
            return
        logger.warning(
            f"[{self.call_sid}] Transfer fallback fired — no call.bridged or "
            f"B-leg hangup webhook in {TRANSFER_FALLBACK_TIMEOUT_SECS}s. "
            f"Forcing teardown."
        )
        await self._handle_transfer_timeout()

    async def _handle_transfer_bridged(self) -> None:
        """Called by the call.bridged webhook handler in server.py when
        Telnyx confirms the customer-human audio bridge is live. Safe to
        tear down our side now — auto_hang_up=False means cancelling the
        pipeline won't kill the A-leg, which is the bridge anchor."""
        if self._bridge_succeeded:
            return
        self._bridge_succeeded = True
        logger.info(f"[{self.call_sid}] Bridge succeeded — releasing pipeline")
        if self._transfer_fallback_task is not None:
            self._transfer_fallback_task.cancel()
            self._transfer_fallback_task = None
        if self._pipeline_task is not None:
            try:
                await self._pipeline_task.cancel()
            except Exception as e:
                logger.warning(f"[{self.call_sid}] Pipeline cancel after bridge: {e}")

    async def _handle_transfer_timeout(self) -> None:
        """Called when the destination didn't answer (B-leg call.hangup from
        Telnyx's timeout_secs, OR our fallback watchdog fires). Per product
        decision (May 2026): no TTS goodbye, no AMD, no fallback chain — just
        terminate the A-leg. Customer's experience is ringing then dead line;
        the call appears as ESCALATED in the dashboard for restaurant
        follow-up."""
        if self._bridge_succeeded:
            return  # Bridge succeeded after all — nothing to do.
        import telnyx_service
        if self._transfer_fallback_task is not None:
            self._transfer_fallback_task.cancel()
            self._transfer_fallback_task = None
        await telnyx_service.hang_up_call(self.call_sid)
        if self._pipeline_task is not None:
            try:
                await self._pipeline_task.cancel()
            except Exception as e:
                logger.warning(f"[{self.call_sid}] Pipeline cancel after transfer timeout: {e}")

    async def _transfer_call(self, to_number: str) -> bool:
        """Transfer the call to a human agent via Telnyx Call Control API.

        Delegates to telnyx_service.transfer_call so the Telnyx-side ring
        timeout (timeout_secs) is wired through consistently. The service
        layer handles the env-var guard and HTTP error mapping.
        """
        # Safety guard: never transfer to our own AI DID — would create
        # an infinite forwarding loop. Validation at config-save time is
        # the primary defense; this is belt-and-suspenders.
        if self.restaurant_phone_number:
            try:
                from security_utils import normalize_e164
                normalized_to = normalize_e164(to_number)
                normalized_self = normalize_e164(self.restaurant_phone_number)
                if normalized_to == normalized_self and normalized_to:
                    logger.error(
                        f"[{self.call_sid}] Refusing to transfer to "
                        f"{to_number} — equals our own AI DID. "
                        f"Misconfiguration; check restaurant config."
                    )
                    return False
            except ValueError as e:
                logger.warning(
                    f"[{self.call_sid}] Could not normalize for DID "
                    f"safety check: {e}"
                )

        if not os.environ.get("TELNYX_API_KEY"):
            logger.error(
                f"[{self.call_sid}] Cannot transfer call to {to_number} — "
                f"TELNYX_API_KEY environment variable is not set"
            )
            return False
        import telnyx_service
        return await telnyx_service.transfer_call(
            self.call_sid,
            to_number,
            timeout_secs=TRANSFER_RING_TIMEOUT_SECS,
        )
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
                    self.transcript, self.menu_index,
                    detected_order_type=self._detected_order_type,
                )
                # Use extracted items if present — ignore confirmed flag
                # ORDER_CONFIRMED signal is the source of truth, not extraction
                if extracted and extracted.items:
                    extracted.restaurant_id = self.restaurant_id
                    extracted.call_sid      = self.call_sid
                    extracted.caller_number = self.caller_number
                    extracted.order_confirmed = True
                    self.order = extracted
                    # Set correct order_type. The extraction LLM may infer "reservation"
                    # when the customer also booked a table, but a food order's fulfillment
                    # type is always "pickup" or "delivery". For dual-intent calls use a
                    # combined label so the stored record reflects both intents.
                    _ot = self._detected_order_type or self.order.order_type or "pickup"
                    _food = "delivery" if ("delivery" in _ot or self.order.order_type == "delivery") else "pickup"
                    if "reservation" in _ot or self.order.order_type == "reservation":
                        self.order.order_type = f"{_food}+reservation"
                    else:
                        self.order.order_type = _food
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

        # Post-call delivery address validation (distance check)
        # startswith covers both "delivery" and the combined "delivery+reservation".
        if self.order.order_type.startswith("delivery") and self.order.delivery_address:
            try:
                from delivery_utils import validate_delivery_distance
                validation = await validate_delivery_distance(
                    restaurant_address=self.restaurant.get("address", ""),
                    delivery_address=self.order.delivery_address,
                    max_radius_miles=self.restaurant.get("delivery_radius_miles", 5.0),
                )
                if not validation.get("within_radius"):
                    logger.warning(
                        f"[{self.call_sid}] Delivery address outside radius: "
                        f"{validation.get('distance_miles', '?')} miles"
                    )
                    # Send apology SMS via Telnyx
                    try:
                        from telnyx_service import send_sms
                        await send_sms(
                            to=self.caller_number,
                            body=(
                                f"Sorry, {self.restaurant.get('name', 'the restaurant')} "
                                f"cannot deliver to your address — it's outside our delivery area "
                                f"({validation.get('distance_miles', '?')} miles, max {self.restaurant.get('delivery_radius_miles', 5)} miles). "
                                f"Please call back to place a pickup order instead."
                            ),
                            idempotency_key=f"delivery_reject:{self.call_sid}",
                            metadata={
                                "purpose": "delivery_rejection",
                                "restaurant_id": self.restaurant_id,
                                "call_sid": self.call_sid,
                            },
                        )
                    except Exception as sms_err:
                        logger.error(f"[{self.call_sid}] Delivery rejection SMS error: {sms_err}")
                    self._order_dispatched = False
                    return False
                logger.info(f"[{self.call_sid}] Delivery address validated: {validation.get('distance_miles')} miles")
            except Exception as e:
                logger.warning(f"[{self.call_sid}] Delivery validation skipped: {e}")
                # Proceed anyway — don't block order if validation service fails

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
            "caller_name":        self.order.customer_name if self.order and self.order.customer_name else None,
            "started_at":         self.started_at,
            "created_at":         self.started_at,
            "ended_at":           datetime.now(timezone.utc).isoformat(),
            "status":             "ESCALATED" if self._escalated else "COMPLETED",
            "contained_by_ai":    not self._escalated,
            "escalated_to_human": self._escalated,
            "transcript":         self.transcript,
            "order":              self.order.to_dict() if self.order.items else None,
            "order_total": (
                self._appointment_total
                if self.business_type in ("clinic", "salon", "home_services", "legal")
                else self.order.total
            ),
            "kitchen_order_id":   self.order.kitchen_order_id,
            "quality_eval":       quality,
            "business_type":      self.business_type,  # Track business type
        }
        
        # Add booking info for appointment businesses
        if self._booking_dispatched and self.business_type in ("clinic", "salon", "home_services", "legal"):
            record["booking_dispatched"] = True

        # ── Internal cost tracking (admin only) ──
        duration_secs = getattr(self, "_actual_duration_seconds", None)
        if duration_secs is None:
            # Fallback: estimate from started_at to now
            try:
                started = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
                duration_secs = int((datetime.now(timezone.utc) - started).total_seconds())
            except Exception:
                duration_secs = 0

        duration_minutes = duration_secs / 60.0

        # Voice cost: $0.0085/min ceil per minute — TODO: update for Telnyx (~$0.0046/min US local)
        import math
        cost_voice = math.ceil(duration_minutes) * 0.0085

        # SMS cost: $0.0083/message — TODO: update for Telnyx (~$0.0040/message US)
        sms_count = getattr(self, "_sms_count", 0)
        cost_sms = sms_count * 0.0083

        # Gemini Live: free preview — track duration for future billing
        # Estimated future cost: ~$0.008/min when priced
        cost_gemini_live = 0.0  # free preview

        # Gemini extraction tokens: $0.075/1M input + $0.30/1M output
        # We track total tokens as combined input+output approximation
        # Real split unavailable without modifying return signature
        from gemini_service import extract_order_from_transcript
        extract_tokens = getattr(extract_order_from_transcript, "_last_tokens", 0)
        # For appointment businesses, use booking extraction tokens instead
        if self.business_type in ("clinic", "salon", "home_services", "legal"):
            from appointment_service import extract_booking_from_transcript
            extract_tokens = getattr(extract_booking_from_transcript, "_last_tokens", 0)
        # Approximate: 70% input, 30% output
        cost_gemini_extract = (
            (extract_tokens * 0.7 / 1_000_000) * 0.075 +
            (extract_tokens * 0.3 / 1_000_000) * 0.30
        )

        cost_total = cost_voice + cost_sms + cost_gemini_live + cost_gemini_extract

        record["cost_voice_cents"] = round(cost_voice * 100, 4)
        record["cost_sms_cents"] = round(cost_sms * 100, 4)
        record["cost_gemini_live_cents"] = round(cost_gemini_live * 100, 4)
        record["cost_gemini_extract_cents"] = round(cost_gemini_extract * 100, 4)
        record["cost_total_cents"] = round(cost_total * 100, 4)
        record["gemini_extract_tokens"] = extract_tokens
        record["sms_count"] = sms_count
        record["duration_seconds_actual"] = duration_secs

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

        # Calculate revenue from booked service(s)
        # service_name may be comma-separated for multiple services
        booked_names = [
            s.strip().lower()
            for s in booking.get("service_name", "").split(",")
        ]
        total_cents = 0
        for svc in self.services:
            svc_name = svc.get("name", "").strip().lower()
            price = svc.get("price_cents", 0) or 0
            # Exact match first
            if svc_name in booked_names:
                total_cents += price
                continue
            # Fuzzy match — check if any booked name contains or is contained
            # by the service name (handles "Standard Haircut" vs "Haircut" etc.)
            if any(
                svc_name in b or b in svc_name
                for b in booked_names
                if len(b) > 4  # avoid matching short words like "cut"
            ):
                total_cents += price
        self._appointment_total = total_cents
        logger.info(
            f"[{self.call_sid}] Appointment revenue: "
            f"${total_cents/100:.2f} for {booking.get('service_name')}"
        )

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
            if result.get("sms_sent"):
                self._sms_count += 1
        else:
            logger.warning(f"[{self.call_sid}] Appointment dispatch partial: {result}")

        return True


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Structured booking intent classifier
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as dc_field
import re as _re
from datetime import date as _date, timedelta as _td


@dataclass
class BookingIntent:
    date_str: Optional[str]               # "YYYY-MM-DD" or None
    service_name: Optional[str]           # matched service name or None
    confidence: float                     # 0.0–1.0
    trigger: str                          # what drove the classification
    already_injected: bool = False        # prevents double-injection


def classify_booking_intent(
    transcript: List[Dict],
    services: List[Dict],
    order_state_confirmed: bool,
    timezone_str: str = "UTC",
) -> BookingIntent:
    """
    Structured intent classifier for appointment availability checks.

    Examines:
      - Conversation position (must be in date-negotiation, not post-confirm)
      - Last N customer turns for explicit/relative/named dates
      - All turns for service name mentions
      - Confidence scoring across multiple signals

    Returns BookingIntent with confidence 0 if no check is warranted.
    """
    # Don't check after booking is already confirmed
    if order_state_confirmed:
        return BookingIntent(None, None, 0.0, "already_confirmed")

    # Need at least 2 transcript entries to have context
    if len(transcript) < 2:
        return BookingIntent(None, None, 0.0, "insufficient_context")

    # Resolve against business local timezone, not UTC.
    # At 10pm CDT (UTC-5), UTC date is already the next calendar day —
    # using UTC here causes "tomorrow" to resolve one day too far ahead.
    try:
        import pytz as _pytz
        _tz = _pytz.timezone(timezone_str)
        today = datetime.now(_pytz.utc).astimezone(_tz).date()
    except Exception:
        today = _date.today()

    date_str = None
    date_confidence = 0.0
    date_trigger = "none"

    # Search recent customer turns (last 10 entries)
    recent = transcript[-10:]
    customer_turns = [e for e in recent if e.get("role") == "customer"]
    all_text = " ".join(e.get("text", "") for e in recent).lower()
    customer_text = " ".join(e.get("text", "") for e in customer_turns).lower()

    # ── 1. Explicit ISO / numeric dates ──────────────────────────────────
    iso_match = _re.search(r"\b(\d{4}-\d{2}-\d{2})\b", all_text)
    if iso_match:
        date_str = iso_match.group(1)
        date_confidence = 1.0
        date_trigger = "iso_date"

    # ── 2. Month + day  ("march 29", "april 15th", "april fifth") ─────
    if not date_str:
        months = {
            "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
            "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        }
        # Word ordinals for spoken dates ("fifth", "twenty-first", etc.)
        word_ordinals = {
            "first":1,"second":2,"third":3,"fourth":4,"fifth":5,
            "sixth":6,"seventh":7,"eighth":8,"ninth":9,"tenth":10,
            "eleventh":11,"twelfth":12,"thirteenth":13,"fourteenth":14,"fifteenth":15,
            "sixteenth":16,"seventeenth":17,"eighteenth":18,"nineteenth":19,"twentieth":20,
            "twenty-first":21,"twenty-second":22,"twenty-third":23,"twenty-fourth":24,
            "twenty-fifth":25,"twenty-sixth":26,"twenty-seventh":27,"twenty-eighth":28,
            "twenty-ninth":29,"thirtieth":30,"thirty-first":31,
        }
        month_pattern = "|".join(months.keys())
        ordinal_pattern = "|".join(word_ordinals.keys())

        # Try numeric day first ("april 15th", "march 29")
        m = _re.search(
            rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
            customer_text
        )
        # Then try word ordinal ("april fifth", "march twenty-ninth")
        if not m:
            m = _re.search(
                rf"\b({month_pattern})\s+({ordinal_pattern})\b",
                customer_text
            )
            if m:
                try:
                    month_num = months[m.group(1)]
                    day_num = word_ordinals[m.group(2)]
                    year = today.year if month_num >= today.month else today.year + 1
                    candidate = _date(year, month_num, day_num)
                    date_str = candidate.strftime("%Y-%m-%d")
                    date_confidence = 0.9
                    date_trigger = "month_word_ordinal"
                except ValueError:
                    pass
        elif m:
            try:
                month_num = months[m.group(1)]
                day_num = int(m.group(2))
                year = today.year if month_num >= today.month else today.year + 1
                candidate = _date(year, month_num, day_num)
                date_str = candidate.strftime("%Y-%m-%d")
                date_confidence = 0.95
                date_trigger = "month_day"
            except ValueError:
                pass

    # ── 3. Relative words ─────────────────────────────────────────────
    if not date_str:
        if "today" in customer_text:
            date_str = today.strftime("%Y-%m-%d")
            date_confidence = 0.9
            date_trigger = "relative_today"
        elif "tomorrow" in customer_text:
            date_str = (today + _td(days=1)).strftime("%Y-%m-%d")
            date_confidence = 0.9
            date_trigger = "relative_tomorrow"
        elif "day after tomorrow" in customer_text:
            date_str = (today + _td(days=2)).strftime("%Y-%m-%d")
            date_confidence = 0.85
            date_trigger = "relative_day_after"

    # ── 4. Named weekdays ("this friday", "next monday") ──────────────
    if not date_str:
        day_names = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        this_next = _re.search(
            r"\b(this|next)?\s*(" + "|".join(day_names) + r")\b",
            customer_text
        )
        if this_next:
            modifier = this_next.group(1) or "this"
            target_day = day_names.index(this_next.group(2))
            days_ahead = (target_day - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7 if modifier == "next" else 0
            elif modifier == "next":
                days_ahead += 7
            date_str = (today + _td(days=days_ahead)).strftime("%Y-%m-%d")
            date_confidence = 0.8
            date_trigger = f"weekday_{this_next.group(2)}"

    if not date_str or date_confidence < 0.5:
        return BookingIntent(None, None, 0.0, "no_date_found")

    # ── Service name resolution ────────────────────────────────────────
    matched_service = None
    service_confidence = 0.0

    for svc in services:
        svc_name = svc.get("name", "").lower()
        if svc_name in all_text:
            matched_service = svc.get("name")
            service_confidence = 1.0
            break
        # Partial word match (e.g. "haircut" matches "Standard Haircut")
        words = svc_name.split()
        if any(w in all_text for w in words if len(w) > 4):
            if service_confidence < 0.7:
                matched_service = svc.get("name")
                service_confidence = 0.7

    # Fallback: single service business
    if not matched_service and len(services) == 1:
        matched_service = services[0].get("name")
        service_confidence = 0.6

    overall_confidence = date_confidence * max(service_confidence, 0.5)

    return BookingIntent(
        date_str=date_str,
        service_name=matched_service,
        confidence=overall_confidence,
        trigger=f"{date_trigger}|service={'matched' if matched_service else 'fallback'}",
    )


async def create_call_pipeline(
    websocket,
    system_prompt: str,
    restaurant_id: str,
    call_sid: str,
    stream_sid: str = "",
    on_call_complete: Optional[Callable] = None,
    session: Optional[CallSession] = None,
    voice: Optional[str] = None,
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

        if not _TELNYX_SERIALIZER_AVAILABLE:
            logger.error(f"[{call_sid}] TelnyxFrameSerializer not installed (pipecat-ai[telnyx] missing)")
            return None
        # auto_hang_up=False: every hangup path in this module now invokes
        # telnyx_service.hang_up_call(call_sid) explicitly before cancelling
        # the pipeline. The serializer's implicit hangup-on-EndFrame killed
        # in-progress transfers (race window between transfer-accepted and
        # bridge-established); explicit ownership lets the escalation path
        # cancel the pipeline AFTER call.bridged without ending the A-leg.
        _serializer = TelnyxFrameSerializer(
            stream_id=stream_sid or call_sid,
            outbound_encoding="PCMU",
            inbound_encoding="PCMU",
            call_control_id=call_sid,
            api_key=os.environ.get("TELNYX_API_KEY", ""),
            params=TelnyxFrameSerializer.InputParams(auto_hang_up=False),
        )
        # ── Ambient noise mixer (optional, env-gated, graceful) ─────────────────
        # AMBIENT_NOISE_ENABLED=false in env disables. Mixer creation failures
        # (missing file, missing package) silently degrade to no ambient noise —
        # calls work normally without it.
        _ambient_mixer = _build_ambient_mixer()

        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                serializer=_serializer,
                audio_out_mixer=_ambient_mixer,
            ),
        )

        from pipecat.services.google.gemini_live.llm import GeminiVADParams, EndSensitivity, StartSensitivity, InputParams
        from google.genai.types import ThinkingConfig

        async def on_ai_transcript(full_text: str):
            if not session:
                return
            # on_ai_transcript is the primary signal handler for Gemini Live.
            # on_assistant_turn_stopped is NOT reliable for Gemini Live turns
            # (audio streams bypass the aggregator's frame-based turn detection),
            # so all critical signals live here.
            if full_text.startswith("SYSTEM:"):
                logger.debug(f"[{call_sid}] Skipping SYSTEM frame from transcript")
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
                session._sms_count += 1
                logger.info(f"[{call_sid}] Menu SMS triggered")

            # ── ORDER_CONFIRMED signal handled in add_transcript_entry ──
            # (detect_call_signals + _handle_order_confirmed is the single path,
            #  including the escalation_deferred flow — no duplicate here)

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

            # ── RESERVATION_CONFIRMED signal (restaurant reservations) ──
            reservation_confirmed_phrases = [
                "reservation_confirmed",
                "your reservation is confirmed",
                "reservation is confirmed",
                "i have a table for",
                "table is booked",
                "table has been reserved",
                "your table is reserved",
            ]
            if (
                session.business_type == "restaurant"
                and not session._reservation_dispatched
                and any(p in text_lower for p in reservation_confirmed_phrases)
            ):
                logger.info(f"[{call_sid}] RESERVATION_CONFIRMED signal detected")
                session._reservation_dispatched = True
                asyncio.create_task(session._handle_reservation_confirmed())

            # ── CALL_END signal — farewell phrases trigger a 30s hangup timer ──
            call_end_phrases = [
                "call_end",
                "goodbye!",
                "have a great day!",
                "have a good day!",
                "thanks for calling",
                "thank you for calling",
            ]
            if (
                session.business_type != "restaurant"
                and session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED)
                and any(p in text_lower for p in call_end_phrases)
            ):
                logger.info(f"[{call_sid}] Farewell detected — starting 30s goodbye timer")
                if not hasattr(session, '_farewell_timer') or session._farewell_timer is None:
                    async def _farewell_hangup():
                        await asyncio.sleep(30)
                        if not session._hangup_scheduled:
                            logger.info(f"[{call_sid}] 30s post-farewell silence — ending call")
                            asyncio.create_task(session._schedule_hangup(reason="farewell_timeout"))
                    session._farewell_timer = asyncio.create_task(_farewell_hangup())

        # Pass availability tool for appointment businesses, order total tool
        # for everything else (order-based businesses like restaurants).
        _tools_list = None
        if _TOOLS_AVAILABLE and session:
            is_appointment_business = session.business_type in (
                "clinic", "salon", "home_services", "legal"
            )
            _tools_collected = []
            if is_appointment_business and CHECK_AVAILABILITY_TOOL:
                _tools_collected.append(CHECK_AVAILABILITY_TOOL)
            elif not is_appointment_business and COMPUTE_ORDER_TOTAL_TOOL:
                # Restaurant / any non-appointment business uses order total tool
                _tools_collected.append(COMPUTE_ORDER_TOTAL_TOOL)
            if _tools_collected:
                _tools_list = _tools_collected

        gemini_live = RingAIGeminiLive(
            on_ai_transcript=on_ai_transcript,
            api_key=api_key,
            model=f"models/{model}",
            system_instruction=system_prompt,
            voice_id=voice,
            http_options={"api_version": "v1alpha"},
            tools=_tools_list,
            params=InputParams(
                thinking=ThinkingConfig(thinking_level="LOW"),
                output_sample_rate=8000,   # match Telnyx PCMU — no resampling needed
                vad=GeminiVADParams(
                    start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                    end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=600,
                    prefix_padding_ms=0,
                ),
            ),
        )
        session._gemini_llm = gemini_live
        # ── Shared availability fetch (used by both handler paths) ────────────
        async def _fetch_availability(date_str: str, service_name: Optional[str]) -> dict:
            from appointment_service import get_available_slots
            slots = await get_available_slots(
                restaurant_id=session.restaurant_id,
                date_str=date_str,
                service_name=service_name or None,
                services=session.services,
                config=session.config,
                db=session.db,
            )
            available = [s for s in slots if s["available"]]
            if not available:
                return {
                    "available": False,
                    "message": f"No available slots on {date_str}.",
                }
            # Return ALL available slots — truncating causes the AI to hallucinate
            # that slots exist beyond what was listed because count > len(shown slots)
            return {
                "available": True,
                "date": date_str,
                "slots": ", ".join(s["display_time"] for s in available),
                "count": len(available),
            }

        # ── Native function call handler (fast path — no VAD interference) ────
        # _fn_in_progress suppresses _handle_interruption for the duration.
        # After result_callback, we also append to context so Gemini's
        # server-side history reflects the completed tool call.
        if _tools_list and session:
            async def _handle_check_availability(params):
                date_str = params.arguments.get("date", "").strip()
                service_name = params.arguments.get("service_name", "").strip() or None
                logger.info(
                    f"[{call_sid}] check_availability (native): date={date_str} service={service_name}"
                )
                if not date_str:
                    await params.result_callback({"error": "date is required"})
                    return

                logger.info(
                    f"[{call_sid}] ✅ check_availability INVOKED by Gemini "
                    f"(tool_call_id={params.tool_call_id})"
                )
                # Note: _fn_in_progress is now managed by _run_function_call override
                try:
                    result = await _fetch_availability(date_str, service_name)
                    await params.result_callback(result)
                    import json as _json
                    from pipecat.processors.aggregators.llm_response_universal import (
                        LLMMessagesAppendFrame,
                    )
                    await task.queue_frame(LLMMessagesAppendFrame(
                        messages=[{
                            "role": "system",
                            "content": (
                                f"[check_availability completed: {_json.dumps(result)}]"
                            ),
                        }]
                    ))
                    logger.info(f"[{call_sid}] check_availability (native) result injected: {result}")
                    _intent_cache[f"{date_str}:{service_name}"] = True
                except Exception as _e:
                    logger.error(f"[{call_sid}] check_availability error: {_e}")
                    await params.result_callback({"error": "Could not check availability right now."})

            gemini_live.register_function("check_availability", _handle_check_availability)

        # ── compute_order_total handler (non-appointment businesses) ─────────
        # Fires right before the STEP 4 readback so Gemini speaks the tool's
        # total verbatim rather than computing arithmetic in-context.
        if _tools_list and COMPUTE_ORDER_TOTAL_TOOL in _tools_list:
            async def _handle_compute_order_total(params):
                args = params.arguments or {}
                items_request = args.get("items", []) or []
                logger.info(
                    f"[{call_sid}] compute_order_total INVOKED by Gemini "
                    f"with {len(items_request)} item(s)"
                )
                total_cents = 0
                resolved = []
                unresolved = []
                try:
                    for it in items_request:
                        raw_name = (it.get("name") or "").strip()
                        if not raw_name:
                            continue
                        try:
                            qty = int(it.get("quantity", 1))
                        except (TypeError, ValueError):
                            qty = 1
                        if qty < 1:
                            qty = 1
                        menu_item = (
                            session.menu_index.find(raw_name)
                            if session.menu_index else None
                        )
                        if menu_item:
                            unit_cents = int(menu_item.get("price", 0))
                            subtotal_cents = unit_cents * qty
                            total_cents += subtotal_cents
                            resolved.append({
                                "name": menu_item.get("name", raw_name),
                                "quantity": qty,
                                "unit_price_dollars": f"${unit_cents / 100:.2f}",
                                "subtotal_dollars": f"${subtotal_cents / 100:.2f}",
                            })
                        else:
                            unresolved.append(raw_name)
                    result = {
                        "total_dollars": f"${total_cents / 100:.2f}",
                        "items_resolved": resolved,
                        "items_unresolved": unresolved,
                    }
                    logger.info(
                        f"[{call_sid}] compute_order_total result: "
                        f"{result['total_dollars']} "
                        f"({len(resolved)} resolved, {len(unresolved)} unresolved)"
                    )
                    await params.result_callback(result)
                except Exception as _e:
                    logger.error(f"[{call_sid}] compute_order_total error: {_e}")
                    await params.result_callback({
                        "total_dollars": "",
                        "items_resolved": [],
                        "items_unresolved": [],
                        "error": str(_e),
                    })

            gemini_live.register_function(
                "compute_order_total", _handle_compute_order_total
            )

        # ── Classifier-based fallback path (fires when native call was cancelled) ─
        # Triggered from on_ai_transcript when the AI says a check phrase.
        # Uses BookingIntent classifier over full transcript + conversation state.
        # Injects result via both LLMMessagesAppendFrame (context) + TextFrame (prompt).
        _intent_cache: dict = {}  # date_str → bool, prevents duplicate injections

        async def _classifier_availability_check(ai_text: str):
            if not session:
                return
            if session.business_type not in ("clinic", "salon", "home_services", "legal"):
                return

            # Only fire on explicit check phrases in the AI's output
            check_phrases = [
                "one moment", "let me check", "let me look",
                "checking availability", "checking for you", "look that up",
            ]
            if not any(p in ai_text.lower() for p in check_phrases):
                return

            # Skip if native handler is currently running
            if gemini_live._fn_in_progress:
                logger.debug(f"[{call_sid}] Classifier skipped — native handler in progress")
                return

            # Also skip if native handler already handled this intent
            # (classify first so we have the cache key before fetching)

            # Run classifier over transcript + conversation state
            intent = classify_booking_intent(
                transcript=session.transcript,
                services=session.services,
                order_state_confirmed=session.order.state in (
                    OrderState.CONFIRMED, OrderState.COMPLETED
                ),
                timezone_str=session.restaurant.get("timezone", "UTC"),
            )

            logger.info(
                f"[{call_sid}] BookingIntent: date={intent.date_str} "
                f"service={intent.service_name} confidence={intent.confidence:.2f} "
                f"trigger={intent.trigger}"
            )

            if intent.confidence < 0.5 or not intent.date_str:
                logger.info(f"[{call_sid}] Classifier confidence too low — skipping injection")
                return

            # Deduplicate: skip if native handler OR a prior classifier run
            # already handled this date+service combination
            cache_key = f"{intent.date_str}:{intent.service_name}"
            if _intent_cache.get(cache_key):
                logger.debug(f"[{call_sid}] Classifier skipped — already handled {cache_key}")
                return
            _intent_cache[cache_key] = True

            try:
                import json as _json
                from pipecat.processors.aggregators.llm_response_universal import (
                    LLMMessagesAppendFrame,
                )

                result = await _fetch_availability(intent.date_str, intent.service_name)
                logger.info(
                    f"[{call_sid}] Classifier fallback injecting for "
                    f"{intent.date_str}: {result}"
                )

                # Step 1: Append to local context history so Gemini's aggregator
                # treats the function as completed for this conversation turn
                await task.queue_frame(LLMMessagesAppendFrame(
                    messages=[{
                        "role": "system",
                        "content": (
                            f"[check_availability completed via fallback: "
                            f"{_json.dumps(result)}]"
                        ),
                    }]
                ))

                # Step 2: Queue a TextFrame so the live model generates a
                # spoken response using the injected context
                if result["available"]:
                    prompt = (
                        f"SYSTEM: Availability check complete. "
                        f"For {intent.date_str}, available slots are: {result['slots']}. "
                        f"Tell the customer which times are open. "
                        f"If they asked for a specific time, confirm it if it appears in the list, "
                        f"or offer the nearest available slot. One sentence only."
                    )
                else:
                    prompt = (
                        f"SYSTEM: Availability check complete. "
                        f"No slots available on {intent.date_str}. "
                        f"Tell the customer we're fully booked that day and ask "
                        f"if they'd like to try a different date. One sentence only."
                    )

                await task.queue_frame(TextFrame(text=prompt))

            except Exception as _e:
                logger.error(f"[{call_sid}] Classifier fallback error: {_e}")
                # Don't leave cache poisoned on error
                _intent_cache.pop(cache_key, None)

       # ------------------------------------------------------------------
        # Build pipeline
        # ------------------------------------------------------------------
        from pipecat.processors.user_idle_processor import UserIdleProcessor

        async def _idle_placeholder(processor, retry_count) -> bool:
            return False
        idle_processor = UserIdleProcessor(callback=_idle_placeholder, timeout=60.0)

        # Official Pipecat transcript aggregators for Gemini Live
        from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
        from pipecat.turns.user_turn_strategies import UserTurnStrategies
        from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregatorParams
        context = LLMContext()
        context_pair = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                user_turn_strategies=UserTurnStrategies(
                    stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)]
                )
            )
        )
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
                # Use buffered transcription chunks (multiple can arrive at same timestamp)
                if hasattr(session, '_gemini_llm') and session._gemini_llm and session._gemini_llm._user_text_buffer:
                    text = "".join(session._gemini_llm._user_text_buffer).strip()
                    session._gemini_llm._user_text_buffer.clear()
                else:
                    text = message.content.strip() if message.content else ""
                if text:
                    logger.info(f"[{call_sid}] CUSTOMER: {text}")
                    session.add_transcript_entry("customer", text)
                    # Detect order type from customer speech (restaurant only)
                    if session.business_type == "restaurant":
                        _tl = text.lower()
                        _plan = session.restaurant.get("plan", "STARTER")
                        _rest_has_delivery = session.restaurant.get("offers_delivery", True)
                        _rest_has_reservations = session.restaurant.get("offers_reservations", True)
                        if any(w in _tl for w in ["delivery", "deliver", "delivered"]):
                            if _plan == "PRO" and _rest_has_delivery:
                                session._detected_order_type = "delivery"
                                logger.info(f"[{call_sid}] Order type locked: delivery (from customer)")
                            elif _rest_has_delivery:
                                # STARTER — restaurant has delivery, AI will offer escalation via prompt
                                logger.info(f"[{call_sid}] Delivery requested on STARTER — AI will offer escalation to team")
                                session._escalation_deferred = True
                            else:
                                # Restaurant doesn't offer delivery at all
                                logger.info(f"[{call_sid}] Delivery requested but restaurant doesn't deliver")
                        elif any(w in _tl for w in ["pickup", "pick up", "pick-up", "carry out", "carryout"]):
                            session._detected_order_type = "pickup"
                            logger.info(f"[{call_sid}] Order type locked: pickup (from customer)")
                        elif any(w in _tl for w in ["reservation", "reserve", "book a table", "table for"]):
                            # Same signal build_system_prompt derives reservations_enabled
                            # from (restaurant doc first, then config). When off, a table
                            # mention must NOT engage reservation logic.
                            _reservations_enabled = session.restaurant.get(
                                "reservations_enabled",
                                (session.config or {}).get("reservations_enabled", False),
                            )
                            if not _reservations_enabled:
                                # Reservations disabled — do NOT engage reservation
                                # logic: don't flip order_type (stays pickup/delivery)
                                # and don't defer escalation. The prompt's decline block
                                # instructs the AI to decline the table.
                                logger.info(f"[{call_sid}] Table mention but reservations disabled — not engaging reservation logic")
                            elif _plan == "PRO" and _rest_has_reservations:
                                _prior = session._detected_order_type if session._detected_order_type in ("pickup", "delivery") else None
                                session._detected_order_type = f"{_prior}+reservation" if _prior else "reservation"
                                logger.info(f"[{call_sid}] Order type locked: {session._detected_order_type} (from customer)")
                            elif _rest_has_reservations:
                                # STARTER — restaurant has reservations, AI will offer escalation via prompt
                                logger.info(f"[{call_sid}] Reservation requested on STARTER — AI will offer escalation to team")
                                session._escalation_deferred = True
                            else:
                                logger.info(f"[{call_sid}] Reservation requested but restaurant doesn't offer reservations")
                    # Cancel farewell timer if customer speaks again
                    if hasattr(session, '_farewell_timer') and session._farewell_timer:
                        session._farewell_timer.cancel()
                        session._farewell_timer = None

        if session.business_type not in ("restaurant",):
            @assistant_aggregator.event_handler("on_assistant_turn_stopped")
            async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
                # Classifier fallback only needed for appointment businesses
                if session and session.business_type == "restaurant":
                    return
                full_text = message.content.strip() if message.content else ""
                if not full_text or full_text.startswith("SYSTEM:"):
                    return
                asyncio.create_task(_classifier_availability_check(full_text))

        task = PipelineTask(
            pipeline,
            enable_rtvi=False,
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
                # Also check if Gemini is stuck after a cancelled function call
                # and kick it out with a recovery prompt
                if gemini_live._fn_in_progress:
                    logger.warning(f"[{call_sid}] Gemini stuck with fn_in_progress — forcing recovery")
                    gemini_live._fn_in_progress = False
                    await task.queue_frame(TextFrame(
                        text="SYSTEM: Continue the conversation. Ask the customer when they'd like to come in."
                    ))
                else:
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
            nonlocal _greeting_sent
            if not _greeting_sent:
                _greeting_sent = True
                logger.info(f"[{call_sid}] Client connected — waiting for Gemini session")
                for _ in range(40):
                    if gemini_live._session is not None:
                        break
                    await asyncio.sleep(0.1)
                if gemini_live._session is None:
                    logger.warning(f"[{call_sid}] Gemini session not ready — greeting skipped")
                    return
                await asyncio.sleep(0.3)
                try:
                    await gemini_live._session.send_realtime_input(text="__BEGIN_CALL__")
                    logger.info(f"[{call_sid}] BEGIN_CALL sent via send_realtime_input")
                except Exception as e:
                    logger.warning(f"[{call_sid}] BEGIN_CALL failed: {e}")

                # Start call duration timer — auto-escalate if call runs too long
                if session and session.business_type == "restaurant":
                    async def _call_duration_guard():
                        try:
                            _plan = session.restaurant.get("plan", "STARTER")
                            try:
                                from server import PLAN_CONFIG
                                _pf = PLAN_CONFIG.get(_plan, PLAN_CONFIG["STARTER"])
                            except ImportError:
                                _pf = {"max_call_duration_sec": 180, "warn_at_sec": 150}
                            max_seconds = _pf.get("max_call_duration_sec")
                            warn_at = _pf.get("warn_at_sec")

                            if not max_seconds:
                                # PRO — no duration limit, but keep a safety net
                                max_seconds = 240 if session._detected_order_type == "delivery" else 180
                                await asyncio.sleep(max_seconds)
                                if session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED) and not session._escalated:
                                    logger.info(f"[{call_sid}] Call duration limit ({max_seconds}s) — escalating")
                                    session._escalated = True
                                    session.order.transition(OrderState.ESCALATED, "call duration limit")
                                    await session._schedule_hangup(reason="escalation")
                                return

                            # STARTER — warn at warn_at seconds, escalate at max_seconds
                            await asyncio.sleep(warn_at)
                            if session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED) and not session._escalated:
                                logger.info(f"[{call_sid}] STARTER call duration warning at {warn_at}s")
                                # Inject system warning for AI to relay to customer
                                if hasattr(session, '_gemini_llm') and session._gemini_llm:
                                    try:
                                        await session._gemini_llm.send_text_message(
                                            "SYSTEM NOTICE: This call will be forwarded to our reception team in 30 seconds. "
                                            "Please let the customer know by saying something like: "
                                            "'Just so you know, I'll be connecting you with our team in about 30 seconds.' "
                                            "Then continue helping with the order."
                                        )
                                    except Exception as _e:
                                        logger.warning(f"[{call_sid}] Could not inject duration warning: {_e}")

                            await asyncio.sleep(max_seconds - warn_at)
                            if session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED) and not session._escalated:
                                # If order has items and is near completion, extend by 60s
                                _has_items = hasattr(session.order, 'items') and len(getattr(session.order, 'items', [])) > 0
                                if _has_items and not getattr(session, '_duration_extended', False):
                                    logger.info(f"[{call_sid}] STARTER duration limit but order in progress — extending 60s")
                                    session._duration_extended = True
                                    await asyncio.sleep(60)
                                    if session.order.state not in (OrderState.CONFIRMED, OrderState.COMPLETED) and not session._escalated:
                                        logger.info(f"[{call_sid}] STARTER extended duration exceeded — escalating")
                                        session._escalated = True
                                        session.order.transition(OrderState.ESCALATED, "starter call duration limit extended")
                                        await session._schedule_hangup(reason="escalation")
                                else:
                                    logger.info(f"[{call_sid}] STARTER call duration limit ({max_seconds}s) — escalating to reception")
                                    session._escalated = True
                                    session.order.transition(OrderState.ESCALATED, "starter call duration limit")
                                    await session._schedule_hangup(reason="escalation")
                        except asyncio.CancelledError:
                            pass
                    session._call_timer_task = asyncio.create_task(_call_duration_guard())

                
        # ------------------------------------------------------------------
        # Disconnect handler
        # Only fires on_call_complete if _schedule_hangup hasn't already done so.
        # Covers the case where customer hangs up before ORDER_CONFIRMED.
        # ------------------------------------------------------------------
        @transport.event_handler("on_client_disconnected")
        async def on_disconnect(transport, client):
            logger.info(f"[{call_sid}] Disconnected — post-call processing")
            if session and session._call_timer_task:
                session._call_timer_task.cancel()
                session._call_timer_task = None
            try:
                # Flush any remaining AI text that wasn't captured before disconnect
                if session and hasattr(session, '_gemini_llm') and session._gemini_llm:
                    await session._gemini_llm._flush_ai_buffer()
                if session:
                    # Ensure order dispatched if not already
                    if session.order.state == OrderState.CONFIRMED and not session._order_dispatched and not session._hangup_scheduled:
                        await session.dispatch_order_if_ready()

                    # Last-chance extraction if still no items
                    if not session.order.items and session.transcript:
                        extracted = await extract_order_from_transcript(
                            session.transcript, session.menu_index,
                            detected_order_type=session._detected_order_type,
                        )
                        if extracted:
                            extracted.restaurant_id = restaurant_id
                            extracted.call_sid      = call_sid
                            extracted.caller_number = session.caller_number
                            # Set correct order_type (same logic as dispatch_order_if_ready)
                            _ot = session._detected_order_type or extracted.order_type or "pickup"
                            _food = "delivery" if ("delivery" in _ot or extracted.order_type == "delivery") else "pickup"
                            extracted.order_type = f"{_food}+reservation" if ("reservation" in _ot or extracted.order_type == "reservation") else _food
                            session.order = extracted
                            result = await send_order_to_kitchen(extracted, session.restaurant)
                            if result["success"]:
                                session.order.kitchen_order_id = result["order_id"]

                    # Multi-intent / missed live signal: book any confirmed
                    # reservation now, awaited before the pipeline is cancelled
                    # in `finally`. Mirrors the order dispatch above.
                    await session._ensure_reservation_booked()

                # Route through the session's idempotent helper — fires
                # exactly once per call across every potential caller. If a
                # prior path already fired (order_confirmed, _schedule_hangup,
                # etc.), this is a no-op.
                if session is not None:
                    await session._fire_on_call_complete()
                    # Single end-of-call reservation-outcome SMS: apologize once,
                    # and only if no attempt (here or earlier) booked the table.
                    # This handler is the last code to run per call, so it runs
                    # after every booking attempt and never contradicts a confirmation.
                    await session._notify_reservation_unavailable_if_pending()
                elif on_call_complete:
                    # Defensive fallback: no session attached (pipeline failed
                    # to build past WS handshake) — invoke the callback
                    # directly with whatever we have.
                    logger.info(f"[{call_sid}] Firing on_call_complete from disconnect (no session)")
                    await on_call_complete(
                        call_sid=call_sid,
                        restaurant_id=restaurant_id,
                        transcript=[],
                        session=None,
                    )

            except Exception as e:
                logger.error(f"[{call_sid}] Post-call error: {e}", exc_info=True)

            finally:
                # Skip explicit Telnyx hangup when a transfer is or was in
                # progress for this session. After call.bridged, the WS
                # closes (our side of the pipeline is gone, by design) and
                # this disconnect handler runs — but the A-leg is the
                # bridge anchor and hanging it up tears down the
                # customer↔human audio path. Telnyx manages the bridge
                # lifecycle; we get call.hangup webhooks when it ends
                # naturally.
                #
                # For non-transfer disconnects (customer hangs up normally,
                # network drop, etc.) we still explicitly hang up — the
                # serializer's auto_hang_up=False means nothing else will.
                if session is None or not getattr(session, "_transfer_in_progress", False):
                    try:
                        import telnyx_service
                        await telnyx_service.hang_up_call(call_sid)
                    except Exception as e:
                        logger.warning(f"[{call_sid}] Telnyx hangup in disconnect failed (non-fatal): {e}")
                else:
                    logger.info(
                        f"[{call_sid}] Skipping A-leg hangup in disconnect — "
                        f"transfer in progress (bridge owned by Telnyx)"
                    )
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

def generate_twiml_stream_response(websocket_url: str, call_sid: str, status_callback_url: str = "") -> str:
    response_attr = f' statusCallback="{status_callback_url}" statusCallbackMethod="POST" statusCallbackEvent="completed"' if status_callback_url else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response{response_attr}>
    <Connect>
        <Stream url="{websocket_url}">
            <Parameter name="callSid" value="{call_sid}" />
        </Stream>
    </Connect>
</Response>"""
