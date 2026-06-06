# Duuutah AI — Audit Findings Log

Running log of issues found during the line-by-line `server.py` audit. Pairs with `AUDIT_LEDGER.md` (which tracks *coverage*); this tracks *issues*. Fixes are batched and flow through staging → prod; nothing here is fixed until marked ✔️.

**Repo:** `abhishek96405/RingAI` · audited at `ringai-deploy` HEAD
**Severity:** 🔴 High / launch-blocker · 🟡 Medium · 🟢 Low/polish
**Status:** ⬜ Open · 🔧 fix prompt issued · ✔️ merged

---

## Summary

| ID | Sev | Area | Issue | Status |
|---|---|---|---|---|
| A1-1 | 🔴 | CORS | Wildcard `["*"]` + credentials fallback; secure helper unused | ⬜ |
| A3-1 | 🔴 | OAuth | Google Calendar callback: no `state` validation (CSRF) + unauth token write + plaintext tokens | ⬜ |
| A1-2 | 🔴 | Ops | No `/health` endpoint (breaks Render health check + no readiness probe) | ⬜ |
| A1-3 | 🟡 | Perf/Resilience | `get_current_user` does a Mongo read+write on every request | ⬜ |
| A2-1 | 🟡 | Security | Rate limiting applied to 6 of 93 routes | ⬜ |
| A2-2 | 🟡 | Security/Perf | Public menu page unthrottled + 6 DB queries/hit | ⬜ |
| A2-3 | 🟡 | Info leak | `detail=str(e)` returns raw exceptions to clients (4×) | ⬜ |
| A3-2 | 🟡 | Correctness | Reservation availability check + insert not atomic (double-booking race) | ⬜ |
| A1-4 | 🟡 | Tech debt | Data migration runs on every startup | ⬜ |
| A2-8 / A3-3 | 🟡 | Perf | Double restaurant+membership lookup per request (systemic) | ⬜ |
| A1-5 | 🟢 | Ops | `logging.basicConfig` after early log calls (Sentry "initialized" swallowed) | ⬜ |
| A2-4 | 🟢 | Dead code | `select_restaurant` orphaned (no decorator) + redundant local imports | ⬜ |
| A2-5 | 🟢 | Logic | Unreachable plan-gating branch in `update_restaurant` | ⬜ |
| A2-6 | 🟢 | Branding | "Powered by RingAI" on the **customer-facing** public menu page | ⬜ |
| A1-6 | 🟢 | Branding | "RingAI" in API title + root message | ⬜ |
| A2-7 | 🟢 | Consistency | Input sanitization applied unevenly (services rigorous, menu/restaurant lean on Pydantic) | ⬜ |
| A1-7 | 🟢 | Resilience | All service modules hard-imported → any import error crashes startup | ⬜ |

**Launch-blockers (must fix before launch):** A1-1, A3-1, A1-2.

---

## Detail

