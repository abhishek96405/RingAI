"""Voice pipeline regression tests for Duuutah AI.

This package covers backend/call_pipeline.py — the Pipecat + Gemini Live
real-time call pipeline. Tests focus on decision-making, state transitions,
and known regressions; raw audio plumbing is mocked.

Three named regression tests live here as load-bearing protection against
previously-fixed bugs (see the test files for full context):

- ``test_vad_no_greeting_lock_regression.py`` — VAD must process user audio
  during the assistant's greeting (the ``_greeting_in_progress`` lock has
  been removed).
- ``test_assistant_turn_stopped_regression.py`` — the assistant-turn handler
  is only registered for non-restaurant business types; restaurants rely on
  on_ai_transcript instead (see call_pipeline.py:1421-1430 + 1044-1050).
- ``test_restaurant_guard_regression.py`` — code paths gated on
  ``business_type == "restaurant"`` only execute for restaurants.
"""
