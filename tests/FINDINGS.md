# Duuutah AI — Test Findings

This file is the bug log discovered while building and running the automated
test suite. Each entry follows the template below. **The test suite never
fixes production code.** Bugs are recorded here for human triage.

## Template

```
## YYYY-MM-DD — <one-line summary>
- **File:** `backend/<file>.py`
- **Line(s):** N
- **Severity:** critical | high | medium | low
- **Symptom:** what's wrong (what tests observed)
- **Expected:** what should happen
- **Suggested fix:** one paragraph
- **Test:** `backend/tests/<path>::test_name`
```

Severity guide:
- **critical** — data loss, security breach, payment failure, customer harm
- **high** — feature broken for a significant slice of tenants
- **medium** — incorrect output in a specific scenario; workarounds exist
- **low** — cosmetic or low-impact edge case

## Findings

## 2026-05-22 — setup_signal_handlers fails on non-main-thread lifespans
- **File:** `backend/server.py`
- **Line(s):** 117-124 (function `setup_signal_handlers`), called at 3346 from `startup_seed`
- **Severity:** medium
- **Symptom:** `setup_signal_handlers()` calls `loop.add_signal_handler(SIGTERM, ...)`. When the FastAPI lifespan is driven from a worker thread (e.g. Starlette's `TestClient`, or some ASGI test harnesses, or any container runtime that delegates lifespan to a non-main thread), Python's `asyncio.unix_events.add_signal_handler` raises `RuntimeError: set_wakeup_fd only works in main thread of the main interpreter`, which crashes app startup entirely.
- **Expected:** Signal handler registration should either (a) detect non-main-thread context and skip registration with a warning, or (b) catch `RuntimeError`/`ValueError`/`NotImplementedError` from `add_signal_handler` and degrade gracefully.
- **Suggested fix:**
  ```python
  def setup_signal_handlers():
      import threading
      if threading.current_thread() is not threading.main_thread():
          logger.warning("setup_signal_handlers: skipping, not on main thread")
          return
      loop = asyncio.get_event_loop()
      try:
          loop.add_signal_handler(signal.SIGTERM, lambda: ...)
          loop.add_signal_handler(signal.SIGINT, lambda: ...)
      except (NotImplementedError, RuntimeError, ValueError) as exc:
          logger.warning("setup_signal_handlers: skipping (%s)", exc)
  ```
- **Test workaround in place:** `backend/tests/conftest.py` `app` fixture monkeypatches the function to a no-op for the duration of each test. This is acceptable for tests but does not mitigate the production risk if Render or another runtime ever delegates app lifespan to a non-main thread.
- **Test:** `backend/tests/unit/test_infrastructure_smoke.py::test_app_fixture_constructs`
