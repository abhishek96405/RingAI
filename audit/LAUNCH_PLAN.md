# Duuutah AI — Master Launch Plan (Restaurant Vertical)

**Repo:** `abhishek96405/RingAI` · plan baselined at `ringai-deploy` HEAD `a52ee4ed` (June 10, 2026)
**Goal:** First paying restaurant live, with no silent-failure or security exposure, in ~10 working days.
**Verticals at launch:** Restaurants only. Salons = second pass (post-launch). Clinics / home services / legal = hidden.
**Workflow:** Claude (architect/reviewer) writes Claude Code prompts → Abhishek executes → diffs/test output reviewed → merge. Every PR: branch off `ringai-deploy` → full pytest → deploy to `duuutah-staging` → verify → merge → Render auto-deploy → prod smoke.
**Acceptance harness:** the xfail-strict test suite. Each fix deletes its xfail marker; suite must go red→green as objective proof. Zero new failures vs. the 17-failure OAuth baseline.

---

## Verification status (re-audited June 10, 2026 at HEAD a52ee4ed)

| ID | Finding | Status |
|---|---|---|
| A1-1 | CORS wildcard default + credentials (`server.py:366`) | 🔴 confirmed open |
| A1-2 | No `/health` route; CF middleware whitelists nonexistent path | 🔴 confirmed open |
| A3-1 | Calendar OAuth callback: raw `restaurant_id` as state, no validation/auth (`server.py:2272`) | 🔴 confirmed open |
| A6-2 | `/ws/notifications` unauthenticated, streams PII (`server.py:5681`) | 🔴 confirmed open |
| A7-1 | Order dispatch failure → still COMPLETED + DB fallback returns `success:True` | 🔴 confirmed open |
| A7-2 | Square order created with no `fulfillments` (invisible in dashboard/KDS); Clover no print event | 🔴 confirmed open |
| D3-1 | Escalation transfer broken (undefined `settings`) | ✔️ **resolved** — verified robust at HEAD |
| D3-3 | `plan-features` endpoint: `payload.restaurant_id` NameError → 500 always (`server.py:4865`) | 🔴 confirmed |
| D3-4 | `except httpx.HTTPStatusError` with no module-level import → 500 on Telnyx error paths (3593/3667/3764) | 🔴 confirmed |
| D3-6 | `create_reservation` returns mutated doc with ObjectId → 500 on every success (`server.py:2065`) | 🔴 confirmed |
| NEW-1 | `GEMINI_MODEL` env var double-duty: live default in `call_pipeline.py:1317`, text default in `server.py:5388` | 🟡 new finding |
| NEW-2 | Cost constants stale: `cost_gemini_live = 0.0 # free preview`; extraction priced at 2.0-Flash-era $0.075/$0.30 | 🟡 new finding |
| NEW-3 | Extraction model hardcoded in 2 places (`gemini_service.py:124`, `appointment_service.py:625`) | 🟡 new finding |
| NEW-4 | `AUDIT_FINDINGS.md` / `FIX_PLAN.md` never committed to any branch | 🟢 process |

All other A/B/C/D-series findings from the consolidated audit remain as logged; this plan sequences them below.

---

## Phase 0 — Setup & ground rules (Day 0, ~1 hour)

- **0.1** Commit `AUDIT_FINDINGS.md`, `FIX_PLAN.md`, and this `LAUNCH_PLAN.md` to `ringai-deploy` so the source of truth is in git, not on one laptop.
- **0.2** Feature freeze: no new features until Phase 4 completes. Bug-fix branches only.
- **0.3** Confirm `duuutah-staging` deploys from the `staging` branch and env overrides are intact (DB_NAME=duuutah_staging, Clerk dev, Stripe test, Square sandbox). Staging is the proving ground for every PR below.
- **0.4** Branch protection on `ringai-deploy`: require the CI test job to pass before merge (closes D1-1; stops deploy-on-push bypassing CI — D1-2).

---

## Phase 1 — Launch blockers (Days 1–4) — code lane

