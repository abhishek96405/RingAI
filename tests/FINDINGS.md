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

## 2026-05-22 — `_block_unknown_outbound_http` autouse fixture incompatible with `respx_mock`
- **File:** `backend/tests/conftest.py`
- **Line(s):** 437-471 (fixture `_block_unknown_outbound_http`) and 274-280 (fixture `respx_mock`)
- **Severity:** medium (test-infra only)
- **Symptom:** The autouse `_block_unknown_outbound_http` fixture monkeypatches `httpx.AsyncClient.send` to raise `RuntimeError` for any non-localhost URL **before** delegating to `real_send_async`. respx (0.21.1) intercepts at a lower layer (`httpx._transports.default.handle_async_request` → connection pool), but our `send` wrapper raises **before** reaching the transport, so respx-mocked routes never get a chance to fire. The comment "respx installs its own transport; if a respx_mock fixture is active, calls go through it instead of here" is incorrect for the current respx version.
- **Expected:** When `respx_mock` is active for a request, that request should resolve through respx's mock router. The autouse guard should only fire for calls that would otherwise reach the real network.
- **Suggested fix:** In `_guarded_async` / `_guarded_sync`, delegate to `real_send_async` first and let respx intercept; only block if respx is not active. One simple heuristic: check `respx.mock._patches` (or the `respx.router._RESOLVER` global) for an active router; if active, pass through. Alternatively, restructure the autouse so it patches **transport** rather than `send`.
- **Test workaround used by C2:** Tests that need to mock outbound HTTP use `monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(...))` (or the same for `post`/`request`) directly. These patches bypass `send` entirely, so the autouse guard never fires. respx is not used for external URLs in C2.
- **Test:** `backend/tests/unit/test_auth_helpers.py`, `backend/tests/unit/test_delivery_utils.py`, and many others.

## 2026-05-22 — Upsell logic lacks a structured decision function
- **File:** `backend/gemini_service.py`
- **Line(s):** `build_system_prompt` around 1185–1900 (uses `upsell_enabled` flag); no `decide_upsell` exists
- **Severity:** medium
- **Symptom:** Upsell behavior is implemented as a prompt-level toggle (`upsell_enabled: bool`), not as a structured decision function. Two consequences:
  1. There is no way for offline code (POS dispatch, analytics, A/B testing) to enumerate what *would* be suggested for a given cart — the suggestion only emerges mid-conversation in the LLM output.
  2. There is no cuisine-matching guard: if the menu includes Tiramisu (Italian dessert) and the cart is Chicken Biryani (Indian), nothing prevents the LLM from suggesting Tiramisu as an upsell, which is jarring.
- **Expected:** A function like `decide_upsell(cart=[...]) -> Optional[Dict]` that returns a structured suggestion with `category`, `cuisine`, `item_id`. Cuisine of suggested item must match cuisine of cart items.
- **Suggested fix:** Add `decide_upsell` in `gemini_service.py`. Index menu items by `cuisine` (a new optional column on MenuItem). At the decision point, filter the menu by the dominant cuisine of the cart and pick the highest-margin item in a complementary category (dessert/drink). The system prompt's upsell instruction should reference this structured suggestion rather than asking the LLM to invent one.
- **Test:** `backend/tests/unit/test_gemini_service_upsell_decision.py::test_decide_upsell_suggests_cuisine_matched_dessert_expected_behavior` (xfail strict)

## 2026-05-22 — `CF_SECRET_TOKEN` env-var leakage from host environment can 403 every test
- **File:** `backend/server.py`
- **Line(s):** 5396-5410 (`cloudflare_security_middleware`)
- **Severity:** low (test-infra hygiene)
- **Symptom:** The middleware reads `CF_SECRET_TOKEN` at module import time. If the developer's shell has `CF_SECRET_TOKEN` set (Cloudflare access secret used in production), the entire test app returns 403 for every route, including `/openapi.json`, because the module-level `CF_SECRET_TOKEN` is captured before pytest-env's `pyproject.toml` env list applies. CI is unaffected because GitHub Actions runners do not have this var.
- **Expected:** Test runs should be hermetic against host environment leakage of production secrets.
- **Suggested fix:** Either (a) add `"CF_SECRET_TOKEN="` to the pytest-env `env` list in `pyproject.toml` (clears the var before the server module imports), or (b) have `cloudflare_security_middleware` skip the check when `ENVIRONMENT == "test"`.
- **Test workaround used by C2:** Run pytest with `CF_SECRET_TOKEN= pytest ...` to clear the var for the test process.
- **Test:** `backend/tests/unit/test_infrastructure_smoke.py::test_app_fixture_constructs`
