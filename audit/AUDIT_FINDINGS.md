# Duuutah AI — Audit Findings Log

Running log of issues found during the line-by-line `server.py` audit. Pairs with `AUDIT_LEDGER.md` (which tracks *coverage*); this tracks *issues*. Fixes are batched and flow through staging → prod; nothing here is fixed until marked ✔️.

**Repo:** `abhishek96405/RingAI` · audited at `ringai-deploy` HEAD
**Scope of this version:** `server.py` complete (A1–A6, all 95 routes).
**Severity:** 🔴 High / launch-blocker · 🟡 Medium · 🟢 Low/polish
**Status:** ⬜ Open · 🔧 fix prompt issued · ✔️ merged

---

## Summary

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
| A5-1 | 🟡 | Billing | Overage billing + call-count increment have no idempotency guard | ⬜ |
| A5-2 | 🟡 | Billing | Overage decision reads a stale pre-fetched call count | ⬜ |
| A5-3 | 🟡 | Functional | Square OAuth callback stores raw auth code, never exchanges it for a token | ⬜ |
| A6-1 | 🟡 | Access control | `send_menu_sms_endpoint` doesn't enforce membership → SMS abuse/spoofing | ⬜ |
| A1-4 | 🟡 | Tech debt | Data migration runs on every startup | ⬜ |
| A2-8 / A3-3 | 🟡 | Perf | Double restaurant+membership lookup per request (systemic) | ⬜ |
| A1-5 | 🟢 | Ops | `logging.basicConfig` after early log calls (Sentry "initialized" swallowed) | ⬜ |
| A2-4 | 🟢 | Dead code | `select_restaurant` orphaned (no decorator) + redundant local imports | ⬜ |
| A2-5 | 🟢 | Logic | Unreachable plan-gating branch in `update_restaurant` | ⬜ |
| A2-6 | 🟢 | Branding | "Powered by RingAI" on the **customer-facing** public menu page | ⬜ |
| A1-6 | 🟢 | Branding | "RingAI" in API title + root message | ⬜ |
| A2-7 | 🟢 | Consistency | Input sanitization applied unevenly | ⬜ |
| A1-7 | 🟢 | Resilience | All service modules hard-imported → any import error crashes startup | ⬜ |
| A4-3 | 🟢 | Analytics | Call duration estimated `len(transcript)*8`; inconsistent with `duration_seconds_actual` (NOT a billing issue) | ⬜ |
| A4-4 | 🟢 | Observability | Silent `except` on POS credential decryption | ⬜ |
| A5-4 | 🟢 | Billing | No explicit Stripe event-id dedup (mitigated; handlers idempotent) | ⬜ |
| A5-5 | 🟢 | Billing | `refund_order` leaks raw Stripe error + Stripe-before-DB ordering + no idempotency key | ⬜ |
| A5-6 | 🟢 | Perf | `$inc`/`$set` fan-out across all 5 collections for one restaurant_id | ⬜ |
| A6-3 | 🟢 | Access control | `telnyx_get_order` authed but not scoped to caller | ⬜ |
| A6-4 | 🟢 | Security | `test-mode/status` + `test-mode/scenarios` unauthenticated | ⬜ |
| A6-5 | 🟢 | Webhook | Square webhook signs over `str(request.url)` — proxy scheme/host mismatch risk | ⬜ |

**Launch-blockers (must fix before launch):** A1-1 (CORS) · A1-2 (`/health`) · A3-1 (Google OAuth CSRF) · A6-2 (notifications WS).

**Systemic theme:** REST authorization is rigorous (71/95 routes enforce `ensure_restaurant_access`; no unguarded tenant CRUD). The real gaps cluster in (1) CORS config, (2) OAuth + **WebSocket** authorization, (3) unwired rate-limit / connection-cap infrastructure.

---

## Detail — High

