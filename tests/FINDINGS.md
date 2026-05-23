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
- **Resolution (C3):** Fixed in `pyproject.toml` pytest-env block by adding `"CF_SECRET_TOKEN="`. The middleware-bypass is verified by `backend/tests/integration/test_middleware_and_lifespan.py::test_cloudflare_middleware_is_noop_when_token_unset`.

## 2026-05-22 — `public_menu_page` raises UnboundLocalError on the not-found branch
- **File:** `backend/server.py`
- **Line(s):** 1264-1360 (function `public_menu_page`); failing reference at line 1276; shadowing import at line 1359
- **Severity:** high
- **Symptom:** When `GET /menu/{restaurant_id}` is called with an unknown restaurant_id, the route raises `UnboundLocalError: cannot access local variable 'HTMLResponse' where it is not associated with a value`. The response is 500 (or whatever the reverse proxy serves on uncaught exceptions) instead of a 404 HTML page. The bug is that line 1359 contains `from fastapi.responses import HTMLResponse`, which makes `HTMLResponse` a local variable for the entire function — even though it's also imported at module scope (server.py:2). Python sees the local assignment and shadows the module-level name, but the assignment only runs after the not-found return at line 1276.
- **Expected:** A 404 HTML response with the body `<h2>Menu not found</h2>`.
- **Suggested fix:** Remove the redundant `from fastapi.responses import HTMLResponse` at line 1359. The module-level import at line 2 is sufficient.
- **Test:** `backend/tests/integration/test_api_root_and_bootstrap.py::test_public_menu_unknown_restaurant_raises_unboundlocalerror` (captures the bug) and `::test_public_menu_returns_404_for_unknown_restaurant_expected` (xfail strict — what should happen)

## 2026-05-22 — `/api/me/repair-membership` grants the calling user ownership of every unowned restaurant
- **File:** `backend/server.py`
- **Line(s):** 1087-1112 (function `repair_membership`)
- **Severity:** critical (security — cross-tenant data exposure)
- **Symptom:** The route iterates every business collection (restaurants, clinics, salons, home_services, legal) for ALL documents, then for each one where the calling user has no membership, creates an owner membership row. There is no Clerk-side check that the calling user previously belonged to the org. In a real deployment with multiple tenants in the same database, ANY authenticated Clerk user can call this endpoint and instantly become owner of every restaurant on the platform.
- **Expected:** The endpoint should only restore memberships the user previously had, verified via Clerk's user-organization membership API. Better: remove the endpoint entirely or gate it behind admin auth.
- **Suggested fix:**
  ```python
  @api_router.post("/me/repair-membership")
  async def repair_membership(user: Dict[str, Any] = Depends(get_current_user)):
      # Fetch the user's actual org memberships from Clerk
      orgs = await get_user_organisations_from_clerk(user["id"])
      restaurants = await db.restaurants.find({"org_id": {"$in": orgs}}, {"_id": 0}).to_list(100)
      ...
  ```
  Or gate the route behind an admin role check.
- **Test:** `backend/tests/integration/test_api_root_and_bootstrap.py::test_repair_membership_creates_missing_memberships` (captures current behavior) and `::test_repair_membership_does_not_steal_other_tenants` (xfail strict)

## 2026-05-22 — `ensure_restaurant_access` returns 403 leaking existence
- **File:** `backend/server.py`
- **Line(s):** 1022-1030 (function `ensure_restaurant_access`)
- **Severity:** medium (existence-leakage / OWASP A01)
- **Symptom:** Cross-tenant requests to any resource-owned route (GET/PUT/DELETE on a restaurant/menu/appointment owned by another tenant) return 403 instead of 404. 403 reveals that the resource exists — a malicious tenant can enumerate other tenants' resources by IDs to learn what's in the system, even though they can't read its contents. The route should return 404 to hide existence completely.
- **Expected:** Both "you have no membership" and "resource doesn't exist" should map to a single 404 response with a generic body. This is the standard OWASP pattern for multi-tenant SaaS.
- **Suggested fix:** Replace the `HTTPException(status_code=403, detail="You do not have access to this restaurant")` at line 1025 with `HTTPException(status_code=404, detail="Restaurant not found")`. Same for the second branch at line 1029. Audit every route's reliance on `ensure_restaurant_access` for status-code changes.
- **Test:** `backend/tests/integration/test_api_restaurants.py::test_get_restaurant_wrong_tenant_returns_403` (captures current) and `::test_get_restaurant_wrong_tenant_should_return_404` (xfail strict)