### PR-A · Order integrity (A7-1 + A7-2) — Day 1–2. The product's core promise.
1. `send_order_to_kitchen`: when `pos_type` is set and the POS dispatch fails, **do not** fall through to a `success:True` DB fallback. Return `{"success": False, "method": "<pos>", "fallback_saved": True}` after persisting the order for recovery.
2. `dispatch_order_if_ready`: on failure, transition to a new `DISPATCH_FAILED` order state (not COMPLETED). Surface in Orders tab with a red "Needs attention" badge.
3. Operator alert on failure: SMS to `escalation_phone_number` (or owner phone) + dashboard notification via the WS manager: "Order from <caller> could not be sent to <POS>. View in dashboard."
4. Square: add `fulfillments: [{type: "PICKUP", state: "PROPOSED", pickup_details: {...}}]` so orders appear in Square Dashboard/KDS and print. Verify in Square sandbox on staging.
5. Clover: after line items, POST a print event (`/v3/merchants/{mId}/print_event`) so the kitchen printer fires. Verify in Clover sandbox.
6. Delete xfails in `unit/test_gemini_service_pos_dispatch.py` + `voice/test_post_call_extraction_e2e.py`; suite green.
7. **Manual gate:** one real test call on staging per POS → ticket visibly appears in POS dashboard.