### 🔴 A1-1 — CORS wildcard + credentials; secure helper is dead code
**Where:** `server.py:369–377`; `get_secure_cors_origins()` imported `:281`, `get_cors_origins()` `:178` — unused.
**Problem:** Live config is `allow_origins = CORS_ORIGINS or ["*"]` with `allow_credentials=True`; Starlette reflects any origin.
**Risk:** If `CORS_ORIGINS` unset on Render, API accepts any origin. (Bearer-token auth, not cookies, lowers severity — but fails review + removes a defense layer.)
**Fix:** Wire `get_secure_cors_origins()`; drop the `"*"` default + dead functions. Confirm `CORS_ORIGINS` set on prod.

### 🔴 A3-1 — Google Calendar OAuth callback: no state validation + unauth token write
**Where:** callback `:2265`, connect `:2238`. Contrast Square `:5044` / Stripe Connect `:5104` (both call `consume_oauth_state`).
**Problem:** Google callback takes `state` as the raw `restaurant_id`, never validates it, no auth, upserts `google_calendar_tokens` into that restaurant.
**Risk:** Attacker completes Google OAuth for their own account, calls callback with `state=<victim_id>` → their tokens written to the victim restaurant → victim's AI books customer appointments into the attacker's calendar. Tokens (incl. `refresh_token`) stored plaintext.
**Fix:** Mirror Square/Stripe — `issue_oauth_state`/`consume_oauth_state`; encrypt tokens at rest (POS creds already are — copy that).

### 🔴 A6-2 — `/ws/notifications` unauthenticated + unauthorized
**Where:** `server.py:5674`.
**Problem:** `manager.connect(websocket, restaurant_id)` with no token check, no membership check. Any client may subscribe with `?restaurant_id=<id>`.
**Risk:** Streams real-time new-order (with totals), new-call, and appointment events. `restaurant_id` is public (exposed in `/menu/{restaurant_id}`), so anyone with a restaurant's menu link can watch its live activity. Cross-tenant live-data leak.
**Fix:** Authenticate the WS (Clerk token via query/subprotocol) + verify membership for `restaurant_id` before connect; reject otherwise.

### 🔴 A1-2 — No `/health` endpoint
**Where:** referenced in `CF_BYPASS_PREFIXES:5647` + Render health checks, never defined. Only `/api/` (`:1108`) returns 200.
**Risk:** Render health check on `/health` 404s → instance flagged unhealthy / restart loop; no real readiness probe.
**Fix:** Immediate: set Render Health Check Path to `/api/`. Better: add `/health` with a Mongo ping.

---

## Detail — Medium

### 🟡 A1-3 — `get_current_user` writes to Mongo every request
**Where:** `:1043–1057`. Read+write (`find_one` + `update_one`/`insert_one`) per request, on ~every route.
**Risk:** 2 Mongo ops on every call (latency/cost on M0); couples all auth to DB availability.
**Fix:** Upsert only when the doc is missing or a field changed; skip the write on the hot path.

### 🟡 A2-1 — Rate limiting on 6 of 95 routes
**Where:** 6 `@limiter.limit` decorators; `LIMIT_*` constants mostly unused.
**Fix:** Apply to public menu page (by IP), bootstrap/auth, all writes, POS/billing. (In-process limiter → fully effective only at 1 instance.)

### 🟡 A2-2 — Public menu page unthrottled + DB-heavy
**Where:** `:1367`. Public, unauth, 5 collection `find_one`s + menu query/hit. *Fix:* IP rate limit + optional cache. (XSS-safe, no sensitive fields.)

### 🟡 A2-3 — Internal exception text leaked
**Where:** `detail=str(e)` 4× (incl. `voice_preview ~:1361`, `refund_order`). *Fix:* generic 500, log detail (Sentry).

### 🟡 A3-2 — Reservation double-booking race
**Where:** `:1990`. Availability check then insert not atomic. *Fix:* unique index / atomic conditional insert.

