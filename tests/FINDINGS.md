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
**Status:** RESOLVED in commit `c160d54` (hotfix PR #4). The unsafe iterate-and-grant route was retired — `/api/me/repair-membership` no longer creates memberships across foreign tenants.
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
**Status:** RESOLVED in the auth/access-control batch (fix branch `fix/auth-access-control-batch`). Both the no-membership branch and the not-found branch now return `HTTPException(404, "Restaurant not found")` — callers cannot distinguish "doesn't exist" from "exists but not yours".
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

## 2026-05-23 — `POST /api/webhooks/square` is an unsigned, unhandled stub
**Status:** RESOLVED in commit `12a15e8` (PR #5 hotfix), 2026-05-23. Endpoint now requires HMAC-SHA256 signature verification against `SQUARE_WEBHOOK_SIGNATURE_KEY` (returns 503 if unconfigured, 401 if signature missing or invalid), dispatches `oauth.authorization.revoked` events to mark integrations disconnected, and idempotency-checks via the `webhook_events` collection so retries are deduplicated.
- **File:** `backend/server.py`
- **Line(s):** 5097-5101 (function `square_webhook`)
- **Severity:** critical (security — accepts spoofed events; missing event handling)
- **Symptom:** The route returns `{"received": True}` for ANY request body, with no signature verification, no `x-square-hmacsha256-signature` header check, no event-type dispatch, and no idempotency. Three distinct security bugs in one tiny function:
  1. **Spoofed events accepted:** A malicious caller can POST arbitrary JSON; the server logs receipt and returns 200. If any downstream code consumes square webhook events from logs/queues, those events cannot be trusted.
  2. **OAuth revocation ignored:** When a merchant disconnects in Square's UI, Square fires `oauth.authorization.revoked`. The stub ignores it, so the `integrations` collection retains `connected: True` plus tokens that no longer work — calls into Square will fail with stale tokens and the user has no UI indication.
  3. **Inventory updates ignored:** `inventory.count.updated` events are dropped, so Square-managed POS inventory drifts from the Duuutah AI menu cache.
- **Expected:** Verify HMAC-SHA256 of `notification_url + payload` against `SQUARE_WEBHOOK_SIGNATURE_KEY`. Reject with 400/403 on mismatch, missing header, or malformed header. Dispatch at minimum `oauth.authorization.revoked` and `inventory.count.updated`. Deduplicate by `event_id`.
- **Suggested fix:** Replace the stub with full HMAC-SHA256 verification using `hmac.compare_digest`, then dispatch on event type (revocation -> mark integration disconnected; inventory -> bump menu cache). Persist `event_id` in a `webhook_events` collection to dedup replays.
- **Test:** `backend/tests/webhooks/test_square_webhooks.py::test_square_webhook_*_expected` (xfail strict) and `backend/tests/webhooks/test_square_signature_verification.py::*` (xfail strict)

## 2026-05-23 — OAuth state token is the literal `restaurant_id` (Square + Stripe Connect)
**Status:** RESOLVED in commit `fffc63f` (PR #5 hotfix), 2026-05-23. State tokens are now cryptographically random (`secrets.token_urlsafe(32)`), single-use (atomic `find_one_and_update` with `consumed=False` guard), and bound to issuer (restaurant_id + user_id + provider) with a 10-minute TTL via Mongo index. New module: `backend/oauth_state_service.py`. Google Calendar OAuth was untouched (already uses signed-JWT state).
- **File:** `backend/server.py`
- **Line(s):** 4850-4882 (`square_connect`, `square_callback`); 4889-4965 (`stripe_connect_callback`)
- **Severity:** critical (security — RFC 6749 §10.12 violation; CSRF / replay risk)
- **Symptom:** Both Square and Stripe Connect OAuth flows use the calling business's `restaurant_id` as the OAuth `state` parameter (e.g. `state=tenant_a_restaurant`). State is never stored server-side and never validated against a session-bound nonce. Consequences:
  - **Predictable:** Any attacker who learns a restaurant_id (UUIDs leak via URLs, error messages, support tickets) can forge a valid state.
  - **Replayable:** A captured OAuth state has no TTL and no single-use enforcement; the same `code + state` combo completes the OAuth flow repeatedly.
  - **CSRF gap:** RFC 6749 mandates state must be unguessable AND bound to the user-agent session. Without that binding, an attacker can begin an OAuth flow on their own account and trick a victim into completing it under the victim's session, attaching the attacker's Stripe Connect account to the victim's restaurant_id and redirecting future Stripe payouts.
- **Expected:** Per RFC 6749 §10.12 and OWASP OAuth guidance: generate a per-request 32-byte cryptographically-random nonce via `secrets.token_urlsafe(32)`, store it in a TTL'd `oauth_state_tokens` collection with `restaurant_id`, `user_id`, `provider`, `created_at`, `expires_at`, `consumed_at` fields. On callback: look up the state, reject if missing/expired/consumed, mark consumed, and use the stored `restaurant_id`.
- **Suggested fix:** Add `_mint_oauth_state(restaurant_id, user_id, provider) -> str` and `_consume_oauth_state(token, provider) -> Optional[str]` helpers. Replace `state={restaurant_id}` with `state=<minted_token>` in both connect URLs; in both callbacks call `_consume_oauth_state` and reject if it returns None.
- **Test:** `backend/tests/security/test_oauth_state_token_security.py::test_*_should_*_expected` (xfail strict) and `::test_*_captures_bug` (current)

## 2026-05-23 — `/api/admin/process-reminders` has no admin-role check
**Status:** RESOLVED in the auth/access-control batch (fix branch `fix/auth-access-control-batch`). The route now performs the same `ADMIN_USER_ID` comparison as `/api/admin/cost-analytics`: callers whose `user.id` does not match the env var are rejected with 403 "Admin access required".
- **File:** `backend/server.py`
- **Line(s):** 1796-1810 (function `process_reminders_admin`)
- **Severity:** high (any tenant owner can trigger a global cron job)
- **Symptom:** The route lives under `/api/admin/` and is intended as a cron-style trigger for the reminder-sending job, but the only dependency is `Depends(get_current_user)` — any authenticated user can call it. By contrast, `/api/admin/cost-analytics` properly checks `user.id == ADMIN_USER_ID` (server.py:4215-4217). The reminders endpoint is missing the same gate.
- **Expected:** Same admin-id check as `/api/admin/cost-analytics`: return 403 if `user.get("id") != os.environ.get("ADMIN_USER_ID")`. Better: factor into a `require_admin` dependency reused on every admin route.
- **Suggested fix:** Add a `require_admin` dependency comparing `user["id"]` to `ADMIN_USER_ID`; switch every `/api/admin/*` route to use it.
- **Test:** `backend/tests/security/test_admin_role_enforcement.py::test_admin_process_reminders_accepts_any_authenticated_user_captures_bug` (current) and `::test_admin_process_reminders_rejects_non_admin_expected` (xfail strict)

## 2026-05-23 — Public menu HTML page renders menu item names without HTML escaping (stored XSS)
**Status:** RESOLVED in the auth/access-control batch (fix branch `fix/auth-access-control-batch`). Every user-controlled field rendered into the public menu HTML (item name, item description, category name, restaurant name, cuisine type, page title) now passes through `html.escape()`. The local `html = ...` variable that shadowed the stdlib module was renamed to `page_html`.
- **File:** `backend/server.py`
- **Line(s):** 1264-1360 (function `public_menu_page`); f-string template interpolation of `item["name"]`, `item["description"]`, category names
- **Severity:** high (stored XSS — exploitable against anyone visiting the public menu page)
- **Symptom:** The public menu HTML page at `GET /menu/{restaurant_id}` builds its HTML by interpolating menu item fields directly with no HTML escaping. A menu item created with `name="<script>alert('xss')</script>"` renders as a working `<script>` tag in the page; any visitor to that public menu URL executes attacker-controlled JavaScript in the Duuutah AI origin. A malicious tenant could plant payloads in their OWN menu and use the public URL as a phishing landing page — or compromise a victim browser that has cookies for *.duuutah.ai.
- **Expected:** Every interpolated user-controllable field passes through `html.escape()` before being rendered. Long-term: migrate to Jinja2 templates with autoescape=True.
- **Suggested fix:** Wrap every `item["name"]`, `item["description"]`, and category name in `html.escape(...)` before f-string interpolation. Audit the whole function for other interpolation sites.
- **Test:** `backend/tests/security/test_input_validation_html_injection.py::test_public_menu_html_renders_unescaped_item_names_captures_bug` (current) and `::test_public_menu_html_escapes_item_names_expected` (xfail strict)

## 2026-05-23 — Stripe webhook crashes (KeyError → 500) on events missing `data.object`
- **File:** `backend/server.py`
- **Line(s):** 4703-4704 (function `stripe_webhook`)
- **Severity:** low (resilience — webhook returns 500 instead of 400)
- **Symptom:** After signature verification, the route does `event["data"]["object"]` unconditionally. A real Stripe `ping` event or any malformed payload that omits `data` raises `KeyError`, which becomes a 500. Stripe interprets non-2xx responses as delivery failures and retries with exponential backoff; an avalanche of malformed-event retries could pile up in the delivery queue and delay legitimate events.
- **Expected:** Return 200 (with a `warning` field) or 400 with a clear "malformed event" body when `event["data"]["object"]` is missing. The route should be defensive about input shape.
- **Suggested fix:** Replace `data = event["data"]["object"]` with `data = event.get("data", {}).get("object")` and short-circuit when data is None.
- **Test:** `backend/tests/webhooks/test_webhook_payload_edge_cases.py::test_stripe_event_with_missing_data_object_raises_keyerror_captures_bug` (current) and `::test_stripe_event_with_missing_data_object_should_400_expected` (xfail strict)

## 2026-05-23 — Stripe webhook lacks event-id deduplication; replayed checkout events fire side effects every time
- **File:** `backend/server.py`
- **Line(s):** 4689-4847 (function `stripe_webhook`)
- **Severity:** medium (idempotency — duplicate WebSocket notifications + duplicate SMS on event replay)
- **Symptom:** Stripe's at-least-once delivery semantics means the same event (same `evt_*` id) can arrive multiple times during a transient network blip or worker restart. The webhook never records seen `event_id`s. The DB-level `$set` updates are naturally idempotent (no counter increments), BUT the secondary side effects — WebSocket notification on `checkout.session.completed` order_payment (server.py:4727-4733) and the payment-confirmation SMS (server.py:4736-4759) — re-fire on every replay. Net: a customer can receive 2-5 "payment received" SMS messages for one actual payment, and the restaurant dashboard pings repeatedly for the same order.
- **Expected:** Persist `event_id` in a dedup table on first receipt; on replay, return 200 immediately without re-running side effects.
- **Suggested fix:** On every Stripe webhook, check `db.webhook_events.find_one({"event_id": ..., "provider": "stripe"})` before dispatch; insert the event_id on first sight. Add a TTL index on `received_at` (90-day expiry).
- **Test:** `backend/tests/webhooks/test_webhook_idempotency.py::test_stripe_checkout_replay_does_not_send_second_sms_expected` (xfail strict) and `::test_stripe_invoice_paid_idempotent_on_replay` (passing — DB-level $set is naturally idempotent)

## 2026-05-23 — Square webhook 500s on signed non-dict JSON bodies (post-hotfix gap)
- **File:** `backend/server.py`
- **Line(s):** 5171-5174 (`square_webhook`, after `json.loads`)
- **Severity:** medium (resilience — Square will retry on 500, amplifying load)
- **Symptom:** After the hotfix landed signature verification (commit `12a15e8`), the handler proceeds to `event_id = event.get("event_id") or event.get("id")`. If a correctly-signed body decodes to a non-dict JSON value (`null`, `[]`, a bare string or number), the `.get` call raises `AttributeError: 'NoneType' object has no attribute 'get'` (or similar for list), and FastAPI returns 500. Square treats 5xx as a delivery failure and retries with exponential backoff.
- **Expected:** Return 400 with a clear "malformed event" body when the decoded payload is not a JSON object.
- **Suggested fix:** Between the `json.loads` and the `event.get(...)` line, insert `if not isinstance(event, dict): raise HTTPException(status_code=400, detail="Square payload must be a JSON object")`.
- **Test:** `backend/tests/webhooks/test_webhook_payload_edge_cases.py::test_square_webhook_handles_signed_non_dict_bodies_expected` (xfail strict)

## 2026-05-23 — Stripe webhook accepts future-timestamp signed payloads (replay window bypass)
- **File:** `backend/server.py`
- **Line(s):** 4689-4701 (function `stripe_webhook`); relies on `stripe.Webhook.construct_event`
- **Severity:** low (defence-in-depth — exploit path requires clock skew or NTP attack)
- **Symptom:** The Stripe SDK's `WebhookSignature.verify_header` checks only `now - ts <= tolerance`, never the symmetric `ts - now <= tolerance`. A signed payload with a far-future timestamp passes the replay-window check and is accepted. Narrow exploit path (requires the attacker to control or skew server clocks via NTP), but for defence-in-depth the route should reject any timestamp more than ±300s from now.
- **Expected:** Explicit two-sided window check before invoking `construct_event`.
- **Suggested fix:** Parse `t=<unix>` from the `stripe-signature` header upfront; reject if `abs(time.time() - ts) > 300`.
- **Test:** `backend/tests/webhooks/test_stripe_signature_verification.py::test_future_timestamp_is_currently_accepted_captures_bug` (current) and `::test_future_timestamp_should_return_400_expected` (xfail strict)

## 2026-05-23 — `_transfer_call` references undefined `settings` module → every escalation transfer silently fails
- **File:** `backend/call_pipeline.py`
- **Line(s):** 519 (inside `CallSession._transfer_call`)
- **Severity:** high (escalations to human are silently dropped instead of transferred)
- **Symptom:** `_transfer_call` builds the Telnyx Call Control API request with `"Authorization": f"Bearer {settings.TELNYX_API_KEY}"`. `settings` is never imported anywhere in `call_pipeline.py` (grep `^(from|import) .*settings` returns no matches; grep `\bsettings\.` returns only line 519). At runtime, `NameError: name 'settings' is not defined` is raised inside the `try` block, caught by the broad `except Exception as e` at line 526, logged as `Transfer to {to_number} failed: name 'settings' is not defined`, and the function returns False. The caller in `_schedule_hangup` (line 495) then treats the transfer as failed and falls through to plain pipeline cancellation — the caller is hung up on instead of being connected to a human. Every escalation flow in production currently behaves this way.
- **Expected:** Successful Telnyx transfer with the call moved to the escalation phone number.
- **Suggested fix:** Replace `settings.TELNYX_API_KEY` with `os.environ.get("TELNYX_API_KEY", "")` (consistent with the rest of `call_pipeline.py`, which reads env vars directly). Alternatively, add `from server import settings` if a settings module actually exists — but the codebase pattern is direct env access, so the simpler fix is preferred. Also worth wrapping the `except Exception` to re-raise NameError / AttributeError during local dev so this class of bug surfaces immediately.
- **Test:** `backend/tests/voice/test_call_pipeline_hangup_paths.py::test_transfer_call_currently_nameerrors_on_undefined_settings_captures_bug` (current, passing) and `::test_transfer_call_handles_telnyx_success_expected` (xfail strict)

## 2026-05-23 — `classify_booking_intent` matches `"tomorrow"` before `"day after tomorrow"`, shadowing the latter
- **File:** `backend/call_pipeline.py`
- **Line(s):** 925-938 (relative-word branch inside `classify_booking_intent`)
- **Severity:** medium (appointment customers asking for "day after tomorrow" get tomorrow's slots instead)
- **Symptom:** The relative-word branch checks `"today" in customer_text`, `"tomorrow" in customer_text`, then `"day after tomorrow" in customer_text` in that order using substring matching. Because `"tomorrow" in "day after tomorrow"` is True, the tomorrow branch wins before the day-after-tomorrow branch is ever evaluated. Net effect: a salon customer saying "day after tomorrow" gets quoted tomorrow's availability instead. The classifier returns `trigger="relative_tomorrow"` and the wrong date.
- **Expected:** "day after tomorrow" should resolve to `today + 2 days` with `trigger="relative_day_after"`.
- **Suggested fix:** Re-order the elif chain so `"day after tomorrow"` is checked BEFORE `"tomorrow"`, or use a regex like `\bday after tomorrow\b` checked first. Simplest patch:
  ```python
  if "day after tomorrow" in customer_text:
      date_str = (today + _td(days=2)).strftime("%Y-%m-%d")
      date_confidence = 0.85
      date_trigger = "relative_day_after"
  elif "today" in customer_text:
      ...
  elif "tomorrow" in customer_text:
      ...
  ```
- **Test:** `backend/tests/voice/test_classify_booking_intent.py::test_day_after_tomorrow_phrase_currently_matches_tomorrow_first_captures_bug` (current, passing) and `::test_day_after_tomorrow_should_resolve_two_days_out_expected` (xfail strict)

## 2026-05-23 — `dispatch_order_if_ready` does not reset `_order_dispatched` after extraction failure → blocks future retries
- **File:** `backend/call_pipeline.py`
- **Line(s):** 533-573 (function `dispatch_order_if_ready`; failing branch at the `for/else` clause around line 569-573)
- **Severity:** medium (legitimate orders that just-failed-to-extract-on-first-attempt cannot be retried within the same call)
- **Symptom:** The function sets `self._order_dispatched = True` at line 537 (entry guard intent), then if the in-memory order has no items it runs an extraction retry loop. When all `max_retries` attempts fail (the `else` branch of `for…else` at line 569-573), it returns False *without* resetting `_order_dispatched` to False. A subsequent call to `dispatch_order_if_ready` from the disconnect handler or a later signal will hit the entry guard at line 534 (`if self._order_dispatched: ... return False`) and skip extraction entirely. The call ends with no order dispatched even though the transcript may now contain enough context to extract successfully.
- **Expected:** When extraction fails after max_retries, `_order_dispatched` should be reset to False so future dispatch attempts within the same call can succeed.
- **Suggested fix:** Add `self._order_dispatched = False` immediately before the `return False` in the for/else branch (around line 572). Same fix should be applied to the order_type-mismatch branch (line 540) which already does this correctly — confirming this is a copy-paste-missed-the-reset, not a deliberate design.
- **Test:** `backend/tests/voice/test_call_pipeline_error_paths.py::test_dispatch_with_no_items_and_extraction_returns_none_captures_bug` (current, passing) and `::test_dispatch_failure_should_allow_future_retry_expected` (xfail strict)

## 2026-05-24 — `useWebSocketNotifications` logs caller's restaurant_id and full URL to `console.log` on every connect/reconnect (info-leak / log noise)
- **File:** `frontend/src/hooks/useWebSocketNotifications.ts`
- **Line(s):** 66 (connect), 73 (open), 128 (disconnect), 134 (reconnect scheduling)
- **Severity:** low (info-leak via browser devtools / external log shippers; constant noise in production console)
- **Symptom:** Each connect/open/close/reconnect emits `console.log("[WS] ...", url, restaurant_id, code, reason)`. The URL contains the active tenant's `restaurant_id` query param, and the codepath fires on every reconnect attempt (every 5s by default after a drop). On a noisy mobile network this produces thousands of console lines per session, all containing tenant identifiers.
- **Expected:** Either remove the logs entirely or gate behind `import.meta.env.DEV`. Tenant identifiers should not be unconditionally written to `console.log` in production.
- **Suggested fix:**
  ```ts
  const log = (...args: unknown[]) => { if (import.meta.env.DEV) console.log("[WS]", ...args); };
  // replace each console.log with log(...)
  ```
- **Test:** `frontend/src/test/hooks/useWebSocketNotifications.test.tsx` (covered indirectly by the test that verifies URL composition).

## 2026-05-24 — `DashboardLayout` logs admin-detection state to `console.log` on every render (info-leak)
- **File:** `frontend/src/components/layout/DashboardLayout.tsx`
- **Line(s):** 83
- **Severity:** low (info-leak; also produces console noise on every dashboard render)
- **Symptom:** `console.log("Admin debug:", { ADMIN_CLERK_ID, userId: user?.id, match: user?.id === ADMIN_CLERK_ID });` runs on every render of the layout. This exposes the configured `VITE_ADMIN_CLERK_ID` (an admin Clerk user ID) and the current user's Clerk user ID to the browser console — easily scraped by any browser extension or external log shipper.
- **Expected:** Debug log should be removed (or gated behind `import.meta.env.DEV`). Admin status should not be unconditionally written to `console.log` in production.
- **Suggested fix:** Delete line 83 outright. The flag `isAdmin` is already in component state for use; there is no need to log the comparison.
- **Test:** `frontend/src/test/components/layout/DashboardLayout.test.tsx` (rendering the dashboard triggers the log).

## 2026-05-24 — `AppSessionContext.refreshSession` has no in-flight guard; concurrent calls double-fire and may clobber the active restaurant id
- **File:** `frontend/src/context/AppSessionContext.tsx`
- **Line(s):** 124-160 (`refreshSession`)
- **Severity:** medium (race condition; surfaced via flaky test setup before the mock-clerk memoization fix)
- **Symptom:** `refreshSession` has no in-flight guard. If `setActiveRestaurant` (which updates state and triggers a re-render) and the auth/effect-driven bootstrap fire near-simultaneously, two `bootstrapSession()` calls go in parallel. The one that resolves last wins, even if it has stale params, which can flip `localStorage.ringai.activeRestaurantId` back to a previously-active tenant or null. Reproducible in tests when `useAuth().getToken` changes identity per render (we saw 400+ bootstrap calls in a single render cycle before we memoized the mock).
- **Expected:** Either (a) maintain a `refreshing` ref and ignore re-entrant calls, or (b) cancel an in-flight bootstrap when a new one starts (e.g. AbortController).
- **Suggested fix:**
  ```ts
  const inFlight = useRef<Promise<BootstrapPayload | null> | null>(null);
  const refreshSession = useCallback(async (prefId = null) => {
    if (inFlight.current) return inFlight.current;
    const p = (async () => { /* existing body */ })();
    inFlight.current = p;
    try { return await p; } finally { inFlight.current = null; }
  }, [/*...*/]);
  ```
- **Test:** `frontend/src/test/context/AppSessionContext.test.tsx::refreshSession re-fetches /api/me/bootstrap` (currently passing; was the reproducer for the original 400-fire bug — fixed in the mock but the prod race is still possible).

## 2026-05-24 — `OrdersPage` fetches three pages with magic-number guards; never paginates past 300 rows
- **File:** `frontend/src/pages/dashboard/OrdersPage.tsx`
- **Line(s):** 41-54 (`fetchOrders`)
- **Severity:** medium (data integrity; orders past page 3 are silently dropped from the view)
- **Symptom:** `fetchOrders` runs at most 3 sequential `getCalls` requests (page=1 COMPLETED + page=1 ESCALATED, then page=2 and page=3 COMPLETED, each conditional on the previous response's `pages` field). A restaurant with >300 completed orders that have `order_json.items` will see only the most recent ~300 in the Orders page; older orders are invisible until the operator changes the filter. No UX hint that data is truncated.
- **Expected:** Paginate properly: either server-side (request page N until `pages` is reached, with a hard upper cap and a "Showing N of M" footer) or client-side with a "Load more" button.
- **Suggested fix:** Convert to a real paginated list with a `[page, setPage]` state and a "Next / Previous" footer, matching `CallsPage`'s pattern. Limit `getCalls` to `limit=20` per page.
- **Test:** `frontend/src/test/pages/dashboard/OrdersPage.test.tsx::renders rows when calls with order data are returned` (currently asserts a single row; the 300-row truncation is not directly tested because the test fixtures are small).

## 2026-05-24 — `DashboardHome` polls analytics every 30s without backing off on failure; toast.error fires on every retry
- **File:** `frontend/src/pages/dashboard/DashboardHome.tsx`
- **Line(s):** 111-122 (the `useEffect` setting up the interval and visibility listener)
- **Severity:** low (resource waste; UX noise — error toast fires on every retry)
- **Symptom:** The dashboard polls `/analytics/summary` every 30s plus every `visibilitychange -> visible`. On a 5xx (auth blip, restart, etc.) the toast `Failed to load dashboard data` fires every 30s without backoff. A tab left open during a server restart will spam the user with error toasts.
- **Expected:** Either (a) exponential backoff after the first failure, or (b) collapse repeated identical error toasts (sonner has `id`/`description` dedup options), or (c) suppress toast on failed polls and only surface errors on user-initiated refresh.
- **Suggested fix:** Convert to a `useQuery({ queryKey, queryFn, refetchInterval: 30_000, retry: 2 })` via the existing `@tanstack/react-query` QueryClient, and suppress toasts on background refetch failures (only fire on the first manual fetch).
- **Test:** `frontend/src/test/pages/dashboard/DashboardHome.test.tsx::recovers (renders the layout) when the analytics request fails` (verifies the failure path renders cleanly; backoff is not currently tested).

## 2026-05-24 — `sanitizeRestaurantId` accepts the literal strings `"null"` / `"undefined"` from corrupted localStorage; defensive code masks an upstream bug
- **File:** `frontend/src/lib/api.ts`
- **Line(s):** 34-49 (`sanitizeRestaurantId`, `getRestaurantId`, `setRestaurantId`)
- **Severity:** low (defensive code that suggests an underlying past bug; the sanitization for sentinel strings would be unnecessary if the corruption couldn't happen in the first place)
- **Symptom:** Both `getRestaurantId` and `setRestaurantId` route their inputs through `sanitizeRestaurantId`, which explicitly checks for the strings `"null"` and `"undefined"`. This implies that somewhere upstream a `String(restaurantId)` or template literal was producing those strings instead of clearing the key. The defensive coding masks the original source.
- **Expected:** The producer (callsite that wrote `"null"` to localStorage) should be identified and fixed. Once fixed, the sanitization can be simplified to just `trim()`-and-check-empty.
- **Suggested fix:** Add a `console.warn(...)` inside `sanitizeRestaurantId` when it sees `"null"`/`"undefined"`, gated on `import.meta.env.DEV`, to surface the producing callsite during dev. Once no warnings fire in dev for a week, the sentinel checks can be removed.
- **Test:** `frontend/src/test/lib/api.test.ts::setRestaurantId removes the key when given the string 'null'` and `...'undefined'` (currently captures the defensive behavior; the suggested warning is not yet present).

## 2026-05-24 — Test infra: jsdom v20 missing `hasPointerCapture` / `setPointerCapture` shims required by Radix UI Select
- **File:** `frontend/src/test/setup.ts` (now fixed)
- **Severity:** test-infra only (not a production bug; recorded for future test-author awareness)
- **Symptom:** When a test calls `userEvent.click()` on a `<SelectTrigger>` rendered by `@radix-ui/react-select` under jsdom v20, Radix dispatches pointer events that call `target.hasPointerCapture(pointerId)`. jsdom v20 doesn't implement Pointer Events at all, so the call throws `TypeError: target.hasPointerCapture is not a function`.
- **Expected:** Tests should be able to drive Radix Select dropdowns. The shim should live in shared setup so individual tests don't reinvent it.
- **Suggested fix (already applied in C6):** Add the three Pointer-Events methods (`hasPointerCapture` -> `() => false`, `setPointerCapture`/`releasePointerCapture` -> no-op `vi.fn()`) to `HTMLElement.prototype` if not present, in `src/test/setup.ts`.
- **Test:** `frontend/src/test/pages/dashboard/CallsPage.test.tsx::filters by status through the dropdown` (would crash without the shim).

## 2026-05-24 — Mock `@clerk/clerk-react` must memoize hook results to avoid infinite re-renders in `AppSessionContext`
- **File:** `frontend/src/test/utils/mock-clerk.tsx` (now fixed); related production-side risk in `frontend/src/context/AppSessionContext.tsx:116`
- **Severity:** test-infra (immediate) / low-prod (latent brittleness)
- **Symptom:** A naive mock of `useAuth()` that returns `{ getToken: vi.fn(...) }` produces a fresh `getToken` reference on every render. `AppSessionContext.tsx` lists `getToken` as a `useEffect` dep (line 116, depending on `[authLoaded, isSignedIn, getToken]`), so the effect re-runs every render, which calls `setTokenResolved(false)` -> re-render -> repeat. We observed 400+ bootstrap calls in a single test render before adding `React.useMemo` to the mock. The same pattern would bite a real Clerk integration if Clerk ever changed its hook to return a non-stable `getToken`.
- **Expected:** Either (a) `AppSessionContext` should not list `getToken` as an effect dep (replace with a ref), or (b) the mock should always return stable references. We chose (b) for the test mock; (a) is the more robust prod fix.
- **Suggested fix in prod:**
  ```ts
  const getTokenRef = useRef(getToken);
  useEffect(() => { getTokenRef.current = getToken; }, [getToken]);
  // then call getTokenRef.current() inside the effect, and drop getToken from the dep array
  ```
- **Test:** `frontend/src/test/context/AppSessionContext.test.tsx::refreshSession re-fetches /api/me/bootstrap` (was the reproducer; mock memoization fixed the test, but the underlying brittleness in prod code remains worth flagging — see also the related race-condition finding above).

## 2026-07-24 — TelnyxFrameSerializer's streaming resampler never flushes at stream end, dropping ~100ms of trailing audio on any rate-mismatched leg
- **File:** `pipecat/audio/resamplers/soxr_stream_resampler.py` (`SOXRStreamAudioResampler`, third-party, installed under `.venv`) — owned/constructed from `pipecat/serializers/telnyx.py` (`TelnyxFrameSerializer.__init__`, also third-party); consumed by `backend/call_pipeline.py`'s `L16TelnyxFrameSerializer.serialize()`/`deserialize()` (~lines 114-160) and by the parent class's own PCMU/PCMA `serialize()`/`deserialize()`, both of which call `self._output_resampler.resample(...)` / `self._input_resampler.resample(...)` without ever calling a matching flush/close.
- **Severity:** low
- **Symptom:** `SOXRStreamAudioResampler.resample()` wraps `soxr.ResampleStream.resample_chunk()`, which buffers audio internally and emits output in blocks (~100ms in my test) rather than 1:1 per input chunk. Nothing in pipecat or in `L16TelnyxFrameSerializer` ever calls a "final chunk" / flush variant to drain whatever's still buffered inside `soxr.ResampleStream`'s internal state when the stream ends (EndFrame, CancelFrame, or the websocket just closing). That trailing buffered audio — up to ~100ms — is silently lost.
- **Verified via:** a manual script (not yet an automated test) that fed a synthetic 1kHz tone burst through the exact `SOXRStreamAudioResampler` pipecat uses, 20 chunks of 320 samples (20ms) at 16000→8000 Hz, with the burst placed at chunk index 5:
  - The burst's energy appeared delayed by 5 chunks (~100ms) at chunk index 10 at full RMS (10395 vs ~0 baseline) — confirming this is buffering/delay, **not** a silent mid-stream drop.
  - Total output samples came in at 3032 vs a mathematically expected ~3200 for 20×320 samples at a 16000→8000 ratio — a ~5% shortfall consistent with the final buffered block never being flushed.
- **Scope / exposure:** This resampler has always been used for the customer's inbound speech leg (Telnyx wire rate → pipeline rate), on every call, regardless of codec — this is pre-existing behavior, not introduced by the L16 upgrade. After the L16 upgrade (`AUDIO_CODEC` unset, the new default), wire rate and pipeline rate are both 16000 on both legs, so the resampler's own `if in_rate == out_rate: return audio` shortcut fires and `resample_chunk()` is never invoked at all — exposure drops to zero on the default path. It only resurfaces if `AUDIO_CODEC=PCMU` is used to roll back (reproducing the original 8000/16000 mismatch on the inbound leg), or for the ~3.7s pre-roll clip specifically under a PCMU rollback (its frame is always tagged 16000; see `call_pipeline.py` around line 2768).
- **Expected:** No audio lost when a resampling stream ends — the last buffered block should be flushed out before serializer/transport teardown completes.
- **Suggested fix:** Needs a "final chunk" hook at stream end. Two options: (a) upstream fix in `SOXRStreamAudioResampler` — check whether `soxr.ResampleStream` (the C library binding) exposes a flush/last-chunk parameter on `resample_chunk`, and add a `flush()`/`close()` method pipecat's serializers call on `EndFrame`/`CancelFrame`; or (b) a call_pipeline.py-local workaround in `L16TelnyxFrameSerializer` that, on `EndFrame`/`CancelFrame`, calls `resample_chunk` one more time with a small silence pad to force the tail out before returning. Whichever direction, needs a real audio A/B (not just a sample-count check) to confirm the flushed tail isn't itself audibly distorted.
- **Test:** none yet — this was found via the manual verification script above, not the automated suite. Would need a new test under `backend/tests/voice/` that constructs a serializer with mismatched rates, feeds a known signal, tears down the stream, and asserts the trailing samples are recovered.