### PR-B · Security pair (A6-2 + A3-1) — Day 2–3.
1. A6-2: require a Clerk token on the `/ws/notifications` handshake (query param or first-message auth), verify token, and verify membership of the requested `restaurant_id` before `manager.connect`. Reject otherwise (4401 close).
2. A3-1: reuse `oauth_state_service.py` for Google Calendar — `/calendar/google/connect` issues a crypto-random single-use state bound to `restaurant_id` + user; callback validates and consumes it, 403 on mismatch. (Same pattern already merged for Square/Stripe in PR #5.)
3. While in there: encrypt Google tokens at rest with the existing encryption util (A3 follow-up) if not already.
4. Delete corresponding xfails (`integration/test_websocket_endpoints.py`, `integration/test_api_oauth_integrations.py`).

### PR-C · Config & ops surface (A1-1 + A1-2) — Day 3. Small.
1. CORS fail-safe: if `CORS_ORIGINS` unset → allow only `FRONTEND_URL`; never default `["*"]` with credentials. Log a startup warning if unset.
2. Add `GET /health` (no auth, no DB hit beyond a cheap ping, returns 200 + build info). Point Render health check at it. CF middleware whitelist now matches a real route.
3. Verify prod env: `CORS_ORIGINS` set to the real frontend origin(s).
4. Delete `security/test_cors_*` xfails.

### PR-D · Latent-500 batch (D3-2, D3-3, D3-4, D3-5, D3-6, D3-9) — Day 4. Mechanical.
1. D3-3: `payload.restaurant_id` → `restaurant_id` in `plan-features` (this also unblocks frontend plan gating, C7-1).
2. D3-4: module-level `import httpx` in `server.py`.
3. D3-6: `insert_one(doc.copy())` or strip `_id` before returning in `create_reservation`.
4. D3-2: fix `public_menu_page` UnboundLocalError on not-found → proper 404.
5. D3-5: `simulate_call` timedelta UnboundLocalError when reservations disabled.
6. D3-9: `run_test_scenario` undefined `call_sid` in salon branch + guard `config.get`.
7. Delete all six xfails; suite green.

**End of Phase 1 = the six original blockers closed.**

---

## Phase 2 — Launch-scope product cleanup (Days 4–6) — frontend lane

### PR-E · Verticals & multilingual scoping
1. Hide clinic / home services / legal everywhere user-facing: onboarding vertical picker, landing page references, dashboard branches. Hide via a `SUPPORTED_VERTICALS = ["restaurant", "salon"]` constant (frontend + backend) — do not delete code; salons stay visible (data work continues post-launch), the rest gated off.
2. Backend guard: onboarding/API rejects `business_type` outside the supported list (defense-in-depth so nothing can create a clinic doc).
3. Multilingual: dashboard toggle replaced with a disabled "Coming soon" state (it's already disabled — make the UI say so instead of looking broken). Remove/neutralize language-count claims on the landing page.
4. Salon-specific dashboard gaps (the 12 UI/UX items from the salon audit) are explicitly **post-launch** — restaurants first.

### PR-F · Frontend criticals from C-series
1. C12-6 plan-casing lockout: normalize plan comparisons (`.toUpperCase()` at one boundary) across the five affected components — Pro customers currently get locked out of paid features.
2. Billing-bypass via client-controlled query parameter: server-side enforcement only; remove the param trust.
3. Admin Clerk ID console leak: delete the `console.log` on render.
4. Service-worker/PWA: confirm the SW neutralization shipped June 5 holds (regression test exists).

---

## Phase 3 — Model & platform configuration (Days 6–8)

### PR-G · Model config split + cost truth
1. Split env vars: `GEMINI_LIVE_MODEL` (default `gemini-3.1-flash-live-preview`) and `GEMINI_EXTRACT_MODEL` (default `gemini-2.5-flash` until 3.1-lite A/B passes). `call_pipeline.py`, `gemini_service.py:124`, `appointment_service.py:625`, and the `/status` endpoint all read the right one. **GA-day swap for the live model becomes a Render env change + one staging smoke call.**
2. Cost constants → env-driven (`GEMINI_LIVE_COST_PER_MIN`, extract input/output rates) with current real prices; kill the `0.0 # free preview` hardcode.
3. TTS model string (`server.py:1348`) also env-driven.

### PR-H · Extraction → Gemini 3.1 Flash-Lite, A/B then flip
1. Staging A/B: run 20–30 archived real transcripts through extraction with `gemini-3.1-flash-lite` vs `gemini-2.5-flash`; compare item accuracy, totals, JSON validity.
2. Migration notes for the 3-series: pin thinking low (`reasoning_effort: "low"` via the OpenAI-compat param) — extraction needs no reasoning budget; and test `temperature` — Google advises keeping 1.0 on Gemini 3 models, your code uses 0.0. Whichever wins the A/B is what ships.
3. On pass: flip `GEMINI_EXTRACT_MODEL=gemini-3.1-flash-lite` (≈40% cheaper output, faster TTFT). On fail: stay on 2.5-flash, revisit post-launch.

### PR-I · Vertex AI strategy (decision encoded, partial migration now)
**Facts (verified June 10, 2026):** 3.1 Flash Live preview is AI-Studio-only — no Vertex availability. Vertex Live API is GA only with the 2.5 Flash native-audio model. Google Cloud SLAs cover GA offerings only; preview products are excluded. Pipecat 0.0.104 speaks API-key WebSocket to AI Studio; Vertex Live requires OAuth + different endpoint (a Pipecat change — last upgrade attempt broke audio and was reverted).
1. **Now:** move *extraction* to Vertex (3.1 Flash-Lite is on Vertex). Two implementation options — (a) Vertex OpenAI-compat endpoint with a `google-auth` token-refresh wrapper (keeps the openai SDK code), or (b) switch extraction calls to `google-genai` SDK with `vertexai=True`. Option (a) is the smaller diff. Service account JSON via Render env. Gets SLA + enterprise data handling on the text path.
2. **Voice stays on AI Studio paid tier** with 3.1 Flash Live preview at launch. Documented and deliberate: best quality, battle-tested in this stack, no SLA exists for it anywhere.
3. **Trigger to migrate voice:** the day 3.1 Flash Live reaches GA on Vertex → spike branch, staging smoke calls, flip. If a customer contract requires a voice SLA before then, the fallback is Vertex + 2.5 native audio GA (accept quality regression + Pipecat auth work — scope as its own project).
4. Honesty note: product uptime is bounded by single-instance Render + Atlas tier, not the model SLA. See Phase 5.

---

## Phase 4 — Hardening batch (Days 8–9)

### PR-J · Webhooks & reliability
1. D3-13: Stripe webhook event-id dedup (reuse the `webhook_events` TTL collection Square already uses) — stops duplicate payment SMS on replay.
2. D3-12 / D3-14 / D3-15: Stripe missing `data.object` → 400 not 500; reject future-timestamp signatures; Square non-dict signed body → 400.
3. D3-7: `classify_booking_intent` — match "day after tomorrow" before "tomorrow".
4. D3-8: reset `_order_dispatched` on extraction failure so retry within the call works (pairs with PR-A).

### PR-K · Database & scale floor
1. Create indexes (idempotent startup or migration script): `calls(restaurant_id, created_at)`, `orders(restaurant_id, created_at)`, `reservations(restaurant_id, reservation_date)`, `memberships(user_id, restaurant_id)`, `sms_messages(call_sid)`, plus the existing TTL indexes.
2. Keep Render at **1 instance** until the in-process rate limiter and scheduler lock are made multi-instance-safe (post-launch item) — document this constraint in the README.
3. D2: add `--cov-fail-under` floor + ruff lint job to CI (cheap, prevents regression of exactly the D3 bug class).

---

## Phase 5 — Non-code lanes (run in PARALLEL with Phases 1–4)

### Legal / marketing (blocks Stripe live mode — start Day 1)
1. Remove: SOC 2 claim, fabricated testimonials, fake stats (5,000+ businesses / 2.5M calls / 4.9 rating), unbuilt integrations (OpenTable, Resy, Toast, Yelp), unsupported verticals.
2. Keep only real integrations: Square, Clover, Twilio/Telnyx, Stripe, Google Calendar.
3. Publish Terms of Service + Privacy Policy pages (required for Stripe live mode). Add AI-disclosure language for calls (several US states require it; the prompt already discloses — keep it that way).
4. Pricing page matches actual Stripe products/tiers.

### Ops go-live (Days 7–10)
1. MongoDB Atlas: M0 → paid tier (M10) + continuous backups enabled. **Non-negotiable before real customer data.**
2. Stripe live mode: legal pages published, business details, live keys to Render, distinct `STRIPE_PRICE_STARTER`/`STRIPE_PRICE_PRO`, webhook endpoint re-registered with live signing secret.
3. Clerk production instance: prod keys, sign-in/up flows, email templates, custom domain.
4. Render env audit: `CORS_ORIGINS`, `GEMINI_LIVE_MODEL`, `GEMINI_EXTRACT_MODEL`, cost vars, `ADMIN_USER_ID`, encryption key, Telnyx/Google/Square creds, Sentry DSN (already wired), `CF_SECRET_TOKEN`.
5. Telnyx: 10DLC campaign active (done), number auto-assignment verified.
6. Sentry: confirm events arrive from prod backend + frontend; set alert rule on error spike.

---

## Launch gate — go/no-go checklist (Day 10)

Go requires ALL of:
- [ ] Phases 1–2 PRs merged; xfail count for blocker tests = 0; suite green (only the 17 known OAuth baseline failures, ideally also fixed by then).
- [ ] Staging end-to-end: real phone call → order placed → **ticket visible in POS sandbox dashboard** → SMS received → call record correct in dashboard.
- [ ] Failure drill on staging: break the POS token deliberately → call → verify DISPATCH_FAILED state + operator SMS + dashboard alert fire. (This proves A7-1 is truly dead.)
- [ ] Escalation drill: trigger escalation → human phone rings → bridge works; unplugged-phone case → call appears ESCALATED in dashboard.
- [ ] Security spot-checks: WS connect without token rejected; calendar callback with forged state rejected; CORS from a random origin blocked.
- [ ] Atlas paid + backups on; Stripe live test purchase + webhook verified; Clerk prod sign-up works.
- [ ] Legal pages live; landing page contains zero unverifiable claims.
- [ ] Rollback plan: last-known-good commit tagged; Render rollback rehearsed once.

**Deliberately deferred (post-launch backlog, in order):** salon data-model migration + 12 salon UI gaps · booking integrations (Mindbody/Vagaro/Jane/Acuity) · Toast partner approval · multilingual via IVR DTMF · multi-instance scaling (limiter/scheduler) · `server.py` modular split · upsell `decide_upsell` guard (D3-11) · Vercel Hobby→Pro · remaining 🟢 polish items from AUDIT_FINDINGS.md.

---

## Operating rhythm

Daily: pick the next PR top-down → Claude writes the Claude Code prompt → run → paste diff + pytest tail back for review → staging deploy → verify → merge. One PR in flight at a time (your branch-confusion history says serialize). Anything discovered mid-fix gets logged to AUDIT_FINDINGS.md, not fixed inline, unless it's in the same file and ≤5 lines.