## 2026-05-22 — `/api/restaurants/{id}/plan-features` references undefined `payload.restaurant_id`
- **File:** `backend/server.py`
- **Line(s):** 4695-4700 (function `get_plan_features_endpoint`)
- **Severity:** high (route entirely broken)
- **Symptom:** The route signature is `async def get_plan_features_endpoint(restaurant_id: str, user: ... = Depends(get_current_user))` — no `payload` parameter exists. The function body then does `restaurant = await ensure_restaurant_access(payload.restaurant_id, user)`, which raises `NameError: name 'payload' is not defined`. Every call to this route returns 500.
- **Expected:** 200 with `{"plan": <name>, "features": <plan features dict>}`.
- **Suggested fix:** Replace `payload.restaurant_id` with `restaurant_id`:
  ```python
  @api_router.get("/restaurants/{restaurant_id}/plan-features")
  async def get_plan_features_endpoint(restaurant_id: str, user: Dict[str, Any] = Depends(get_current_user)):
      restaurant = await ensure_restaurant_access(restaurant_id, user)
      plan = restaurant.get("plan", "STARTER")
      return {"plan": plan, "features": get_plan_features(plan)}
  ```
- **Test:** `backend/tests/integration/test_api_billing_voice_demo.py::test_plan_features_raises_nameerror_due_to_payload_typo` (current) and `::test_plan_features_should_return_plan_block` (xfail strict)

## 2026-05-22 — `httpx` not imported at module scope yet referenced in `except` clauses
- **File:** `backend/server.py`
- **Line(s):** 3478-3483 (telnyx_numbers_search), 3552-3554 (telnyx_provision_number), 3649-3651 (telnyx_assign_existing_number); references `httpx.HTTPStatusError` without a module-level `import httpx`
- **Severity:** high (every Telnyx error path returns the wrong status code)
- **Symptom:** When `telnyx_service.search_available_numbers` (or `create_number_order`, or `update_phone_number`) raises an `httpx.HTTPStatusError`, the `except httpx.HTTPStatusError` clause attempts to resolve `httpx.HTTPStatusError` and fails with `NameError: name 'httpx' is not defined`. Python then aborts the handler and falls through to FastAPI's default 500-handler instead of returning the documented 502 with a meaningful detail. Same pattern for two other Telnyx routes. The bug is masked in success-path tests because the except clause never fires.
- **Expected:** 502 with `{"detail": "Telnyx search failed (...)"}`.
- **Suggested fix:** Add `import httpx` to the top-of-file imports (server.py:1-20). The existing local `import httpx` inside `auto_detect_timezone` (line 397) only scopes it to that function; the global is unaffected.
- **Test:** `backend/tests/integration/test_api_oauth_integrations.py::test_telnyx_search_propagates_telnyx_error_as_500_due_to_missing_httpx_import` (current) and `::test_telnyx_search_should_return_502_on_error` (xfail strict)

## 2026-05-22 — `simulate_call` raises UnboundLocalError on `timedelta` when reservations disabled
- **File:** `backend/server.py`
- **Line(s):** 2974-3156 (function `simulate_call`); shadowing import at line 3037 inside the `if reservations_enabled:` branch; failing reference at line 3133
- **Severity:** high (demo route unusable when reservations not enabled — also any other path that loses the local import)
- **Symptom:** Same shadowing pattern as the `HTMLResponse` bug. Inside the reservations-pre-fetch branch at line 3037, `from datetime import date, timedelta` runs — making `timedelta` a local for the whole function. When `reservations_enabled` is False, the local binding is never made; later use of `timedelta` at line 3133 (`(now - timedelta(seconds=start_offset))`) raises `UnboundLocalError: cannot access local variable 'timedelta' where it is not associated with a value`.
- **Expected:** 200 with the simulated call record body.
- **Suggested fix:** Remove the local `from datetime import date, timedelta` at line 3037. `timedelta` is already imported at module scope (server.py:17). Same for `date`.
- **Test:** `backend/tests/integration/test_coverage_demo_and_scenarios.py::test_simulate_call_raises_unbound_timedelta_when_reservations_disabled` (current) and `::test_simulate_call_succeeds_with_reservations_disabled` (xfail strict)

## 2026-05-22 — `/api/test-mode/run-scenario` references undefined `call_sid` in clinic/salon branch
- **File:** `backend/server.py`
- **Line(s):** 5215-5390 (function `run_test_scenario`); failing references at 5258 and 5269 inside the `if business_type in ("clinic", "salon", "home_services", "legal"):` branch
- **Severity:** medium (test-mode entirely unusable for appointment-business tenants)
- **Symptom:** When the route is exercised for a tenant whose business_type is in `{clinic, salon, home_services, legal}`, line 5258 (`logger.info(f"[{call_sid}] Starting availability pre-fetch for {business_type}")`) raises `NameError: name 'call_sid' is not defined`. `call_sid` is a local variable used by the WebSocket handlers but never defined inside `run_test_scenario`. For restaurant business types the branch is skipped and the bug is not reached.
- **Expected:** Availability pre-fetch should run cleanly without referencing a non-existent variable.
- **Suggested fix:** Either remove the offending log line, or generate a placeholder `call_sid` at the top of the function:
  ```python
  call_sid = f"test_{uuid.uuid4().hex[:8]}"
  ```
  (The function already uses this exact pattern at line 5358 for the auto-learning service call.)