### 🔴 A1-1 — CORS wildcard + credentials; secure helper is dead code
**Where:** `server.py:369–377` (live middleware); `get_secure_cors_origins()` imported `:281`, `get_cors_origins()` `:178` — both unused.
**Problem:** Live config is `allow_origins = CORS_ORIGINS or ["*"]` with `allow_credentials=True`. Starlette, given `["*"]` + credentials, reflects any origin.
**Risk:** If `CORS_ORIGINS` is unset on Render, the API accepts any origin. (Calibrated: auth is Bearer-token not cookies, so not a one-click takeover, but it's a real hardening hole and removes CORS as a defense layer.)
**Fix:** Wire `get_secure_cors_origins()` in; remove the `"*"` default and the two dead functions. Immediately: confirm `CORS_ORIGINS` is set on prod Render.

### 🔴 A3-1 — Google Calendar OAuth callback: no state validation + unauthenticated token write
**Where:** callback `server.py:2265`, connect `:2238`. Contrast: Square callback `:5044`, Stripe Connect callback `:5104` both call `consume_oauth_state(...)`.
**Problem:** Google callback takes `state` as the raw `restaurant_id`, never validates it, has no auth, and upserts `google_calendar_tokens` into that restaurant's config.
**Risk:** Attacker completes Google OAuth for their own account, calls the callback with `state=<victim_restaurant_id>` → their tokens are written to the victim's restaurant → the victim's AI books customer appointments into the attacker's calendar (cross-tenant customer-data exposure). Tokens (incl. `refresh_token`) also stored plaintext.
**Fix:** Mirror Square/Stripe — `issue_oauth_state(restaurant_id, user_id)` in connect, `consume_oauth_state(state, provider="google_calendar")` in callback; encrypt tokens at rest. Mechanism already exists in the codebase.

### 🔴 A1-2 — No `/health` endpoint
**Where:** `/health` referenced in `CF_BYPASS_PREFIXES:5647` and by Render health checks, but never defined. Only `/api/` (root, `:1108`) returns 200.
**Problem/Risk:** A Render health check on `/health` 404s → instance flagged unhealthy / restart loop. No real liveness/readiness probe.
**Fix:** Immediate: set Render Health Check Path to `/api/`. Better: add a `/health` endpoint with a Mongo ping (readiness).

### 🟡 A1-3 — `get_current_user` writes to Mongo on every request
**Where:** `server.py:1043–1057`.
**Problem:** Dependency on ~every route; each call does `find_one` + `update_one`/`insert_one`, rewriting the profile + `updated_at` every request.
**Risk:** 2 extra Mongo ops on every API call (latency/cost on M0); couples all auth to DB availability.
**Fix:** Upsert only when the user doc is missing or a field actually changed; skip the write on the hot path.

### 🟡 A2-1 — Rate limiting applied to 6 of 93 routes
**Where:** 6 `@limiter.limit` decorators total; constants `LIMIT_AUTH` etc. imported but mostly unused.
**Risk:** Brute-force/scraping/cost-abuse on ~87 unthrottled routes, hardest on M0.
**Fix:** Apply the decorators you already have constants for — prioritize public menu page (by IP), bootstrap/auth, all writes, POS/billing. (Limiter is in-process → only fully effective at 1 instance.)

### 🟡 A2-2 — Public menu page unthrottled + DB-heavy
**Where:** `server.py:1367` (`/menu/{restaurant_id}`).
**Risk:** Public, unauth, 5 collection `find_one`s + menu query per hit, no throttle → DB load/cost on M0.
**Fix:** IP rate limit + optional per-restaurant cache. *(Positive: XSS-safe, no sensitive fields exposed.)*

### 🟡 A2-3 — Internal exception text leaked to clients
**Where:** `detail=str(e)` 4× (incl. `voice_preview` ~`:1361`).
**Risk:** Info disclosure (paths, dependency errors, possibly secrets in error strings).
**Fix:** Generic 500 message; log the detail (Sentry captures it).

### 🟡 A3-2 — Reservation double-booking race
**Where:** `server.py:1990` (`create_reservation`).
**Problem/Risk:** Availability check then insert is not atomic → concurrent requests can double-book the last slot.
**Fix:** Unique index on the slot key, or atomic conditional insert/`find_one_and_update`.

### 🟡 A1-4 — Migration runs on every startup
**Where:** `server.py:382–411` (`migrate_businesses_to_typed_collections`).
**Fix:** Convert to a one-off script run once, then remove the hook (or gate behind a flag). Ties to appointment-todo #1.

### 🟡 A2-8 / A3-3 — Double restaurant+membership lookup (systemic)
**Where:** most routes that take `restaurant_id` (e.g. `:1218`, `:1281`, `:1293`, `:1990`, `:2082`, `:2319`).
**Problem:** Call `ensure_restaurant_access` (fetches membership + restaurant), then re-fetch both for `business_type`.
**Fix:** Have `ensure_restaurant_access` return `(restaurant, membership/business_type)`; fixes the whole class at once.

### 🟢 Low / polish
- **A1-5** — `logging.basicConfig` at `:414` runs after the Sentry init + import warnings → early INFO logs swallowed. Configure logging at the top.
- **A2-4** — `select_restaurant` (`:1140`) orphaned (no route decorator), never called; remove. Plus redundant local `asyncio`/`HTMLResponse` imports.
- **A2-5** — `update_restaurant` (~`:1230`) `pop`s a field then checks `if field in update_data` (unreachable). Same for reservations. Clean up.
- **A2-6** — "Powered by RingAI" on the customer-facing public menu page (~`:1465`). Higher priority than internal branding — real diners see it.
- **A1-6** — FastAPI title "RingAI API" (`:357`) + root message (`:1108`). Cosmetic.
- **A2-7** — Sanitization uneven: `create_service` rigorous (`sanitize_string` + bounds); menu/restaurant rely on Pydantic + output escaping. Standardize.
- **A1-7** — All service modules hard-imported (`:258–356`); any import error crashes startup (the cascading-import class). Keep in mind when editing those modules.

---

## What's solid (carry forward — don't "fix" these)
- Tenancy enforced on **every** data route via `ensure_restaurant_access`, including by-item/by-group/by-service routes that resolve the parent `restaurant_id` first (correct IDOR protection).
- `repair_membership` privilege-escalation hole already found + killed (HTTP 410, `:1127`).
- Clerk JWT verification (JWKS + issuer) is correct; tenancy guard returns 404 not 403 to avoid existence leaks.
- Public menu page is XSS-safe (`html.escape` everywhere); exposes no sensitive fields.
- Reservation routes: availability checked before insert, inputs sanitized, pagination bounded, rate-limited.
- Square + Stripe Connect OAuth state validation done correctly.
- Webhook signature verification (Stripe/Square/Telnyx) confirmed in the launch-critical pass.
- Sentry monitoring live on backend + frontend.

---

## Sessions remaining
A4 (Telnyx + call webhooks + media stream) · A5 (Stripe/Square/POS webhooks + billing) · A6 (admin/analytics + full 95-route tenancy sweep) · A7–A10 (gemini_service, call_pipeline — incl. the silent-reservation-drop + kitchen dispatch) · B1–B4 (services) · C1–C6 (frontend) · D1–D2 (tests/infra).
