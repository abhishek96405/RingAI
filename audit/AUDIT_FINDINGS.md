# Duuutah AI — Consolidated Audit Findings (Master)

Full-stack, line-by-line audit. Single consolidated log across all series: backend core call path (A1–A8), backend service modules (B), frontend (C), tests/CI/infra (D). Self-contained — every finding has Where / Problem / Risk / Fix.

**Repo:** `abhishek96405/RingAI` · audited at `ringai-deploy` HEAD `0e8fa6d4`
**Product status:** PRE-LAUNCH — no live/paying customers (Bawarchi, Desi Chowrastha, Great Cups/Clips = demo/test data).
**Severity:** 🔴 High / launch-blocker · 🟡 Medium · 🟢 Low/polish
**Status:** ⬜ Open · 🔧 fix in progress · 🔍 verify · ✔️ merged/resolved · ⏸️ deferred (accepted-for-launch, see detail)

---

## ⚠️ Status reconciliation (changed since the core-call-path audit)
Three security hotfix efforts have **merged into `ringai-deploy`** and are reflected as ✔️ where relevant:
- **PR #4** — `/api/me/repair-membership` cross-tenant ownership takeover → now **410 Gone**.
- **PR #5** — OAuth `state` for Square + Stripe Connect → crypto-random single-use (`oauth_state_service.py`); Square webhook → HMAC-SHA256 + dedup + revocation.
- **auth/access-control batch** (`fix/auth-access-control-batch`) — `ensure_restaurant_access` 403→404; `/api/admin/process-reminders` admin-gate; public-menu stored-XSS `html.escape()`. *(PRs #4/#5 confirmed merged; confirm this batch's merge.)*

**All 6 launch-blockers are now resolved**, and the former near-blocker **D3-1 is verified resolved**:
- **A7-1, A7-2** ✔️ — PR-A (commits `0dca8671` + `89aed334`): visible dispatch-failure path + real POS kitchen tickets (Clover per-unit line items).
- **A6-2** ✔️ + **C5-1** ✔️ — PR-B (commit `5629634e`): `/ws/notifications` now requires a valid Clerk token + tenant membership before `accept()`; the frontend sends a fresh token per (re)connect.
- **A3-1 (CSRF half)** ✔️ — PR-B: calendar OAuth `state` is now opaque, single-use, validated; trusted `restaurant_id` derived from the stored record.
- **A1-1, A1-2** ✔️ — THIS PR: CORS wired to the `get_cors_origins()` allowlist (no wildcard+credentials default); `/health` liveness route added.
- **D3-1** ✔️ — re-verified resolved; escalation transfer is robust at `call_pipeline.py:812`.

**Remaining open items are all non-blockers** — called out explicitly so nothing reads as "done" that isn't:
- **B3-7** ✔️ — Google Calendar tokens are encrypted at rest (PR-G, commit `4fff5f6`): `encrypt_calendar_tokens` on connect + refresh, prefix-aware `decrypt_calendar_tokens` on read, field in `ENCRYPTED_CREDENTIAL_FIELDS`. Completes A3-1.
- The **§A medium/low items** (A1-3 perf, A2-x rate-limit/info-leak, A4-x, A5-x billing, A6-x, the §A 🟢 polish cluster).
- The **C31-x marketing-claims cluster** (fabricated integration/feature advertising — legal/content lane).
- The **D3 latent-500 batch** (D3-12/13/14/15 webhook resilience + the remaining D3-2…D3-10 latent NameError/edge branches).

---

# §A — `server.py` (A1–A6)

> **Resolved since this audit:** A8-1, A8-2 (PR-D); A7-3, A7-8, A7-9, A7-11, A7-12, A7-14 (PR-E1) are now fixed and merged.

| ID | Sev | Area | Issue | Status |
|---|---|---|---|---|
| A1-1 | 🔴 | CORS | Wildcard `["*"]` + credentials fallback; secure helper unused | ✔️ |
| A3-1 | 🔴 | OAuth | Google callback uses raw `restaurant_id` as `state` — no validation (CSRF) + unauth callback + plaintext tokens | ✔️ |
| A6-2 | 🔴 | WebSocket | `/ws/notifications` unauth + unauthorized → live cross-tenant data leak | ✔️ |
| A1-2 | 🔴 | Ops | No `/health` endpoint (Render health check + readiness probe) | ✔️ |
| A1-3 | 🟡 | Perf | `get_current_user` does Mongo read+write every request | ✔️ |
| A2-1 | 🟡 | Security | Rate limiting applied to 6 of 95 routes | ⬜ |
| A2-2 | 🟡 | Security/Perf | Public menu page unthrottled + 6 DB queries/hit | ⬜ |
| A2-3 | 🟡 | Info leak | `detail=str(e)` returns raw exceptions to clients (4×) | ⬜ |
| A3-2 | 🟡 | Correctness | Reservation availability-check + insert not atomic (double-book race) | ⏸️ |
| A4-1 | 🟡 | DoS/Cost | WS connection-limit functions imported but never enforced | ⬜ |
| A4-2 | 🟡 | WebSocket | Media-stream WS: no transport auth + no duplicate-stream guard | ⬜ |
| A5-1 | 🟡 | Billing | Overage billing + count increment no idempotency (mitigated by A8 fire-once) | ⬜ |
| A5-2 | 🟡 | Billing | Overage decision reads a stale pre-fetched call count | ⬜ |
| A5-3 | 🟡 | Functional | Square OAuth callback stores raw auth code, never exchanges for token | 🔍 |
| A6-1 | 🟡 | Access ctl | `send_menu_sms_endpoint` no membership check → SMS abuse/spoofing | ⬜ |
| A1-4 | 🟡 | Tech debt | Data migration runs on every startup | ✔️ |
| A2-8/A3-3 | 🟡 | Perf | Double restaurant+membership lookup per request (systemic) | 🔧 |
| A1-5 | 🟢 | Ops | `logging.basicConfig` after early log calls | ✔️ |
| A2-4 | 🟢 | Dead code | `select_restaurant` orphaned + redundant local imports | ⬜ |
| A2-5 | 🟢 | Logic | Unreachable plan-gating branch in `update_restaurant` | ⬜ |
| A2-6 | 🟢 | Branding | "Powered by RingAI" on customer-facing public menu page | ⬜ |
| A1-6 | 🟢 | Branding | "RingAI" in API title + root message | ⬜ |
| A2-7 | 🟢 | Consistency | Input sanitization applied unevenly | ⬜ |
| A1-7 | 🟢 | Resilience | All service modules hard-imported → any import error crashes startup | ⏸️ |
| A4-3 | 🟢 | Analytics | Call duration estimated `len(transcript)*8` (NOT billing) | ⬜ |
| A4-4 | 🟢 | Observability | Silent `except` on POS credential decryption | ⬜ |
| A5-4 | 🟢 | Billing | No explicit Stripe event-id dedup (mitigated; handlers idempotent) | ⬜ |
| A5-5 | 🟢 | Billing | `refund_order` leaks raw Stripe error + Stripe-before-DB + no idempotency key | ⬜ |
| A5-6 | 🟢 | Perf | `$inc`/`$set` fan-out across all 5 collections for one restaurant_id | ⏸️ |
| A6-3 | 🟢 | Access ctl | `telnyx_get_order` authed but not scoped to caller | ⬜ |
| A6-4 | 🟢 | Security | `test-mode/status` + `scenarios` unauthenticated | ⬜ |
| A6-5 | 🟢 | Webhook | Square webhook signs over `str(request.url)` — proxy mismatch risk | ⬜ |

## Detail — High (launch-blockers)

### ✔️ A1-1 — CORS wildcard + credentials; secure helper is dead code (✔️ THIS PR)
**Where:** `server.py:369–377`; `get_secure_cors_origins()` imported `:281`, `get_cors_origins()` `:178` — unused.
**Problem:** Live config was `allow_origins = CORS_ORIGINS or ["*"]` with `allow_credentials=True`.
**Risk:** If `CORS_ORIGINS` unset on Render, the API accepts any origin. (Bearer-token auth lowers severity but fails review.)
**Resolved (THIS PR):** the `cors_origins` assignment now calls `get_cors_origins()` (dev-localhost defaults + `CORS_ORIGINS`/`FRONTEND_URL`, normalized — **never** `["*"]`); the wildcard default is gone. The `add_middleware` call is unchanged (`allow_credentials=True`, `allow_origins=cors_origins`, env regex). `get_secure_cors_origins`/`get_cors_origins` left in place; confirm `CORS_ORIGINS` set on prod for the exact frontend origin.
**Test:** `integration/test_middleware_and_lifespan.py` — `get_cors_origins()` never returns `"*"` with env unset; a disallowed Origin is not reflected back.

### ✔️ A3-1 — Google Calendar OAuth callback: no state validation + unauth token write — CSRF half ✔️ PR-B, token-at-rest encryption ✔️ (B3-7, PR-G)
**Status (THIS update):** the **CSRF half is ✔️ resolved (PR-B, commit `5629634e`)** — the `state` is now opaque, single-use, and validated, and the trusted `restaurant_id` is derived from the stored state record rather than the attacker-supplied query param. **The other half — B3-7 (Calendar token encryption at rest) — is now ✔️ resolved (PR-G, commit `4fff5f6`):** `encrypt_calendar_tokens` on connect + refresh, prefix-aware `decrypt_calendar_tokens` on read, field in `ENCRYPTED_CREDENTIAL_FIELDS`. **A3-1 is fully closed.**
**Where:** connect `:2237`, callback `:2264`; `get_google_auth_url` in `calendar_service.py:33` (`"state": restaurant_id` at `:47`). Contrast Square `:5048` / Stripe Connect `:5127` (both call `consume_oauth_state`).
**Problem:** The connect passes the raw `restaurant_id` as the OAuth `state` (plain, **not** a signed JWT). The callback (`google_calendar_callback`) takes `state`, does `restaurant_id = state` (`:2282`) with **no `consume_oauth_state`, no signature/JWT verify, and no `Depends(get_current_user)`**, then upserts `google_calendar_tokens` into that tenant.
**Risk:** An attacker completes Google OAuth on their own account (valid `code`), then calls `GET /api/calendar/google/callback?code=<their_code>&state=<victim_restaurant_id>` (restaurant_id is semi-public — it appears in `/menu/{restaurant_id}` URLs). The callback writes the **attacker's** Google tokens into the **victim's** config → the victim's AI books its customers' appointments into the **attacker's** calendar (attacker sees customer names/times/phones; or sabotages bookings). Tokens (incl. `refresh_token`) are stored **plaintext** at rest (B3-7).
**Note:** The `tests/FINDINGS.md` claim that Google OAuth "already uses signed-JWT state" is **inaccurate** — `calendar_service.py:47` sets `state = restaurant_id` and the callback never verifies it.
**Fix:** Mirror Square/Stripe — `issue_oauth_state(restaurant_id, user["id"], provider="google")` in connect (carry the minted token as `state`), `consume_oauth_state(state=..., provider="google")` in the callback, reject on invalid/expired. Encrypt tokens at rest (reuse `encryption_utils`; B3-7). Both halves in one PR.
**Test:** `integration/test_api_oauth_integrations.py`, `unit/test_calendar_service_unit.py`.

### ✔️ A6-2 — `/ws/notifications` unauthenticated + unauthorized (✔️ PR-B `5629634e`)
**Where:** `server.py:5674`.
**Problem:** `manager.connect(websocket, restaurant_id)` with no token check, no membership check. Any client could subscribe with `?restaurant_id=<id>`.
**Risk:** Streams real-time new-order (with totals), new-call, and appointment events. `restaurant_id` is public (in `/menu/{restaurant_id}`), so anyone with a menu link could watch live activity. Cross-tenant live-data leak.
**Resolved (PR-B, commit `5629634e`):** the WS now requires a valid Clerk token **and** tenant membership before `accept()`; otherwise it rejects with close code 1008. Two-sided with frontend C5-1.
**Test:** `integration/test_websocket_endpoints.py`, `unit/test_websocket_notifications_unit.py`.

### ✔️ A1-2 — No `/health` endpoint (✔️ THIS PR)
**Where:** referenced in `CF_BYPASS_PREFIXES:5647` + Render health checks, never defined. Only `/api/` (`:1108`) returned 200.
**Risk:** Render health check on `/health` 404s → restart loop; no real readiness probe.
**Resolved (THIS PR):** added an **app-level** `@app.get("/health")` returning `{"status": "ok"}`, matching the `CF_BYPASS_PREFIXES` `/health` entry. Kept a pure **liveness** check (no DB call) on purpose so a transient Mongo blip can't make Render cycle the instance.

### ✔️ A7-1 — Silent order loss (✔️ PR-A `0dca8671`+`89aed334`)
**Where:** `gemini_service.py` `send_order_to_kitchen:529`, DB-only fallback `:583`; `call_pipeline.py` `dispatch_order_if_ready:828`.
**Problem:** When no POS path works, the fallback returns `{"success":True,"method":"database"}` though nothing was dispatched (and it doesn't even persist — that's `on_call_complete`). `dispatch_order_if_ready` marks the order COMPLETED on `success:True`; the failure `else` branch is effectively dead (fallback always "succeeds"). No restaurant alert/SMS/alarm, no real retry. The AI verbally confirms the order to the customer *before* dispatch.
**Risk:** For every demo account (no live POS), each order is silently lost while the customer is told it's confirmed. Same shape will bite any restaurant whose POS call fails.
**Fix:** Distinguish the fallback from a real dispatch; fire a loud restaurant alert (SMS to escalation # + dashboard) on non-dispatch; qualify the AI confirmation when there's no working dispatch path; add real retry/backoff; reconsider auto-COMPLETED. Mirror the reservation-unavailable SMS pattern that already exists in `call_pipeline.py`.
**Test:** `unit/test_gemini_service_pos_dispatch.py`, `voice/test_post_call_extraction_e2e.py` (🔴 xfail-strict).

### ✔️ A7-2 — POS "success" ≠ kitchen ticket fired (✔️ PR-A `0dca8671`+`89aed334`)
**Where:** `gemini_service.py` `_send_to_clover:587`, `_send_to_square:752`.
**Problem:** Both create an order + line items and return success, but **Clover never fires the order** (it sits as an unfired draft) and **Square has no `fulfillment` object** (won't route to the KDS / kitchen printer).
**Risk:** Even with a "working" POS integration, the kitchen may never see the ticket — order silently not made.
**Fix:** Physical kitchen-print test per POS; likely an extra fire/fulfillment API call (Clover order fire; Square `fulfillment`). Toast path → B1.
**Test:** `unit/test_gemini_service_pos_dispatch.py`, `unit/test_pos_sync_unit.py`.

## Detail — Medium (`server.py`)
- **A1-3** ✔️ (PR-J/J1) — `get_current_user` did a Mongo read+write on every authenticated request (`updated_at` regenerated each call, so the `$set` always wrote). Now writes only when a Clerk-sourced profile field actually changed, and an absent claim no longer wipes a stored value; the read is retained. Unit-tested in `tests/unit/test_get_current_user_hot_path.py`.
- **A2-1** — Rate limiting on 6 of 95 routes (`LIMIT_*` mostly unused). Apply to public menu (by IP), bootstrap/auth, all writes, POS/billing. (In-process → fully effective only at 1 instance.)
- **A2-2** — Public menu page (`:1367`) unauth + 5 collection `find_one`s/hit. IP rate-limit + optional cache. (XSS-safe.)
- **A2-3** — `detail=str(e)` 4× leaks internal exceptions. Generic 500, log detail to Sentry.
- **A3-2** ⏸️ **DEFERRED (accepted-for-launch).** `create_reservation` (`server.py:2107`) calls `check_reservation_availability` — which *counts* existing reservation docs for the slot against `capacity_per_slot` (`reservation_service.py`, default 10, overridable via `restaurant.reservation_max_per_slot`) — and then, as a separate step, `db.reservations.insert_one`. Two concurrent requests can both pass the count and both insert → an over-capacity slot. The same check-then-insert is shared by **two** write paths: the operator endpoint (`server.py:2156`) and the voice path (`reservation_service.py:579`), so any real fix must cover both. Because capacity is count-based (no per-slot counter to atomically `$inc`), the cheap mitigations are *not* correct: a unique index only works at capacity=1 (default is 10), and "re-check right before insert" / "insert-then-recount-and-roll-back" still race — with no single contended document, two inserts can each read before the other commits and both decide they fit. A correct fix needs a serialization point: **(a) an atomic per-slot counter doc** (`find_one_and_update(booked < capacity, $inc)`) — correct but a second source of truth that can drift if any create/cancel path misses it; or **(b) a `slot_seat` (0…capacity-1) field + a partial (active-only) unique index** on `(restaurant_id, reservation_date, reservation_time, slot_seat)` — drift-free (the docs stay source of truth, the DB enforces capacity) but needs an `active` flag toggled on cancel, a retry-on-duplicate insert loop in the shared path, and an index + backfill of existing docs. Both approaches touch both insert paths + the cancel/update paths + a migration, including the **live voice booking path**. **Deferred** because reservations are opt-in, Pro-gated, and **default-OFF**, default capacity is 10, and there are no live customers — the realistic pre-launch exposure is low and does not justify reworking the voice path right before launch (vs. the launch-gating PR-L). **TRIGGER: implement approach (b) before reservations are enabled for a real customer at meaningful scale.**
- **A4-1** — WS connection-limit funcs imported (`:292–294`) but never called; media-stream WS (most expensive) uncapped. Call check/register/unregister at accept + in `finally`.
- **A4-2** — Media-stream WS (`:4447`): authz rests only on the start message's `call_control_id` matching `active_calls`; no handshake signature/token; duplicate streams not rejected. Add a short-lived signed token in the stream URL; reject duplicate `call_sid` streams. (Shares auth pattern with A6-2.)
- **A5-1** — Overage billing + count increment (`:4579–4600`) no idempotency guard. **Mitigated** by `_fire_on_call_complete` fire-once (A8), but add `idempotency_key=f"overage:{call_sid}"` as defense-in-depth.
- **A5-2** — Overage decision reads a stale pre-fetched count (`:4586`). Use `find_one_and_update(..., return_document=AFTER)`.
- **A5-3** — Square OAuth callback (`:5044–5064`) stores the raw `auth_code` and sets `square_connected=True` but never exchanges it for a token → integration likely non-functional. Exchange + store encrypted token. (Verify in `pos_sync.py`, B-series.)
- **A6-1** — `send_menu_sms_endpoint` (`:3840`) doesn't enforce membership → SMS cost abuse + spoofing. Use `ensure_restaurant_access`.
- **A1-4** ✔️ (PR-J/J4 — appointment-todo #1) — `migrate_businesses_to_typed_collections` was `@app.on_event("startup")`, re-running a data migration on every boot. Removed the startup decorator; the function is retained as a callable, test-covered utility. The comprehensive one-off lives in `backend/migrate_split_brain.py` (dry-run by default). Safe to unwire: `create_restaurant` writes new businesses straight to the typed collection (and rejects dormant types), so nothing needs ongoing migration, and existing data is already migrated.
- **A2-8 / A3-3** 🔧 (PR-J/J2 — substantially addressed; long tail tracked) — ~18 `restaurant_id` routes called `ensure_restaurant_access` (which already fetches membership + restaurant) and then re-fetched both — 4 reads where 2 suffice. Instead of changing `ensure_restaurant_access`'s return type (a breaking change to all ~77 call sites), added `resolve_restaurant_access(restaurant_id, user) -> (full_restaurant, membership)` (J2a) and refactored `ensure_restaurant_access` to delegate to it (contract unchanged; unit-tested in `tests/unit/test_resolve_restaurant_access_unit.py`). Migrated the highest-value double-lookups — reservation routes (J2b) + POS routes (J2c), 4→2 reads each. **Remaining ~11 double-lookup routes tracked for opportunistic migration** (helper already in place): 5 config-only sites (save 1 read each — settings/calendar config routes), 2 `coll = get_business_collection` variants, and 4 structural outliers where the access check is separated from the re-fetch (demo-data + manual-booking + available-slots) needing per-site care on auth/error ordering. **Enumerate the remainder anytime:** ``grep -n 'membership = await db.memberships.find_one({"restaurant_id"' backend/server.py`` and keep the hits with an `ensure_restaurant_access` within ~8 lines above. **TRIGGER:** migrate each to `resolve_restaurant_access` when next touching that route.

## Detail — Medium (`gemini_service.py`)
- **A7-3** — Clover line-item failures swallowed (`:618–619` logs a warning, continues, returns `success:True`) → an empty/partial order reported as success. Treat line-item failure as order failure (or surface it).
- **A7-6** — **Modifier upcharges ignored everywhere.** `ModifierOption.price_delta` (`server.py:784`) exists but is dropped: the `compute_order_total` tool schema (`call_pipeline.py:151`) accepts only `name`+`quantity` (no modifiers), and `OrderItem.subtotal` = `unit_price×qty`. Paid modifiers are free across the spoken quote, SMS, prepayment, and POS. Add a `modifiers` field to the tool schema + handler; resolve `price_delta` and add `delta×qty` in both `compute_order_total` and `OrderItem.subtotal`.
- **A7-8** — `extract_order_from_transcript` truncates the transcript to the first 4000 chars (`transcript_text[:4000]`) → on long calls the final confirmed order is cut off. (`analyse_call_transcript` correctly keeps the tail — inconsistent.) Use head+tail.
- **A7-9** — `MenuIndex.find` substring matching (`key in item_name or item_name in key`) returns an arbitrary first-dict-order match → wrong item+price (e.g. "water" → "Watermelon Juice"). Require unique/high-confidence matches. (Prompt's "use exact names" partly mitigates.)
- **A7-14** — Stored prompt-injection: `customer_profile.last_name` (from a prior caller's spoken name) is interpolated into the system-prompt greeting (`build_system_prompt`). Sanitize/delimit/length-cap CRM data before interpolation.
- **A7-15** — Prompt instructs that a hangup after readback is "treated as confirmed and proceed" → unconsented order dispatch. Don't auto-confirm on hangup, or flag the order for review instead.
- **A7-17** ✔️ (PR-K/K2a) — `_mock_call_analysis` (the Gemini-unavailable fallback in `analyse_call_transcript`, hit on no-client / JSON-parse-failure / exception) fabricated a random `quality_score` (`randint 78–99`) plus random issues/highlights that were stored and shown as a real analysis. Now returns an honest marker — `quality_score=None`, `analysis_available=False`, `order_accuracy="unknown"`, empty issues/highlights, "analysis was unavailable" summary — and the real path stamps `analysis_available=True`. Backend consumers guarded so a null score doesn't skew/aggregate. Unit-tested in `tests/unit/test_mock_call_analysis_honesty.py`. Frontend "Unavailable" labeling is C16-3 (K2b).

## Detail — Medium (`call_pipeline.py`)
- **A8-1 (confirmed active bug)** — `restaurant.get("pos_type", "").lower()` (`gemini_service.py` `send_order_to_kitchen:534`, `get_kitchen_queue_depth:653`) raises **TypeError** when `pos_type` is present-but-None: the `""` default only applies when the key is *absent*, so a salon doc with `pos_type: null` → `None.lower()`. This is the memory-flagged salon disconnect crash. Fix: `(restaurant.get("pos_type") or "").lower()`.
- **A8-2** — `on_disconnect` (`:1971`) runs the restaurant order-dispatch/extraction path for ALL business types → salon/clinic calls hit A8-1 and waste a Gemini extraction. Guard with `business_type == "restaurant"`. (A8-1 + A8-2 = the salon disconnect crash.)
- **A8-6** ✔️ (PR-K/K1) — `create_call_pipeline` took a `voice` arg but immediately overwrote it with env `GEMINI_VOICE`, so every call used the one env voice and the picker was dead. Fixed with `voice = _resolve_voice(voice, session)` — priority: explicit arg → the restaurant's saved `config.voice_id` (session.config) → env `GEMINI_VOICE` → default "Leda". The picker's IDs are real Gemini voice names (Leda/Kore/Aoede/Puck/Zephyr/Orus/Fenrir/Charon) so no mapping is needed. Self-contained in `call_pipeline.py` (no server.py change). Unit-tested in `tests/unit/test_resolve_voice_unit.py` (config-over-env precedence). Closes C12-1.
- **A8-7** — Appointment dispatch failures silent: `dispatch_booking` (`:1028`) returns `True` on partial/failure with no customer/business alert (A7-1 family). Verify `dispatch_appointment` internals (calendar write + SMS) in `appointment_service.py` (B-series).

## Detail — Low / polish (`server.py`)
- **A1-5** ✔️ (PR-J/J5) — `logging.basicConfig` ran after the import-time log calls (Sentry init, optional-service import warnings, service-module import logging), so early INFO was swallowed (root defaults to WARNING) and early records missed the timestamp/name format. Moved the identical `basicConfig` call (plus the module `logger`) to the top of the module, right after the import block — `basicConfig` is a no-op once the root logger has handlers, so it must run before the first log call. Pure relocation; level/format args unchanged.
- **A2-4** — `select_restaurant` (`:1140`) orphaned (no decorator); redundant local `asyncio`/`HTMLResponse` imports.
- **A2-5** — `update_restaurant` (~`:1230`) pops a field then checks `if field in update_data` (unreachable).
- **A2-6** — "Powered by RingAI" on the customer-facing menu page (~`:1465`). Rebrand before launch.
- **A1-6** — FastAPI title "RingAI API" (`:357`) + root message (`:1108`). Cosmetic.
- **A2-7** — Sanitization uneven (`create_service` rigorous; menu/restaurant rely on Pydantic + output escaping).
- **A1-7** ⏸️ **ACCEPTED (by design)** (PR-J/J5) — on inspection the split is already correct. The genuinely-optional modules are soft-imported with graceful degradation: `sentry_sdk` (try/except → "Sentry init skipped"), `payment_service` (try/except → "SMS payment links disabled"), `auto_learning_service` (try/except → "AI learning disabled"). The core modules (`gemini_service`, `call_pipeline`, `auth_helpers`, `security_middleware`, `rate_limiting`, `encryption_utils`, `reservation_service`) are hard-imported — which is the desired behavior: if a core module can't import, the service is fundamentally broken and should fail fast and loudly at deploy/boot, not start "healthy" and then 500 when a user hits a call/auth/billing path. Softening these to try/except would hide deploy failures (missing dep, bad env) until runtime — strictly worse. No code change.
- **A4-3** — Call duration `len(transcript)*8` in `on_call_complete`. NOT billing (billing is per-call-count). Analytics inconsistent: `:4385` uses accurate `duration_seconds_actual`; `:2672/:2739/:2792` use the estimate.
- **A4-4** — Silent `except` on POS credential decryption (`:4511–4513`). Log to Sentry.
- **A5-4** — No explicit Stripe event-id dedup (`:4862`). Mitigated; add `event.id` dedup as defense-in-depth. (See D3-13.)
- **A5-5** — `refund_order` (`:5212`) leaks raw Stripe error, refunds before DB update, no idempotency key.
- **A5-6** ⏸️ **ACCEPTED (by design; cold-path tidy-up tracked).** The hot-path fan-out is already gone: the per-call `monthly_call_count` `$inc` was de-fanned to break-on-match in PR-H (A5-2), and the `visit_count` `$inc` is a single `customer_profiles` upsert (not a business-collection fan-out). The remaining `$set` fan-outs all live on **cold integration paths** — `stripe_webhook`, `square_callback`, `clover_oauth_exchange`, `stripe_connect_callback`/`disconnect` — which fire rarely (a tenant connects a POS once; webhooks occasionally). There the fan-out is a deliberate safety net: it writes POS/billing flags + encrypted credentials to the tenant doc *regardless of which business collection it lives in*, protecting the most sensitive fields against the collection-misplacement class this codebase has hit (the split-brain bug). Resolving `business_type` once to write a single collection would trade that robustness for ~4 no-op writes on rare events — a bad trade. **Tracked tidy-up (post-launch):** now that only `restaurants`+`salons` are active verticals (I0), narrow the fan-out list from all 5 to `[db.restaurants, db.salons]` — keeps cross-collection robustness on the live axis while dropping the 3 always-empty writes. **TRIGGER:** when the dormant clinic/home_services/legal collections are formally retired.
- **A6-3** — `telnyx_get_order` (`:3824`) authed but not scoped to caller. Scope via the audit record's `restaurant_id`.
- **A6-4** — `test-mode/status` + `test-mode/scenarios` (`:5456`, `:5461`) unauthenticated. Require auth or disable in prod.
- **A6-5** — Square webhook signs over `str(request.url)` (`:5296`) → behind CF/Render scheme/host may mismatch. Ensure proxy headers (ties to A6-7).
- **A6-6 / A6-7 / A6-8** — Stale `ringai-v2.onrender.com` host (see A7-18); verify uvicorn `--proxy-headers`; `client_ip` from spoofable `CF-Connecting-IP` if `CF_SECRET_TOKEN` unset.

## Detail — Low / polish (`gemini_service.py`)
- **A7-7** — Unmatched items dropped from the order, but the customer **is** notified via the confirmation SMS ("we don't have X"). Gaps: restaurant not alerted; `dropped_items` omitted from `to_dict()`. (Revised down from Med.)
- **A7-10** — `detect_call_signals` (`:505`) natural-language phrase matching ("order is confirmed/placed") → false-trigger or miss on phrasing drift. **Systemic** (see closing note).
- **A7-12** — `calculate_is_open` (`:910`) fails OPEN on missing/invalid hours/errors → AI takes orders when closed.
- **A7-16** — "CALL_END" token in the prompt isn't detected by `detect_call_signals` (works via farewell phrase; token is dead).
- **A7-4** — "RingAI" branding in the Clover note + Square `source.name`.
- **A7-5** — Internal cost analytics use stale Twilio rates ($0.0085/min, $0.0083/SMS; TODOs to update to Telnyx ~$0.0046/~$0.0040) → ~2× overestimate (admin-only).
- **A7-11** — Non-numeric quantity crashes extraction (unwrapped `int()`).
- **A7-13** — Misplaced docstring; `get_kitchen_queue_depth` code duplication; outbound kitchen webhook unsigned.
- **A7-18** — Stale `ringai-v2.onrender.com` hardcoded in 3 spots — call.answered/gather WS-URL fallback (`server.py:4210,4250`), `send_menu_sms` default `base_url`, on_ai_transcript menu-SMS (`call_pipeline.py:1378`). Customer menu links → dead/old domain. Use `get_backend_public_url()` / `duuutah.com`.

## Detail — Low / polish (`call_pipeline.py`)
- **A8-3** — Keyword order-type detection misfires on negations ("not delivery, pickup" → locks delivery); reconciled later by extraction.
- **A8-4** — Vestigial `_greeting_in_progress` attribute (set, never read after the VAD greeting lock was removed).
- **A8-5** — Stale `_create_initial_response` docstring (describes the old reactive greeting; actual behavior is proactive `__BEGIN_CALL__` on connect).
- **A8-8** — `send_menu_sms` lacks an idempotency key → duplicate menu texts if the AI repeats the trigger phrase.
- **A8-9** — `generate_twiml_stream_response` (`:2083`) likely dead code (Twilio-era TeXML; the live flow uses Telnyx Call Control) with Twilio-era `callSid` naming.

---

# §B — Backend service modules (B-series, ~20 files)
*Granularity note: long-form B writeups were delivered in prior B-series chat blocks; exact line refs for items without one below should be lifted from those blocks / `tests/FINDINGS.md` at commit time.*

| ID | Sev | File | Issue | Status | Test |
|---|---|---|---|---|---|
| B1-6/7/8 | 🟡 | `toast_integration.py` | Toast order submission malformed / kitchen-fire+fulfillment unverified (A7-2 family); Toast also blocked on partner approval (not live) | ⬜ | `unit/test_toast_integration_unit.py` |
| B2-1 | 🔴* | `appointment_service.py` | Silent appointment dispatch failure — `dispatch_appointment` returns success on partial/failure; calendar-write + SMS not surfaced | ⬜ | `unit/test_appointment_service_validation.py`, `integration/test_api_appointments.py` |
| B2-7 | 🟡 | `appointment_service.py` | Calendar free/busy not wired into `get_available_slots` (one-way sync — bookings push to Google, but external busy events don't block AI slots; manual block/unblock is the workaround). `get_free_busy` helper already scaffolded. ⏸️ Deferred post-launch — feature, not a bug; non-launch-gating. | ⏸️ | `unit/test_calendar_service_unit.py` |
| B2-x | 🟢 | `appointment_service.py` | Dead `function_call` path — verified ABSENT (`git log -S 'function_call'` shows it never existed in `appointment_service.py`; `dispatch_appointment` has no legacy branch). Already resolved. | ✔️ | — |
| B3-7 | 🔴 | `encryption_utils.py` | Google Calendar tokens encrypted at rest (PR-G `4fff5f6`: `encrypt_calendar_tokens` on connect + refresh, prefix-aware `decrypt_calendar_tokens` on read; field in `ENCRYPTED_CREDENTIAL_FIELDS`). Completes A3-1 (CSRF half ✔️ PR-B). | ✔️ | `unit/test_encryption_utils.py`, `security/test_encryption_roundtrip_property.py` |
| B4-10 | 🟡 | `server.py`/middleware | No request body-size limit → oversize-payload DoS | ⬜ | `security/test_input_validation_oversize_payloads.py` |
| B5-26 | 🟡 | `delivery_utils.py` | `validate_delivery_distance` fail-open (delivery allowed when distance check errors); verify zip allowlist enforced | ⬜ | `unit/test_delivery_utils.py` |
| B5-38 | ✔️ | `auto_learning_service.py` | (PR-K/K3a) Auto-applied learned aliases at 5 occurrences with no human gate → now human-gated: `_process_menu_suggestion` only records/increments pending suggestions (no auto-apply), and **approval** applies the alias. Built the previously-**missing** `POST .../learning/aliases/{id}/approve` (calls `_apply_menu_alias` + sets `applied:true` + bumps the learned-alias stat) and `.../reject` (sets `rejected:true`, suppressed from resurfacing) — the audit's "endpoints exist" note was wrong; they 404'd. `get_pending_suggestions` surfaces a stable string `id`. UI wiring is C24-1 (K3b). | ✔️ | `unit/test_auto_learning_service_unit.py` |
| B5-3 | — | menu/`MenuPage` | Cents handling end-to-end (`*100`/`/100`) | ✔️ | `integration/test_api_menu.py` |
| A5-3 | 🟡 | `pos_sync.py` | Square OAuth: raw code stored, token exchange unverified | 🔍 | `integration/test_api_oauth_integrations.py` |

\*B2-1 is P0 **only for the appointment (salon/clinic) vertical**; not a blocker for a restaurant-only launch.

---

# §C — Frontend (React/TS/Vite, C0–C35)

### Foundation / config
- **C0-1 🟢** — repo: three lockfiles present (npm + others). Pick one (CI uses `package-lock.json` → keep npm; delete the rest).
- **C1-1 🟡** — bootstrap: missing `VITE_CLERK_PUBLISHABLE_KEY` fails soft (blank app, no clear error). Fail loud with a visible config error.
- **C2-3 🟡** — config: production build wires test/demo endpoints/flags. Gate test/demo wiring behind a non-prod env check.
- **C20 🟢** — `constants.ts`: `SUPPORTED_LANGUAGES = en/te/hi/es` (te/hi parked); 8-voice catalog present but ignored at runtime (A8-6); `defaultHours`/`days`/`APPOINTMENT_TYPES`/labels duplicated inline in `Onboarding` + `DashboardLayout` instead of imported. Import the shared constants; align the language/voice lists to what actually ships.
- **C6-3 🟢** — dashboard surfaces env-var **names** (not values) — minor info disclosure. Remove from the UI.

### Auth / access control
- **C5-1 ✔️** (PR-B `5629634e`) — `useWebSocketNotifications.ts` now sends a fresh Clerk token per (re)connect and won't open an unauthenticated socket; the server authenticates + authorizes before subscribe (frontend half of **A6-2**).
- **C1-5 ✔️** — `AdminPage` is server-side 403-gated (corrected to RESOLVED).
- **C8-1 ✔️** — `VITE_ADMIN_CLERK_ID` *is* used (gates the Admin nav link in `DashboardLayout`); corrected to RESOLVED.
- **C14-1 🟡** — `DashboardLayout.tsx:83`: `console.log("Admin debug", {ADMIN_CLERK_ID, userId, match})` runs every render → leaks the admin Clerk ID + current user's Clerk ID to the browser console. Delete the line (independently logged in `tests/FINDINGS.md`).

### Billing / plan gating
- **C7-1 🟡** — `api.ts`: `getPlanFeatures` defined but unused **and broken** (the backend endpoint 500s — see D3-3). Fix the backend (D3-3) then wire or remove.
- **C12-6 🟡** — exact-case `plan === "PRO"` gate in ≥5 components (`VoiceAndAITab`, `ReservationsPage`, `FulfillmentTab`, `DashboardLayout`, `AILearningWidget`/`DashboardHome`) walls Pro users out of voice + multilingual + reservations + upsell + auto-learning. Make gates case-insensitive; normalize the stored plan value on the backend.
- **C15-6 🟡** — mechanism behind C12-6: `Onboarding` sends UPPERCASE `"PRO"`, `BillingPage` sends lowercase `"pro"` → casing mismatch. Normalize on write.
- **C23-1 🔍** — `DashboardHome` calls `activateRestaurant` on a client-controlled `?billing=success` param → **verify** the backend confirms a real Stripe subscription before activating, else a user can self-activate via `/dashboard?billing=success` (billing bypass).
- **C23-5 🔍** — `DashboardHome` revenue **chart** renders `revenue` without `/100` while the KPI tiles divide by 100 → if the field is cents, the chart is 100× too high. Confirm units; apply `/100` consistently.
- **C19-1 🟢** — `PaymentSuccessPage` trusts the client `?cancelled` param. Confirm server-side.
- **C27-1 🟢** — `Signup`: "Join Thousands of Businesses" is false. Remove/soften.

### Fulfillment / failure-visibility
- **C9-1 🟡** — `OrdersPage` surfaces no dispatch/kitchen status → A7-1 silent loss is invisible to operators. Surface dispatch state + a failure banner.
- **C9-3 🟡** — `OrdersPage` fetches ≤3 pages (~300 most-recent calls) then silently truncates older orders, with no "showing N of M". Add real pagination (match `CallsPage`).
- **C21-1 🟡** — fulfillment: delivery radius relies on the fail-open `validate_delivery_distance` (B5-26). Verify a zip allowlist is enforced.
- **C21-4 🟡** — `FulfillmentTab` saves to two docs (restaurant + config) → partial-save risk if one write fails. Make it transactional or reconcile.
- **C16-3 ✔️** (PR-K/K2b) — with A7-17 fixed (K2a) the analysis fallback returns a null score + `analysis_available=false` instead of fabricated values, so the UI is already truthful (the list row hides a null score). K2b makes it explicit: the detail Quality Score tile reads "Unavailable" and the AI-Analysis block shows a muted "analysis was unavailable" note when `analysis_available === false`. (Transcript-only, no stored audio — a positive.)

### Voice / AI / Pro features
- **C12-1 ✔️** (PR-K/K1) — resolved via A8-6: `create_call_pipeline` now honors `config.voice_id` instead of the env voice, so the `VoiceAndAITab` picker drives live calls. No frontend change needed (the picker already persists `config.voice_id`).
- **C12-2 🟡** — multilingual (te/hi) is advertised but parked/unreliable (VAD wedge, code-mixed trigger mismatches, non-English STT). Keep clearly beta until reliable.
- **C22-1 🟡** — `RulesTab` free-text `business_rules` / `escalation_rules` are injected into the system prompt **unvalidated** → an owner could override safety guardrails. Ensure hardcoded safety rules take precedence in prompt ordering; validate/escape owner text. (Pairs with `unit/test_gemini_service_prompt_assembly.py` — verify the safety-ordering assertion.)
- **C24-1 ✔️** (PR-K/K3b) — `AILearningWidget` now renders pending aliases as approve/reject rows (was read-only), wired to `approveLearningAlias` / `rejectLearningAlias` — approve adds the alias to the menu, reject dismisses it (endpoints were **built in K3a**; the audit's "endpoints already exist" note was wrong). The widget also moved off the dashboard main page into its own **AI Learning** tab (`/dashboard/learning`, restaurant-only, Pro-gated, nav link in `DashboardLayout`).
- **C11 ✔️** — `PhoneForwardingTab` escalation-number config feeds the human-escalation transfer, which is now ✔️ resolved (D3-1). Escalation actually transfers.

### Appointment vertical
- **C17-1 🟡** — `AppointmentsPage` surfaces conflict status (better than Orders) but total-failure dispatch (B2-1) is invisible. Surface total-failure.
- **C17-4 🟡** — no manual appointment creation. Add it (reservations already have this).
- **C18-2 🟡** — reservations have manual create + confirm; appointments lack both → the appointment vertical is less complete. Bring appointments to parity before selling salons.
- **C15-8 ✔️** — Verified correct. `auto_detect_timezone(address)` (`server.py:493`, Google Geocoding + Timezone API) runs in `create_restaurant` and on address-change in update whenever tz is still the `America/Chicago` default — so it never clobbers an explicit pick, and degrades to the default on geocode failure with the `BusinessTab` manual override as backstop. The Onboarding "auto-detected from address" claim is accurate.

### 🔴 Marketing-claims cluster (pre-launch blocker — legal/FTC + trust; non-code lane)
- **C32-1 🔴** — `FeaturesSection` claims **"SOC 2 compliant"** (no audit; open security holes) — highest-liability claim on the site. Also "30+ languages natively" (actually 4, parked). Remove both until true.
- **C28-1 🟠** — `TestimonialsSection` has fabricated testimonials (3 invented people + specific result claims) + fabricated stats ("5,000+ businesses", "2.5M+ calls", "99.8% uptime", "4.9/5") under "Real Results from Real Businesses." Remove/relabel (FTC 2024 reviews/testimonials rule).
- **C31-1 🟠** — `IntegrationsStripSection` advertises OpenTable/Resy/Toast/Yelp/SevenRooms/Square — only Square (+ unlisted Clover) are real → 5 of 6 fabricated. Advertise only what's real.
- **C30-3 🟡** — `PricingSection` advertises Toast POS (unapproved + malformed B1). Remove until real. (C30-1: plan catalog hardcoded a 3rd time.)
- **C29-1 / C34-1 🟡** — Hero "5,000+ businesses" vs CTA "500+" → fabricated **and** mutually inconsistent. Reconcile to one true number.
- **C33-1 🟡** — FAQ "14-day free trial" vs 7-day everywhere else. Reconcile.
- **C35-1 🟡** — `FooterSection` legal links all `href="#"` (Privacy/Terms/Security/GDPR) → no published legal pages (required by Stripe live mode + GDPR/CCPA). Publish before launch.

### Clean positives (don't "fix")
`BusinessTab`, `HoursTab` (use shared constants correctly), Login/Signup Clerk components, `ProtectedRoute`. B5-3 (cents end-to-end) resolved.

### Cross-cutting C themes
(1) marketing claims exceed reality (launch-blocker, non-code); (2) Pro-tier features that don't deliver (voice A8-6/C12-1, multilingual C12-2, upsell, auto-learning B5-38/C24-1, plan-casing lockout C12-6); (3) failure-visibility asymmetry (orders hide dispatch failure C9-1; appointments surface conflicts not total failure C17-1; reservations most complete); (4) "defined but not wired" (approve/reject C24-1, getPlanFeatures C7-1, VITE_ADMIN_CLERK_ID).

---

# §D — Tests / CI / Infra

### Headline: the test suite + CI are a genuine strength
~100 backend test files (`unit` 33, `integration` 15, `security` 19, `voice` 21, `webhooks` 9) + ~40 frontend test files; 38 KB `conftest.py`; real CI (`tests.yml`: backend pytest by marker + branch coverage, frontend Vitest + coverage, separate nightly live job). **The xfail-strict pattern makes the suite a ready-made fix-verification harness** — fixing a bug + deleting one `xfail` marker turns the suite red→green as proof.

### CI / infra findings
- **D1-1 🔍** — Branch protection: confirm CI checks are **required** before merge (workflow exists ≠ gating).
- **D1-2 🟡** — Tests run on push to the **deploy** branch, but Render/Vercel deploy on push **independently** of CI → a red commit still ships. Staging-first closes this.
- **D2-1 🟡** — No `--cov-fail-under` threshold → coverage measured + uploaded but **not enforced**.
- **D2-2 🟢** — No lint/type-check in CI (no ruff/mypy backend; no tsc/eslint frontend).
- **D2-3 (note)** — "CI green" coexists with ~15 known xfail-strict bugs (by design — means no regressions beyond documented xfails).

### D3 — Backend bugs the tests found that static review missed (exact lines from `tests/FINDINGS.md`; mostly ⬜ open, each has an xfail-strict capture)
| ID | Sev | File:line | Bug | Fix |
|---|---|---|---|---|
| D3-1 | ✔️ | `call_pipeline.py:812` | **RESOLVED / re-verified** — `_transfer_call` no longer references undefined `settings`; escalation transfer is robust (was: undefined `settings` → every human-escalation transfer silently failed, caller hung up not transferred) | ✔️ resolved — `os.environ.get("TELNYX_API_KEY","")` in place; transfer path verified |
| D3-2 | ✔️ | `server.py:1359` | `public_menu_page` `HTMLResponse` UnboundLocalError on not-found → 500 not 404 (separate from the XSS `html`→`page_html` rename) | Remove the redundant local `from fastapi.responses import HTMLResponse` |
| D3-3 | ✔️ | `server.py:4695` | `plan-features` uses undefined `payload.restaurant_id` → always 500 (explains C7-1) | Use the `restaurant_id` path param |
| D3-4 | ✔️ | `server.py:3478/3552/3649` | `httpx` not module-imported → Telnyx error paths NameError → 500 not 502 | Add top-level `import httpx` |
| D3-5 | ✔️ | `server.py:3037` | `simulate_call` `timedelta` UnboundLocalError when reservations disabled | Remove the local `from datetime import ...` shadow |
| D3-6 | ✔️ | `server.py:1882` | `create_reservation` returns raw `ObjectId` → 500 on every successful create (qualifies C18 manual create) | `doc.pop("_id", None)` before returning |
| D3-7 | ✔️ | `call_pipeline.py:925` | `classify_booking_intent` matches "tomorrow" before "day after tomorrow" → wrong date | Check "day after tomorrow" first |
| D3-8 | ✔️ | `call_pipeline.py:569` | `dispatch_order_if_ready` doesn't reset `_order_dispatched` after extraction failure → blocks retry within the call (ties A7-1) | Reset `_order_dispatched = False` before the for/else `return False` |
| D3-9 | ✔️ | `server.py:5258` | `run_test_scenario` undefined `call_sid` in clinic/salon branch + unguarded `config.get` | Generate a placeholder `call_sid`; guard `config.get` with `if config else default` |
| D3-11 | 🟡 | `gemini_service.py` | Upsell is prompt-toggle only; no `decide_upsell`, no cuisine-match guard (could suggest Tiramisu for biryani) | Add structured `decide_upsell(cart)` keyed by cuisine |
| D3-12 | ✔️ | `server.py:4703` | Stripe webhook 500 on missing `data.object` | `event.get("data",{}).get("object")` + short-circuit |
| D3-13 | 🟡 | `server.py:4689` | Stripe webhook no event-id dedup → duplicate payment SMS on replay | Dedup via `webhook_events` on `event_id` |
| D3-14 | 🟢 | `server.py:4689` | Stripe webhook accepts future-timestamp signed payloads | Two-sided ±300s window check |
| D3-15 | ✔️ | `server.py:5171` | Square webhook 500 on signed non-dict JSON body | `if not isinstance(event, dict): 400` |
| D3-10 | ✔️ | `server.py:117` | `setup_signal_handlers` fails on non-main-thread lifespans | Skip/try-except when not main thread |

### Resolved-via-tests (✔️ merged into `ringai-deploy`)
repair-membership takeover (PR #4) · OAuth state Square/Stripe + Square webhook signing (PR #5) · ensure_restaurant_access 403→404 · admin-reminders gate · public-menu XSS escape (auth batch — verify merge). Tests: `security/test_oauth_state_token_security.py`, `webhooks/test_square_*`, `integration/test_api_root_and_bootstrap.py` (`…does_not_steal_other_tenants`), `security/test_admin_role_enforcement.py`, `security/test_input_validation_html_injection.py`.

---

# §E — Coverage map (findings ↔ tests ↔ status)
Legend: ✅ acceptance test passing · 🔴xf xfail-strict capture (flips green when fixed) · 🟡 path tested, risk not asserted · ⛔ gap

**Blockers (all ✔️ resolved):** A1-1 ✔️ → `integration/test_middleware_and_lifespan` (no-wildcard + disallowed-origin) · A1-2 ✔️ → `integration/test_api_root_and_bootstrap` (`/health`) · A3-1 CSRF ✔️ → `integration/test_api_oauth_integrations` + `unit/test_calendar_service_unit` (token-at-rest encryption ✔️ B3-7, PR-G `4fff5f6`) · A6-2 ✔️ → `integration/test_websocket_endpoints` + `unit/test_websocket_notifications_unit` · A7-1 ✔️ → `unit/test_gemini_service_pos_dispatch` + `voice/test_post_call_extraction_e2e` · A7-2 ✔️ → `unit/test_gemini_service_pos_dispatch` + `unit/test_pos_sync_unit` + `unit/test_toast_integration_unit`.
**All D3 bugs:** each has its named xfail-strict capture (🔴xf) — see §D table for file mapping.
**Frontend:** C12-1 `VoiceAndAITab.test` · C24-1 `AILearningWidget.test` 🟡 · C22 `RulesTab.test` + `unit/test_gemini_service_prompt_assembly` 🔍 · C4-4 (bootstrap race) `AppSessionContext.test` 🟡 · C1-x `ProtectedRoute.test` ✅ · C9-3/C14-1/C23-3 tests exist but render-only 🟡.
**Gaps (⛔):** marketing-claims cluster (C28–C35, not unit-testable — legal/content lane) · C12-6 plan-casing (no case-insensitivity assertion) · front-end info-leak console asserts · failure-visibility UX · infra (branch protection D1-1, deploy-gating D1-2, M0 backups, scheduler lock, Vercel limits).

---

# §F — What's solid (carry forward — don't "fix")
### `server.py`
- **Tenancy sweep (all 95 routes): 71 enforce `ensure_restaurant_access`, 5 signature/state-verified webhooks/OAuth, 2 admin-gated, 8 self/public.** No unguarded tenant CRUD. By-item/by-group/by-service routes resolve the parent `restaurant_id` first (correct IDOR protection). Tenancy guard returns 404 not 403 (no existence leak).
- `repair_membership` privilege-escalation hole found + killed (HTTP 410). Public menu page XSS-safe (`html.escape`). Clerk JWT verification (JWKS + issuer) correct.
- **Telnyx webhooks verify ed25519 signature before processing, 403 on failure** (both handlers).
- **Stripe webhook**: signature verified, fails closed; order-prepayment idempotent.
- **Square webhook**: HMAC-SHA256 verified (constant-time), fails closed, event-id dedup w/ 7-day TTL.
- `refund_order`: tenancy double-scoped to `call_sid`+`restaurant_id`, status guards, correct Connect refund (`reverse_transfer`, `refund_application_fee`).
- POS credentials encrypted at rest + decrypted only at point of use. Zombie-call sweeper (>10 min); TTL indexes (webhook_events 7d, oauth_states); graceful SIGTERM drain.
### `gemini_service.py`
- Order totals come from the **canonical menu prices, not the LLM** (can't hallucinate a total — modulo A7-6); items validated against the menu (no invented items).
- Allergen protocol forbids "allergen-free"/"safe" guarantees; no-payment-over-phone rule; plan-gated prompt. `evaluate_call_quality` checks AI disclosure / readback / escalation; robust JSON parsing. `analyse_call_transcript` tail-truncates correctly + alias-learning loop; SMS idempotency keys; dynamic ETA.
### `call_pipeline.py` (best-engineered file)
- **Silent-reservation-drop VERIFIED FIXED** — `_ensure_reservation_booked` uses double-checked locking, called idempotently from all 4 paths, runs early in the teardown-protected window.
- **`_fire_on_call_complete` is fire-once** (flag before the await) — mitigates A5-1 double-billing.
- **Warm-transfer state machine**: backgrounds slow analytics, stops streaming (no idle billing), fallback watchdog, idempotent bridge/timeout handlers, **refuses to transfer to the restaurant's own AI DID** (prevents an infinite forwarding loop). *(NB: the former Telnyx-call break is now ✔️ resolved — see D3-1.)*
- **Minimal AI tool surface** (only `check_availability` + `compute_order_total`, both read/compute) — all side-effects gated by `CallSession`. `_fn_in_progress` 3-layer guard prevents VAD from interrupting an in-flight tool call; Gemini-stuck recovery.
### Tests / CI
- Mature, well-structured, mapped to the risk surface; xfail-strict harness ready to verify fixes.

---

# Cross-cutting fix clusters (for the fix-dependency map)
- **WebSocket authz** → A4-2 + A6-2 + C5-1 (one auth pattern, both sockets + frontend).
- **Double restaurant+membership lookup** → A2-8 / A3-3 (one `ensure_restaurant_access` signature change fixes ~20 routes).
- **Rate-limit + connection-cap wiring** → A2-1 + A2-2 + A4-1.
- **Proxy-header / `request.url` trust** → A6-5 + A6-7.
- **Encrypt tokens at rest** → A3-1 + B3-7 reuse the existing POS-credential encryption.
- **`detail=str(e)` leak** → A2-3 + A5-5 (one error-handling helper).
- **Silent-dispatch-failure alerting** → A7-1 + A8-7 (mirror the existing reservation-unavailable SMS pattern).
- **Stale `ringai-v2.onrender.com` host** → A6-6 + A7-18 (3 locations).
- **Natural-language signal fragility** → A7-10 (systemic across `gemini_service` `detect_call_signals` + `call_pipeline` `on_ai_transcript`).
- **Webhook resilience/idempotency** → D3-12/13/14/15 + A5-4.
- **Latent NameError/shadowing class** → D3-1/2/3/4/5/6/9 (rarely-hit error/edge branches; add lint/type-check D2-2 to catch the class).

---

## POS — Deferred / Tracked

**Launch decisions:** customer **prepayment is intentionally disabled for launch**
(commit `3b9c3436` — UI removed, the underlying code is kept **dormant**, not
deleted, so it can be re-enabled later). The three deferred POS items below —
**SQUARE-PRINT-1, SQUARE-PREPAY-1, TOAST-REBUILD-1** — remain **parked**.

Items intentionally NOT built yet. Each has a concrete trigger and a test/verify
method so they can be picked up without re-discovery.

- **SQUARE-PRINT-1** — *Verify OPEN+PROPOSED orders fire Square KDS / kitchen printer.*
  We create the Square order as `state: OPEN` with a `PICKUP`/`DELIVERY`
  fulfillment in state `PROPOSED` and no payment (A7-2). It is unverified whether
  that combination actually fires a Square KDS ticket or a Square-connected
  kitchen printer.
  - **Trigger:** first real Square restaurant onboarded (need their hardware /
    KDS-routing setup).
  - **Test method:** Square sandbox seller with Square for Restaurants + KDS
    routing enabled; create an OPEN order with a PROPOSED pickup fulfillment and
    no payment, observe whether the KDS/printer fires.
  - **Until verified:** Square relies on Duuutah dispatch (dashboard + operator
    SMS) as the kitchen ticket — the order is visible but the print/KDS path is
    not guaranteed.

- **SQUARE-PREPAY-1** — *Optional Square prepayment via Checkout API payment link.*
  Send a `CreatePaymentLink` (Checkout API) link over SMS. A paid link flips the
  order `DRAFT → OPEN` and routes to Square KDS natively with NO 1%
  external-tender fee.
  - **Design:** per-restaurant onboarding setting — prepay `REQUIRED` /
    `OPTIONAL` / `OFF`.
  - **Needs:** a paid-order webhook handler + a "pending payment" order state.
  - **Trigger:** post-launch (revenue/UX optimization, not a launch blocker).

- **TOAST-REBUILD-1** — *`toast_integration.py` is currently non-functional; rebuild.*
  Known bugs in the current implementation:
  - Order payload is missing the `checks[]` wrapper (selections must live inside
    a check).
  - `diningOption` uses literal `"TAKEOUT"`/`"DELIVERY"` instead of real
    per-restaurant Toast GUIDs.
  - `itemGroup.guid` assumes `menu_item_id` is the Toast MenuGroup GUID (it isn't
    — needs a real Toast menu-sync mapping).
  - The `customer` object is on the Order; Toast expects it on the Check.
  - `deliveryInfo` is too thin (needs city/state/zip).
  - Open-price items need `openPriceAmount`.
  - **Blocked on:** Toast partner-program access (a business gate, not code).
  - **Trigger:** Toast partner access granted → rebuild against the checks-based
    structure + genuine menu-GUID sync, then certify via Toast review.