### 🟡 A4-1 — WS connection limit imported but never enforced
**Where:** imported `:292–294`, never called. Media-stream WS (most expensive — spawns Gemini Live + Pipecat) has no cap.
**Risk:** Resource-exhaustion + runaway cost. *Fix:* call check/register/unregister at accept + in `finally`.

### 🟡 A4-2 — Media-stream WS: no transport auth + no duplicate-stream guard
**Where:** `:4447`. Authz rests only on the start message's `call_control_id` matching an `active_calls` row; no signature/token on the handshake; duplicate streams for one `call_sid` not rejected.
**Risk:** Anyone who learns a live `call_control_id` (appears in logs/webhooks) could inject/extract audio or attach a duplicate stream.
**Fix:** Short-lived signed token in the stream URL (+ optional Telnyx source-IP check); reject duplicate streams for an active `call_sid`.

### 🟡 A5-1 — Overage billing + call-count increment: no idempotency guard
**Where:** `:4579–4600`. `$inc` + `stripe.InvoiceItem.create` run unconditionally per `on_call_complete`; no per-`call_sid` flag, no Stripe `idempotency_key`.
**Risk:** If `on_call_complete` fires twice for one call → double-count + double-charge.
**Fix:** Gate on a billed-flag per `call_sid`; `idempotency_key=f"overage:{call_sid}"`.

### 🟡 A5-2 — Overage decision reads a stale call count
**Where:** `:4586`. `_new_count` from the snapshot stashed at call start, not the atomic post-`$inc` value.
**Risk:** Concurrent calls for one restaurant → wrong overage trigger / wrong "call #N".
**Fix:** `find_one_and_update(..., return_document=AFTER)`; decide off the true count.

