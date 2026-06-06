# Duuutah AI — Audit Findings Log

Running log of issues found during the line-by-line backend audit. Pairs with `AUDIT_LEDGER.md` (which tracks *coverage*); this tracks *issues*. Fixes are batched and flow through staging → prod; nothing here is fixed until marked ✔️.

**Repo:** `abhishek96405/RingAI` · audited at `ringai-deploy` HEAD
**Scope of this version:** `server.py` (A1–A6, all 95 routes) + `gemini_service.py` (A7) + `call_pipeline.py` (A8) — the full core call path, ~10,000 lines.
**Severity:** 🔴 High / launch-blocker · 🟡 Medium · 🟢 Low/polish
**Status:** ⬜ Open · 🔧 fix prompt issued · ✔️ merged

---

## Summary

### `server.py` (A1–A6)

| ID | Sev | Area | Issue | Status |
|---|---|---|---|---|
| A1-1 | 🔴 | CORS | Wildcard `["*"]` + credentials fallback; secure helper unused | ⬜ |
| A3-1 | 🔴 | OAuth | Google Calendar callback: no `state` validation (CSRF) + unauth token write + plaintext tokens | ⬜ |
| A6-2 | 🔴 | WebSocket | `/ws/notifications` unauthenticated + unauthorized → live cross-tenant data leak | ⬜ |
| A1-2 | 🔴 | Ops | No `/health` endpoint (breaks Render health check + no readiness probe) | ⬜ |
| A1-3 | 🟡 | Perf/Resilience | `get_current_user` does a Mongo read+write on every request | ⬜ |
| A2-1 | 🟡 | Security | Rate limiting applied to 6 of 95 routes | ⬜ |
| A2-2 | 🟡 | Security/Perf | Public menu page unthrottled + 6 DB queries/hit | ⬜ |
| A2-3 | 🟡 | Info leak | `detail=str(e)` returns raw exceptions to clients (4×) | ⬜ |
| A3-2 | 🟡 | Correctness | Reservation availability check + insert not atomic (double-booking race) | ⬜ |
| A4-1 | 🟡 | DoS/Cost | WS connection-limit functions imported but never enforced | ⬜ |
| A4-2 | 🟡 | WebSocket | Media-stream WS has no transport auth + no duplicate-stream guard | ⬜ |
| A5-1 | 🟡 | Billing | Overage billing + call-count increment have no idempotency guard (mitigated by A8 fire-once) | ⬜ |
| A5-2 | 🟡 | Billing | Overage decision reads a stale pre-fetched call count | ⬜ |
| A5-3 | 🟡 | Functional | Square OAuth callback stores raw auth code, never exchanges it for a token | ⬜ |
| A6-1 | 🟡 | Access control | `send_menu_sms_endpoint` doesn't enforce membership → SMS abuse/spoofing | ⬜ |
| A1-4 | 🟡 | Tech debt | Data migration runs on every startup | ⬜ |
| A2-8 / A3-3 | 🟡 | Perf | Double restaurant+membership lookup per request (systemic) | ⬜ |
| A1-5 | 🟢 | Ops | `logging.basicConfig` after early log calls | ⬜ |
| A2-4 | 🟢 | Dead code | `select_restaurant` orphaned + redundant local imports | ⬜ |
| A2-5 | 🟢 | Logic | Unreachable plan-gating branch in `update_restaurant` | ⬜ |
| A2-6 | 🟢 | Branding | "Powered by RingAI" on the **customer-facing** public menu page | ⬜ |
| A1-6 | 🟢 | Branding | "RingAI" in API title + root message | ⬜ |
| A2-7 | 🟢 | Consistency | Input sanitization applied unevenly | ⬜ |
| A1-7 | 🟢 | Resilience | All service modules hard-imported → any import error crashes startup | ⬜ |
| A4-3 | 🟢 | Analytics | Call duration estimated `len(transcript)*8`; inconsistent with `duration_seconds_actual` (NOT billing) | ⬜ |
| A4-4 | 🟢 | Observability | Silent `except` on POS credential decryption | ⬜ |
| A5-4 | 🟢 | Billing | No explicit Stripe event-id dedup (mitigated; handlers idempotent) | ⬜ |
| A5-5 | 🟢 | Billing | `refund_order` leaks raw Stripe error + Stripe-before-DB ordering + no idempotency key | ⬜ |
| A5-6 | 🟢 | Perf | `$inc`/`$set` fan-out across all 5 collections for one restaurant_id | ⬜ |
| A6-3 | 🟢 | Access control | `telnyx_get_order` authed but not scoped to caller | ⬜ |
| A6-4 | 🟢 | Security | `test-mode/status` + `test-mode/scenarios` unauthenticated | ⬜ |
| A6-5 | 🟢 | Webhook | Square webhook signs over `str(request.url)` — proxy scheme/host mismatch risk | ⬜ |