- **Test:** `backend/tests/integration/test_coverage_demo_and_scenarios.py::test_run_scenario_raises_due_to_undefined_call_sid`

## 2026-05-22 — `POST /api/restaurants/{id}/reservations` returns the inserted doc with raw ObjectId, crashing JSON encoder
- **File:** `backend/server.py`
- **Line(s):** 1882-1933 (function `create_reservation`)
- **Severity:** high (route unusable — 500 on every successful create)
- **Symptom:** The route builds a reservation doc via `create_reservation_doc(...)`, then `await db.reservations.insert_one(doc)`. Motor's `insert_one` mutates the input dict in place, adding `_id: ObjectId(...)`. The route then returns `{"reservation": doc, ...}` — FastAPI's `jsonable_encoder` fails with `TypeError: 'ObjectId' object is not iterable` when trying to serialise the ObjectId. The client sees 500 even though the document was successfully written.
- **Expected:** 200 with `{"reservation": <serialised-reservation-doc>, "message": "..."}`.
- **Suggested fix:** Strip `_id` before returning, or re-read the doc with `{"_id": 0}` projection:
  ```python
  await db.reservations.insert_one(doc)
  doc.pop("_id", None)  # or: doc = await db.reservations.find_one({"id": doc["id"]}, {"_id": 0})
  return {"reservation": doc, "message": "Reservation created successfully"}
  ```
- **Test:** `backend/tests/integration/test_api_appointments.py::test_create_reservation_returns_500_due_to_objectid_leak` (current) and `::test_create_reservation_should_return_200_with_doc` (xfail strict)

## 2026-05-22 — `RestaurantUpdate` zero-int special-case loop names fields that don't exist on the model
- **File:** `backend/server.py`
- **Line(s):** 1152-1189 (function `update_restaurant`); dead loop at 1157-1160
- **Severity:** low (defensive code that does nothing — no functional impact, but confusing)
- **Symptom:** The route's update loop at line 1157-1160 explicitly preserves `slot_capacity`, `slot_interval_minutes`, and `delivery_minimum` from being filtered out as falsy zeros. But NONE of those fields exist on the `RestaurantUpdate` Pydantic model (lines 502-560) — they live on `RestaurantConfigUpdate` (lines 699-735) which is used by a different route. So the `getattr(data, field, None)` always returns None and the loop is dead code.
- **Expected:** Either (a) move the special-case loop to `update_restaurant_config` where the fields actually live, or (b) add the fields to `RestaurantUpdate` if they're supposed to be settable via this route, or (c) delete the dead loop.
- **Suggested fix:** Delete lines 1157-1160 from `update_restaurant`; add equivalent logic to `update_restaurant_config` if zero-value preservation is actually needed for config fields.
- **Test:** `backend/tests/integration/test_coverage_misc.py::test_update_restaurant_zero_int_field_persists` (uses `delivery_fee` which IS on RestaurantUpdate)

## 2026-05-22 — `run_test_scenario` accesses `config.get(...)` without a None guard
- **File:** `backend/server.py`
- **Line(s):** 5291 (and adjacent lines in the prompt-kwargs block)
- **Severity:** medium (route 500s when a restaurant has no `restaurant_configs` row)
- **Symptom:** The `restaurant_configs.find_one(...)` call returns None for tenants that haven't completed onboarding. The subsequent prompt-kwargs construction inlines `config.get(...)` calls — most are guarded with `if config else <default>`, but `delivery_minimum=config.get("delivery_minimum", 1500)` at line 5291 has no guard and raises `AttributeError: 'NoneType' object has no attribute 'get'`.
- **Expected:** Sensible default when no config exists.
- **Suggested fix:** Wrap the call: `delivery_minimum=(config.get("delivery_minimum", 1500) if config else 1500)`. Audit the whole `system_prompt = get_system_prompt(...)` call site for other unguarded `config.get(...)` references.
- **Test:** captured indirectly — `backend/tests/integration/test_coverage_demo_and_scenarios.py::test_run_scenario_success_for_restaurant_with_seeded_config` succeeds only after a config is seeded.