### 🟡 A5-3 — Square OAuth callback stores raw auth code, never exchanges it
**Where:** `:5044–5064`. Validates state, stores `auth_code` + sets `square_connected=True`, but no token exchange (unlike Google's `exchange_code_for_tokens`).
**Risk:** Square auth codes are single-use/short-lived → integration likely can't call Square APIs despite "connected." (Demo/pre-launch.)
**Fix:** Verify against the Square service; exchange the code and store the (encrypted) access token.

### 🟡 A6-1 — `send_menu_sms_endpoint` doesn't enforce membership
**Where:** `:3840`. Fetches membership only for `business_type`; no `if not membership: raise`.
**Risk:** Any authed user sends a menu SMS for any restaurant to any number → SMS cost abuse + spoofing/phishing.
**Fix:** Replace with `await ensure_restaurant_access(restaurant_id, user)`.

### 🟡 A1-4 — Migration runs on every startup
**Where:** `:382–411`. *Fix:* one-off script, then remove the hook (ties to appointment-todo #1).

### 🟡 A2-8 / A3-3 — Double restaurant+membership lookup (systemic)
**Where:** most routes taking `restaurant_id` (`:1218`, `:1281`, `:1293`, `:1990`, `:2082`, `:2319`, `:3845`).
**Fix:** Have `ensure_restaurant_access` return `(restaurant, membership)`; fixes the class at once.

---

## Detail — Low / polish
- **A1-5** — `logging.basicConfig` at `:414` after Sentry init + import warnings → early INFO swallowed. Configure logging at the top.
- **A2-4** — `select_restaurant` (`:1140`) orphaned (no decorator), never called; remove. Redundant local `asyncio`/`HTMLResponse` imports.
- **A2-5** — `update_restaurant` (~`:1230`) pops a field then checks `if field in update_data` (unreachable). Clean up.
- **A2-6** — "Powered by RingAI" on the customer-facing menu page (~`:1465`). Real diners see it — rebrand first.
- **A1-6** — FastAPI title "RingAI API" (`:357`) + root message (`:1108`). Cosmetic.
- **A2-7** — Sanitization uneven (`create_service` rigorous; menu/restaurant rely on Pydantic + output escaping). Standardize.
- **A1-7** — All service modules hard-imported (`:258–356`); any import error crashes startup.
- **A4-3** — Call duration `len(transcript)*8` (in `on_call_complete`). NOT a billing issue (billing is per-call-count). Analytics inconsistent: `:4385` uses accurate `duration_seconds_actual`; `:2672/:2739/:2792` use the estimate. Standardize on `duration_seconds_actual`.
- **A4-4** — Silent `except` on POS credential decryption (`:4511–4513`). Log it (Sentry).
- **A5-4** — No explicit Stripe event-id dedup (`:4862`). Mitigated (set-based updates + SMS idempotency key + paid-update guarded vs un-refund). Add `event.id` dedup as defense-in-depth.
- **A5-5** — `refund_order` (`:5212`) leaks raw Stripe error, refunds before DB update, no idempotency key.
- **A5-6** — `$inc`/`$set` fan-out across all 5 collections (`:4580`, `:5063`) — 4 no-ops. Resolve `business_type` once.
- **A6-3** — `telnyx_get_order` (`:3824`) authed but not scoped to caller. Scope via audit record's `restaurant_id`.
- **A6-4** — `test-mode/status` + `test-mode/scenarios` (`:5456`, `:5461`) unauthenticated. Require auth or disable in prod. (`run-scenario` guarded.)
- **A6-5** — Square webhook signs over `str(request.url)` (`:5296`) → behind CF/Render the scheme/host may mismatch what Square signed. Ensure proxy headers.

---

## What's solid (carry forward — don't "fix" these)
- **Tenancy sweep (all 95 routes): 71 enforce `ensure_restaurant_access`, 5 signature/state-verified webhooks/OAuth, 2 admin-gated, 8 self/public.** No unguarded tenant CRUD route. By-item/by-group/by-service routes resolve the parent `restaurant_id` first (correct IDOR protection).
- `repair_membership` privilege-escalation hole already found + killed (HTTP 410, `:1127`).
- Clerk JWT verification (JWKS + issuer) correct; tenancy guard returns 404 not 403 to avoid existence leaks.
- Public menu page XSS-safe (`html.escape` everywhere); no sensitive fields exposed.
- Reservation routes: availability checked before insert, inputs sanitized, pagination bounded, rate-limited.
- **Telnyx webhooks verify ed25519 signature before processing, 403 on failure** (both handlers).
- **Stripe webhook**: signature verified, fails closed; order-prepayment idempotent (paid-update guarded vs un-refund; SMS idempotency key).
- **Square webhook**: HMAC-SHA256 verified (constant-time), fails closed (503/401), **event-id dedup w/ 7-day TTL**.
- **`refund_order`**: tenancy enforced, order double-scoped to `call_sid`+`restaurant_id`, status guards, correct Connect refund (`reverse_transfer`, `refund_application_fee`).
- POS credentials encrypted at rest + decrypted only at point of use in the call.
- Media-stream WS: pre-fetch design (zero DB latency at stream start), proper `finally` cleanup, idempotent multi-path reservation booking (`_ensure_reservation_booked`), "closed → dispatch blocked" guard.
- Sentry monitoring live on backend + frontend.

---

## Sessions remaining
**`server.py` complete.** Next: A7–A10 (`gemini_service.py`, `call_pipeline.py` — incl. the **POS kitchen-dispatch P0-2/P0-3**, the silent-reservation-drop verification, upsell behavior) · B1–B4 (`reservation_service`, `encryption_utils`, `telnyx_service`, `calendar_service`, `toast_integration`, `pos_sync`, `rate_limiting`, `security_*`) · C1–C6 (frontend) · D1–D2 (tests/infra).

**Top non-server.py launch risk still open:** POS kitchen dispatch — `send_order_to_kitchen` may create a POS order without firing a kitchen ticket, and a DB-only fallback may return `success:true` silently. First priority in A7.