### `gemini_service.py` (A7)

| ID | Sev | Area | Issue | Status |
|---|---|---|---|---|
| A7-1 | 🔴 | Fulfillment | Silent order loss — DB-only fallback returns `success:true` though nothing dispatched; AI confirms to customer before dispatch; no restaurant alert/retry | ⬜ |
| A7-2 | 🔴 | Fulfillment | POS "success" ≠ kitchen ticket fired — Clover order never fired (unfired draft); Square has no `fulfillment` (won't route to KDS) | ⬜ |
| A7-3 | 🟡 | Fulfillment | Clover line-item failures swallowed → empty/partial order reported as success | ⬜ |
| A7-6 | 🟡 | Revenue | Modifier upcharges ignored everywhere (`price_delta` dropped; tool schema has no modifiers field) | ⬜ |
| A7-8 | 🟡 | Correctness | `extract_order_from_transcript` truncates to first 4000 chars → long-call orders cut off | ⬜ |
| A7-9 | 🟡 | Correctness | `MenuIndex.find` substring match returns arbitrary first match (e.g. "water" → "Watermelon Juice") | ⬜ |
| A7-14 | 🟡 | Security | Stored prompt-injection via customer name interpolated into system prompt | ⬜ |
| A7-15 | 🟡 | Consent | Hangup-after-readback treated as confirmation → unconsented dispatch | ⬜ |
| A7-17 | 🟡 | Integrity | `_mock_call_analysis` fabricates random quality scores, stored/shown as real | ⬜ |
| A7-7 | 🟢 | UX | Unmatched items dropped (customer IS told via SMS); restaurant not alerted; `dropped_items` omitted from `to_dict()` | ⬜ |
| A7-10 | 🟢 | Correctness | `detect_call_signals` natural-language phrase matching (systemic — see A8) | ⬜ |
| A7-12 | 🟢 | Correctness | `calculate_is_open` fails OPEN on missing/invalid hours | ⬜ |
| A7-16 | 🟢 | Dead code | "CALL_END" token in prompt not detected (works via farewell phrase) | ⬜ |
| A7-4 | 🟢 | Branding | "RingAI" in Clover note + Square `source.name` | ⬜ |
| A7-5 | 🟢 | Analytics | Cost analytics use stale Twilio rates (~2× overestimate; admin-only) | ⬜ |
| A7-11 | 🟢 | Robustness | Non-numeric quantity crashes extraction (unwrapped `int()`) | ⬜ |
| A7-13 | 🟢 | Tech debt | Misplaced docstring; `get_kitchen_queue_depth` dup; unsigned outbound kitchen webhook | ⬜ |
| A7-18 | 🟢 | Config | Stale `ringai-v2.onrender.com` host (consolidated with A6-6; 3 locations) | ⬜ |

### `call_pipeline.py` (A8)

| ID | Sev | Area | Issue | Status |
|---|---|---|---|---|
| A8-1 | 🟡 | Active bug | `restaurant.get("pos_type","").lower()` → TypeError when `pos_type` is present-but-None (salons) | ⬜ |
| A8-2 | 🟡 | Correctness | `on_disconnect` runs the restaurant order path for ALL business types (triggers A8-1, wastes Gemini call) | ⬜ |
| A8-6 | 🟡 | Functional | Per-restaurant voice config ignored — `create_call_pipeline` overwrites `voice` arg with env var | ⬜ |
| A8-7 | 🟡 | Fulfillment | Appointment dispatch failures silent — `dispatch_booking` returns True on partial/failure, no alert (A7-1 family) | ⬜ |
| A8-3 | 🟢 | Correctness | Keyword order-type detection misfires on negations ("not delivery, pickup") | ⬜ |
| A8-4 | 🟢 | Dead code | Vestigial `_greeting_in_progress` attribute | ⬜ |
| A8-5 | 🟢 | Docs | Stale `_create_initial_response` docstring (describes old reactive greeting) | ⬜ |
| A8-8 | 🟢 | Correctness | `send_menu_sms` lacks idempotency key → duplicate menu texts | ⬜ |
| A8-9 | 🟢 | Dead code | `generate_twiml_stream_response` likely dead (Twilio-era TeXML) | ⬜ |

**Launch-blockers (must fix before launch):** A1-1 (CORS) · A1-2 (`/health`) · A3-1 (Google OAuth CSRF) · A6-2 (notifications WS) · **A7-1 (silent order loss)** · **A7-2 (POS ≠ kitchen ticket fired)**.

**Systemic themes:** (1) REST authorization is rigorous (71/95 routes enforce `ensure_restaurant_access`; no unguarded tenant CRUD) — gaps cluster in CORS, OAuth, and **WebSocket** authz. (2) **Order/appointment fulfillment is optimistic** — multiple paths report success without confirming the kitchen/calendar actually received the work, and the AI verbally confirms before dispatch (A7-1/A7-2/A7-3/A8-7). (3) **Confirmation signals are natural-language phrase matches** on the AI's speech (A7-10) — the single biggest call-flow correctness risk; phrasing drift can miss a trigger or false-fire one.

---

## Detail — High (launch-blockers)

### 🔴 A1-1 — CORS wildcard + credentials; secure helper is dead code
**Where:** `server.py:369–377`; `get_secure_cors_origins()` imported `:281`, `get_cors_origins()` `:178` — unused.
**Problem:** Live config is `allow_origins = CORS_ORIGINS or ["*"]` with `allow_credentials=True`.
**Risk:** If `CORS_ORIGINS` unset on Render, API accepts any origin. (Bearer-token auth lowers severity but fails review.)
**Fix:** Wire `get_secure_cors_origins()`; drop the `"*"` default + dead functions. Confirm `CORS_ORIGINS` set on prod.

### 🔴 A3-1 — Google Calendar OAuth callback: no state validation + unauth token write
**Where:** callback `:2265`, connect `:2238`. Contrast Square `:5044` / Stripe Connect `:5104` (both call `consume_oauth_state`).
**Problem:** Google callback takes `state` as the raw `restaurant_id`, never validates it, no auth, upserts `google_calendar_tokens` into that restaurant.
**Risk:** Attacker completes Google OAuth for their own account, calls callback with `state=<victim_id>` → their tokens written to the victim → victim's AI books customer appointments into the attacker's calendar. Tokens (incl. `refresh_token`) stored plaintext.
**Fix:** Mirror Square/Stripe — `issue_oauth_state`/`consume_oauth_state`; encrypt tokens at rest (POS creds already are — reuse `encryption_utils`).

### 🔴 A6-2 — `/ws/notifications` unauthenticated + unauthorized
**Where:** `server.py:5674`.
**Problem:** `manager.connect(websocket, restaurant_id)` with no token check, no membership check. Any client may subscribe with `?restaurant_id=<id>`.
**Risk:** Streams real-time new-order (with totals), new-call, and appointment events. `restaurant_id` is public (in `/menu/{restaurant_id}`), so anyone with a menu link can watch live activity. Cross-tenant live-data leak.
**Fix:** Authenticate the WS (Clerk token via query/subprotocol) + verify membership before connect. (Shares one auth pattern with A4-2.)

### 🔴 A1-2 — No `/health` endpoint
**Where:** referenced in `CF_BYPASS_PREFIXES:5647` + Render health checks, never defined. Only `/api/` (`:1108`) returns 200.
**Risk:** Render health check on `/health` 404s → restart loop; no real readiness probe.
**Fix:** Immediate: set Render Health Check Path to `/api/`. Better: add `/health` with a Mongo ping.

### 🔴 A7-1 — Silent order loss
**Where:** `gemini_service.py` `send_order_to_kitchen:529`, DB-only fallback `:583`; `call_pipeline.py` `dispatch_order_if_ready:828`.
**Problem:** When no POS path works, the fallback returns `{"success":True,"method":"database"}` though nothing was dispatched (and it doesn't even persist — that's `on_call_complete`). `dispatch_order_if_ready` marks the order COMPLETED on `success:True`; the failure `else` branch is effectively dead (fallback always "succeeds"). No restaurant alert/SMS/alarm, no real retry. The AI verbally confirms the order to the customer *before* dispatch.
**Risk:** For every demo account (no live POS), each order is silently lost while the customer is told it's confirmed. Same shape will bite any restaurant whose POS call fails.
**Fix:** Distinguish the fallback from a real dispatch; fire a loud restaurant alert (SMS to escalation # + dashboard) on non-dispatch; qualify the AI confirmation when there's no working dispatch path; add real retry/backoff; reconsider auto-COMPLETED. Mirror the reservation-unavailable SMS pattern that already exists in `call_pipeline.py`.

### 🔴 A7-2 — POS "success" ≠ kitchen ticket fired
**Where:** `gemini_service.py` `_send_to_clover:587`, `_send_to_square:752`.
**Problem:** Both create an order + line items and return success, but **Clover never fires the order** (it sits as an unfired draft) and **Square has no `fulfillment` object** (won't route to the KDS / kitchen printer).
**Risk:** Even with a "working" POS integration, the kitchen may never see the ticket — order silently not made.
**Fix:** Physical kitchen-print test per POS; likely an extra fire/fulfillment API call (Clover order fire; Square `fulfillment`). Toast path lives in `toast_integration.py` (B-series).

---

## Detail — Medium

### `server.py`
- **A1-3** — `get_current_user` (`:1043–1057`) does a Mongo read+write on every request. Upsert only when missing/changed; skip the write on the hot path.
- **A2-1** — Rate limiting on 6 of 95 routes (`LIMIT_*` mostly unused). Apply to public menu (by IP), bootstrap/auth, all writes, POS/billing. (In-process → fully effective only at 1 instance.)
- **A2-2** — Public menu page (`:1367`) unauth + 5 collection `find_one`s/hit. IP rate-limit + optional cache. (XSS-safe.)
- **A2-3** — `detail=str(e)` 4× leaks internal exceptions. Generic 500, log detail to Sentry.
- **A3-2** — Reservation availability check then insert not atomic (`:1990`). Unique index / atomic conditional insert.
- **A4-1** — WS connection-limit funcs imported (`:292–294`) but never called; media-stream WS (most expensive) uncapped. Call check/register/unregister at accept + in `finally`.
- **A4-2** — Media-stream WS (`:4447`): authz rests only on the start message's `call_control_id` matching `active_calls`; no handshake signature/token; duplicate streams not rejected. Add a short-lived signed token in the stream URL; reject duplicate `call_sid` streams. (Shares auth pattern with A6-2.)
- **A5-1** — Overage billing + count increment (`:4579–4600`) no idempotency guard. **Mitigated** by `_fire_on_call_complete` fire-once (A8), but add `idempotency_key=f"overage:{call_sid}"` as defense-in-depth.
- **A5-2** — Overage decision reads a stale pre-fetched count (`:4586`). Use `find_one_and_update(..., return_document=AFTER)`.
- **A5-3** — Square OAuth callback (`:5044–5064`) stores the raw `auth_code` and sets `square_connected=True` but never exchanges it for a token → integration likely non-functional. Exchange + store encrypted token. (Verify in `pos_sync.py`, B-series.)
- **A6-1** — `send_menu_sms_endpoint` (`:3840`) doesn't enforce membership → SMS cost abuse + spoofing. Use `ensure_restaurant_access`.
- **A1-4** — Migration runs on every startup (`:382–411`). One-off script then remove the hook (appointment-todo #1).
- **A2-8 / A3-3** — Double restaurant+membership lookup on most `restaurant_id` routes. Have `ensure_restaurant_access` return `(restaurant, membership)` — fixes the class at once.

### `gemini_service.py`
- **A7-3** — Clover line-item failures swallowed (`:618–619` logs a warning, continues, returns `success:True`) → an empty/partial order reported as success. Treat line-item failure as order failure (or surface it).
- **A7-6** — **Modifier upcharges ignored everywhere.** `ModifierOption.price_delta` (`server.py:784`) exists but is dropped: the `compute_order_total` tool schema (`call_pipeline.py:151`) accepts only `name`+`quantity` (no modifiers), and `OrderItem.subtotal` = `unit_price×qty`. Paid modifiers are free across the spoken quote, SMS, prepayment, and POS. Add a `modifiers` field to the tool schema + handler; resolve `price_delta` and add `delta×qty` in both `compute_order_total` and `OrderItem.subtotal`.
- **A7-8** — `extract_order_from_transcript` truncates the transcript to the first 4000 chars (`transcript_text[:4000]`) → on long calls the final confirmed order is cut off. (`analyse_call_transcript` correctly keeps the tail — inconsistent.) Use head+tail.
- **A7-9** — `MenuIndex.find` substring matching (`key in item_name or item_name in key`) returns an arbitrary first-dict-order match → wrong item+price (e.g. "water" → "Watermelon Juice"). Require unique/high-confidence matches. (Prompt's "use exact names" partly mitigates.)
- **A7-14** — Stored prompt-injection: `customer_profile.last_name` (from a prior caller's spoken name) is interpolated into the system-prompt greeting (`build_system_prompt`). Sanitize/delimit/length-cap CRM data before interpolation.
- **A7-15** — Prompt instructs that a hangup after readback is "treated as confirmed and proceed" → unconsented order dispatch. Don't auto-confirm on hangup, or flag the order for review instead.
- **A7-17** — `_mock_call_analysis` fabricates random quality scores (`randint 78–99`) + highlights when Gemini is unavailable, stored + shown as real analytics. Mark "analysis unavailable" instead.

### `call_pipeline.py`
- **A8-1 (confirmed active bug)** — `restaurant.get("pos_type", "").lower()` (`gemini_service.py` `send_order_to_kitchen:534`, `get_kitchen_queue_depth:653`) raises **TypeError** when `pos_type` is present-but-None: the `""` default only applies when the key is *absent*, so a salon doc with `pos_type: null` → `None.lower()`. This is the memory-flagged salon disconnect crash. Fix: `(restaurant.get("pos_type") or "").lower()`.
- **A8-2** — `on_disconnect` (`:1971`) runs the restaurant order-dispatch/extraction path for ALL business types → salon/clinic calls hit A8-1 and waste a Gemini extraction. Guard with `business_type == "restaurant"`. (A8-1 + A8-2 = the salon disconnect crash.)
- **A8-6** — Per-restaurant voice ignored: `create_call_pipeline` (`:1297`) takes a `voice` arg (from `config.voice_id`) but overwrites it with env `GEMINI_VOICE` (`:1318`); all calls use the same voice. The `voice_preview` picker doesn't affect live calls.
- **A8-7** — Appointment dispatch failures silent: `dispatch_booking` (`:1028`) returns `True` on partial/failure with no customer/business alert (A7-1 family). Verify `dispatch_appointment` internals (calendar write + SMS) in `appointment_service.py` (B-series).

---

## Detail — Low / polish

### `server.py`
- **A1-5** — `logging.basicConfig` at `:414` after Sentry init + import warnings → early INFO swallowed.
- **A2-4** — `select_restaurant` (`:1140`) orphaned (no decorator); redundant local `asyncio`/`HTMLResponse` imports.
- **A2-5** — `update_restaurant` (~`:1230`) pops a field then checks `if field in update_data` (unreachable).
- **A2-6** — "Powered by RingAI" on the customer-facing menu page (~`:1465`). Rebrand before launch.
- **A1-6** — FastAPI title "RingAI API" (`:357`) + root message (`:1108`). Cosmetic.
- **A2-7** — Sanitization uneven (`create_service` rigorous; menu/restaurant rely on Pydantic + output escaping).
- **A1-7** — All service modules hard-imported (`:258–356`); any import error crashes startup.
- **A4-3** — Call duration `len(transcript)*8` in `on_call_complete`. NOT billing (billing is per-call-count). Analytics inconsistent: `:4385` uses accurate `duration_seconds_actual`; `:2672/:2739/:2792` use the estimate.
- **A4-4** — Silent `except` on POS credential decryption (`:4511–4513`). Log to Sentry.
- **A5-4** — No explicit Stripe event-id dedup (`:4862`). Mitigated; add `event.id` dedup as defense-in-depth.
- **A5-5** — `refund_order` (`:5212`) leaks raw Stripe error, refunds before DB update, no idempotency key.
- **A5-6** — `$inc`/`$set` fan-out across all 5 collections (`:4580`, `:5063`) — 4 no-ops. Resolve `business_type` once.
- **A6-3** — `telnyx_get_order` (`:3824`) authed but not scoped to caller. Scope via the audit record's `restaurant_id`.
- **A6-4** — `test-mode/status` + `test-mode/scenarios` (`:5456`, `:5461`) unauthenticated. Require auth or disable in prod.
- **A6-5** — Square webhook signs over `str(request.url)` (`:5296`) → behind CF/Render scheme/host may mismatch. Ensure proxy headers (ties to A6-7).
- **A6-6 / A6-7 / A6-8** — Stale `ringai-v2.onrender.com` host (see A7-18); verify uvicorn `--proxy-headers`; `client_ip` from spoofable `CF-Connecting-IP` if `CF_SECRET_TOKEN` unset.

### `gemini_service.py`
- **A7-7** — Unmatched items dropped from the order, but the customer **is** notified via the confirmation SMS ("we don't have X"). Gaps: restaurant not alerted; `dropped_items` omitted from `to_dict()`. (Revised down from Med.)
- **A7-10** — `detect_call_signals` (`:505`) natural-language phrase matching ("order is confirmed/placed") → false-trigger or miss on phrasing drift. **Systemic** (see A8 closing note).
- **A7-12** — `calculate_is_open` (`:910`) fails OPEN on missing/invalid hours/errors → AI takes orders when closed.
- **A7-16** — "CALL_END" token in the prompt isn't detected by `detect_call_signals` (works via farewell phrase; token is dead).
- **A7-4** — "RingAI" branding in the Clover note + Square `source.name`.
- **A7-5** — Internal cost analytics use stale Twilio rates ($0.0085/min, $0.0083/SMS; TODOs to update to Telnyx ~$0.0046/~$0.0040) → ~2× overestimate (admin-only).
- **A7-11** — Non-numeric quantity crashes extraction (unwrapped `int()`).
- **A7-13** — Misplaced docstring; `get_kitchen_queue_depth` code duplication; outbound kitchen webhook unsigned.
- **A7-18** — Stale `ringai-v2.onrender.com` hardcoded in 3 spots — call.answered/gather WS-URL fallback (`server.py:4210,4250`), `send_menu_sms` default `base_url`, on_ai_transcript menu-SMS (`call_pipeline.py:1378`). Customer menu links → dead/old domain. Use `get_backend_public_url()` / `duuutah.com`.

### `call_pipeline.py`
- **A8-3** — Keyword order-type detection misfires on negations ("not delivery, pickup" → locks delivery); reconciled later by extraction.
- **A8-4** — Vestigial `_greeting_in_progress` attribute (set, never read after the VAD greeting lock was removed).
- **A8-5** — Stale `_create_initial_response` docstring (describes the old reactive greeting; actual behavior is proactive `__BEGIN_CALL__` on connect).
- **A8-8** — `send_menu_sms` lacks an idempotency key → duplicate menu texts if the AI repeats the trigger phrase.
- **A8-9** — `generate_twiml_stream_response` (`:2083`) likely dead code (Twilio-era TeXML; the live flow uses Telnyx Call Control) with Twilio-era `callSid` naming.

---

## Cross-cutting fix clusters (for the fix-dependency map)
- **WebSocket authz** → A4-2 + A6-2 (one auth pattern, both sockets).
- **Double restaurant+membership lookup** → A2-8 / A3-3 (one `ensure_restaurant_access` signature change fixes ~20 routes).
- **Rate-limit + connection-cap wiring** → A2-1 + A2-2 + A4-1.
- **Proxy-header / `request.url` trust** → A6-5 + A6-7.
- **Encrypt tokens at rest** → A3-1 reuses the existing POS-credential encryption.
- **`detail=str(e)` leak** → A2-3 + A5-5 (one error-handling helper).
- **Silent-dispatch-failure alerting** → A7-1 + A8-7 (mirror the reservation-unavailable SMS pattern that already exists).
- **Stale `ringai-v2.onrender.com` host** → A6-6 + A7-18 (3 locations).
- **Natural-language signal fragility** → A7-10 (systemic across `gemini_service` `detect_call_signals` + `call_pipeline` `on_ai_transcript` phrase lists).

---

## What's solid (carry forward — don't "fix" these)

### `server.py`
- **Tenancy sweep (all 95 routes): 71 enforce `ensure_restaurant_access`, 5 signature/state-verified webhooks/OAuth, 2 admin-gated, 8 self/public.** No unguarded tenant CRUD. By-item/by-group/by-service routes resolve the parent `restaurant_id` first (correct IDOR protection).
- `repair_membership` privilege-escalation hole already found + killed (HTTP 410, `:1127`).
- Clerk JWT verification (JWKS + issuer) correct; tenancy guard returns 404 not 403 (no existence leak).
- Public menu page XSS-safe (`html.escape` everywhere).
- **Telnyx webhooks verify ed25519 signature before processing, 403 on failure** (both handlers).
- **Stripe webhook**: signature verified, fails closed; order-prepayment idempotent.
- **Square webhook**: HMAC-SHA256 verified (constant-time), fails closed, **event-id dedup w/ 7-day TTL**.
- `refund_order`: tenancy double-scoped to `call_sid`+`restaurant_id`, status guards, correct Connect refund (`reverse_transfer`, `refund_application_fee`).
- POS credentials encrypted at rest + decrypted only at point of use.
- Zombie-call sweeper (force-hangup + cleanup >10 min); TTL indexes (webhook_events 7d, oauth_states); graceful SIGTERM drain.

### `gemini_service.py`
- Order totals come from the **canonical menu prices, not the LLM** (can't hallucinate a total — modulo A7-6); items validated against the menu (no invented items).
- Allergen protocol forbids "allergen-free"/"safe" guarantees; no-payment-over-phone rule; plan-gated prompt.
- `evaluate_call_quality` checks AI disclosure / readback / escalation; robust JSON parsing.
- `analyse_call_transcript` tail-truncates correctly + has an alias-learning loop; SMS idempotency keys (`order_confirm:{call_sid}`); dynamic ETA.

### `call_pipeline.py` (best-engineered file)
- **Silent-reservation-drop bug VERIFIED FIXED** — `_ensure_reservation_booked` uses double-checked locking (`_reservation_lock` + `_reservation_booked` re-check), is called idempotently from all 4 paths, and runs early in the teardown-protected window (the original bug relied on the racing `on_call_complete` tail).
- **`_fire_on_call_complete` is fire-once** (flag before the await) — mitigates A5-1 double-billing.
- **Warm-transfer state machine**: backgrounds slow analytics so the transfer isn't delayed, stops streaming (no idle billing), fallback watchdog, idempotent bridge/timeout handlers, and **refuses to transfer to the restaurant's own AI DID** (prevents an infinite forwarding loop).
- **Minimal AI tool surface** (only `check_availability` + `compute_order_total`, both read/compute) — all side-effects gated by `CallSession`, not AI tool calls.
- `_fn_in_progress` 3-layer guard prevents VAD from interrupting/cancelling an in-flight tool call; Gemini-stuck recovery in `handle_user_idle`.
- Anti-hallucination: `_fetch_availability` returns ALL slots; careful Gemini-3.1 transcription-quirk handling; plan-gated duration guard; timezone-aware booking-intent NLU; graceful env-gated ambient mixer; single idempotent end-of-call reservation-unavailable SMS.

---

## Sessions remaining
**Core call path complete** — `server.py` + `gemini_service.py` + `call_pipeline.py` (A1–A8).

**Next — B-series (service modules, ~20 files):**
- **B1 (suggested):** `toast_integration.py` (resolves A7-2 Toast kitchen-fire) + `encryption_utils.py` (resolves A3-1 calendar-token + the POS encryption picture).
- Then: `appointment_service.py` (A8-7 `dispatch_appointment` calendar/SMS failure surfacing + `build_appointment_prompt`), `pos_sync.py` / Square (A5-3 token exchange), `reservation_service.py` (slot-data consistency + `dispatch_reservation`), `security_utils` / `security_middleware`, `rate_limiting`, `oauth_state_service`, `auth_helpers`, `payment_service`, `eta_service`, `delivery_utils`, `scheduler_service`, `reminder_service`, `auto_learning_service`, `language_prompts`, `websocket_notifications`, `test_mode`.
- Then **C-series** (frontend C1–C6), **D-series** (tests/infra D1–D2).

**Top open launch risks:** the 6 blockers above — with POS/kitchen fulfillment (A7-1 / A7-2 / A8-7) and the OAuth + WebSocket authz cluster (A3-1 / A4-2 / A6-2) as the two highest-stakes themes to resolve before any live customer.
