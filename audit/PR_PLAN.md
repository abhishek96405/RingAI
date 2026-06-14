# Duuutah AI — Remaining-Fixes PR Plan (post-blocker backlog)

**Created:** 2026-06-11 · **Base:** `ringai-deploy` @ `3e024467` (all 6 launch-blockers resolved)
**Updated:** 2026-06-13 · `ringai-deploy` @ `f1e76a2d` — POS OAuth arc shipped (Clover connect + Integrations redesign + Square landing page); PR-F closed (launch scope)
**Findings source of truth:** `audit/AUDIT_FINDINGS.md`
**Legend:** ⬜ not started · 🔧 in progress · 🔍 in review · ✔️ merged

Sequences every still-open audit finding into 12 reviewable PRs, walked in
document order (§A → §B → §C → §D), grouped by theme (not by severity). Each PR
merges to `ringai-deploy` independently. Update the Status column as PRs land.

## Already done (context)
- 6 launch-blockers ✔️: A1-1, A1-2 (PR-C) · A3-1 CSRF-half, A6-2, C5-1 (PR-B) · A7-1, A7-2 (PR-A)
- D3-1 ✔️ verified · prepayment disabled-but-dormant · Clover per-unit + order-integrity shipped
- **POS OAuth arc ✔️ (2026-06-13, all merged to `ringai-deploy`):** Clover v2 OAuth (C1 backend + C2 callback page) — **validated live end-to-end** (connect → encrypted token in Mongo → menu sync on sandbox merchant `ANDMRV7JVAAC1`) · Integrations page redesign (C3) · Square OAuth branded landing page (C4). Detail in the "POS OAuth arc" section below.

## The 12-PR sequence

| PR | Status | Theme | Findings |
|----|--------|-------|----------|
| PR-D | ✔️ | Latent-500 / crash hardening | A8-1, A8-2, D3-2, D3-3, D3-4, D3-5, D3-6, D3-9, D3-10, D3-12, D3-15 |
| PR-E | ✔️ | Order & money accuracy (E1 accuracy · E2 modifier upcharges · E2.1 modifier display · E3 menu-driven upsell — all merged) | A7-3, A7-6, A7-8, A7-9, A7-11, A7-12, A7-14, A7-15, D3-7, D3-8, D3-11 |
| PR-F | ✔️ | Endpoint auth & abuse limits (F1 authz · F2 rate-limit/body-size · F3 WS cap · F4 media-stream timeout — launch scope done; blanket rate-limit + signed stream-URL consciously deferred, see notes) | A6-1, A6-3, A6-4, A6-5, A6-6/7/8, A2-1, A2-2, A4-1, A4-2, B4-10 |
| PR-G | ✔️ | Token-at-rest encryption & POS OAuth (finishes A3-1) | B3-7, A5-3, A4-4 |
| PR-H | ✔️ | Billing integrity & plan-casing (launch scope: H1 plan-casing · H2 billing-bypass · H3 webhook-resilience · H4 overage-integrity — all merged; C23-5 verified no-op; A5-5/H5 refund hardening parked with the dormant prepayment feature) | A5-1, A5-2, A5-5, A5-4/D3-13, D3-14, C23-1, C23-5, C12-6, C15-6 |
| PR-I | ✔️ | Booking-vertical reliability (scope: restaurants + salons only — clinic/home_services/legal dormant. I0 vertical-pruning ✔️ · I1 booking-dispatch reliability ✔️ · I2a failure-surfacing ✔️ — booking_dispatch_failed already reaches the high-priority toast/bell path (C17-1); now rendered as an alert with a heavier toast. I2b manual appointment create ✔️ (CreateAppointmentDialog → existing bookAppointment endpoint, persists regardless of calendar; C17-4). I2c confirm/resolve-conflict parity ✔️ (PATCH /appointments/{id}/confirm promotes conflict→confirmed only — narrow, never resurrects cancelled; Confirm button on conflict rows; C18-2). I3 double-book atomicity (A3-2) ⏸️ deferred post-launch — count-based capacity, race shared by the operator endpoint + the live voice path; reservations are opt-in/Pro/default-OFF with no live customers, so the seat-index fix is tracked rather than shipped pre-launch (see AUDIT_FINDINGS A3-2 for design + trigger). I4: C15-8 timezone ✔️ verified (real `auto_detect_timezone`, claim accurate); B2-x dead function_call path ✔️ verified absent; B2-7 calendar free/busy ⏸️ deferred post-launch (feature with manual-block workaround, `get_free_busy` partly scaffolded). PR-I COMPLETE — every finding done or consciously deferred (A3-2 ⏸️, B2-7 ⏸️)) | A3-2, B2-1, A8-7, B2-7, C17-1, C17-4, C18-2, C15-8 |
| PR-J | ✔️ | Performance & startup (J1 A1-3 get_current_user hot-path write eliminated ✔️ · J2 A2-8/A3-3 resolve_restaurant_access added + reservation & POS routes migrated 4→2 reads ✔️; ~11 remaining double-lookup routes tracked for opportunistic migration — see AUDIT_FINDINGS A2-8/A3-3 · J3 A5-6 fan-out ⏸️ accepted by design (hot-path already de-fanned in PR-H; remaining fan-outs are a cold-path safety net, tidy-up to [restaurants, salons] tracked — see AUDIT_FINDINGS A5-6) · J4 A1-4 startup-migration ✔️ — @app.on_event("startup") removed; data no longer migrated on every boot (migrate_split_brain.py is the comprehensive one-off) · J5 A1-5 logging-init order ✔️ (basicConfig moved to import top so early INFO is captured/formatted) · A1-7 hard-imports ⏸️ accepted by design (optional modules already soft-imported; core modules correctly fail-fast — see AUDIT_FINDINGS A1-7)) | A1-3, A2-8/A3-3, A5-6, A1-4, A1-7, A1-5 |
| PR-K | 🔧 | Operator failure-visibility & Pro features (K1 A8-6/C12-1 per-restaurant voice ✔️ — create_call_pipeline resolves voice from config.voice_id (session.config) instead of overwriting with env GEMINI_VOICE; the VoiceAndAITab picker now drives live calls) | C9-1, C9-3, C16-3, A7-17, C24-1/B5-38, C12-1/A8-6, C21-4, C21-1/B5-26, C22-1 |
| PR-L | ⬜ | Marketing-claims & rebranding cleanup (LAUNCH-GATING: FTC/legal) | C32-1, C28-1, C31-1, C30-3, C29-1/C34-1, C33-1, C27-1, C12-2, A2-6, A1-6, A7-4 |
| PR-M | ⬜ | Legal pages — Privacy/Terms/Security/GDPR (LAUNCH-GATING: Stripe live) | C35-1 |
| PR-N | ⬜ | Config & CI hardening | C0-1, C1-1, C2-3, C20, C6-3, C14-1, C7-1, A2-3, D1-1, D1-2, D2-1, D2-2 |
| PR-O | ⬜ | Cosmetic / dead-code sweep | A2-4, A2-5, A2-7, A4-3, A7-5, A7-7, A7-10, A7-13, A7-16, A7-18, A8-3, A8-4, A8-5, A8-8, A8-9 |

## Per-PR notes
- **PR-D** — pure crash/500s; each has an xfail-strict test. Fix + flip the xfail = red→green proof. Includes the active salon `pos_type:null` crash (A8-1/A8-2).
- **PR-E** — order correctness + money; A7-6 (modifier upcharges) is the meatiest (tool-schema + handler change). Pairs with the modifier work discussed for Clover (name/note encoding, price baked into line total).
- **PR-F** — endpoint authz + rate limits + WS connection caps + body-size limit (verify RequestSizeLimitMiddleware already covers B4-10).
- **F2 (rate limits + body-size) — DONE:**
  - A2-2: public menu `/menu/{restaurant_id}` rate-limited (30/min per IP).
  - A2-1 (partial): `send-menu-sms` rate-limited (10/min per user) — SMS cost guard.
  - B4-10: already implemented (5MB RequestSizeLimitMiddleware) and already tested
    (security/test_input_validation_oversize_payloads.py) — no change needed.
  - DEFERRED (accepted-for-launch): blanket rate-limiting of all authenticated writes /
    global SlowAPIMiddleware. Reason: (1) a global IP-keyed limit would throttle Telnyx
    call/SMS webhooks and Stripe/Square payment webhooks (all from a few vendor IPs) →
    dropped calls/payments; going blanket safely needs per-route exemptions across the
    whole call path. (2) The in-process limiter is only partly effective on a single
    instance; proper blanket limits need a Redis-backed store once multi-instance.
    Revisit before onboarding real paying customers.
- **F3 (WS connection cap / A4-1) — DONE:**
  - /ws/notifications now enforces MAX_WS_PER_RESTAURANT (5) live sockets per restaurant
    via check/register/unregister_ws_connection (previously imported but never called).
    Over-cap connections are rejected at the handshake with close 1013, before accept.
  - The media-stream (call-path) WS is intentionally NOT capped — capping it would drop a
    legitimate Nth concurrent call. It uses the separate register_active_websocket
    tracker, left unchanged.
- **F4 (media-stream WS / A4-2) — PARTIAL, rest consciously deferred:**
  - DONE: 15s timeout on the unauthenticated pre-start window
    (MEDIA_STREAM_START_TIMEOUT_SECONDS) — silent sockets closed with 1008. This was
    the only zero-knowledge attack sliver (anyone could hold connections open forever;
    the media WS is intentionally uncapped per F3).
  - DEFERRED (accepted-for-launch): stream-URL signed token + duplicate-stream guard.
    Reason: (1) the Telnyx webhook chain is already Ed25519 signature-verified, so
    abusing the media WS requires a LIVE call_control_id — an opaque, unguessable
    token valid only for the minutes a call is up, present only in signed webhooks,
    private logs, and the DB. (2) Both fixes put their failure mode on 100% of calls:
    a token-verification or URL-encoding bug = no call can connect; a naive dup guard
    can reject a legitimate Telnyx reconnect against a not-yet-cleaned-up session
    (cleanup runs after pipeline teardown). Revisit on staging with a dedicated
    Telnyx test number before onboarding real paying customers.
- **G1 (A4-4) — DONE:** the two silent `except: pass` blocks around POS-credential
  decryption (in `pos_sync_menu` and the media-stream handler) now log via
  `logger.error(..., exc_info=True)` — visible in Render logs and forwarded to Sentry when
  configured. Behavior unchanged (still continues past a decrypt failure rather than
  crashing). Observability only; no new test.
- **G2 (A3-1 token-at-rest / B3-7) — DONE:** Google Calendar OAuth tokens are now encrypted
  at rest. New `encrypt_calendar_tokens`/`decrypt_calendar_tokens` helpers encrypt the
  access_token + refresh_token values inside the tokens dict (the flat
  ENCRYPTED_CREDENTIAL_FIELDS path can't handle a dict). Encrypted at both write paths (OAuth
  callback + the refresh write-back in get_valid_access_token) and decrypted at the sole
  consumer (get_valid_access_token). The `enc:` prefix makes the helpers idempotent and lets
  pre-existing plaintext tokens migrate for free. Two existing tests updated to assert the
  encrypted-at-rest contract.
  - POTENTIAL (separate, NOT fixed here): the refresh write-back hardcodes
    `db.restaurant_configs` while the callback uses `get_config_collection(business_type)` —
    if those collections differ for appointment businesses, refreshed tokens persist to the
    wrong collection. Verify get_config_collection's mapping; track for PR-I.
- **G3 (A5-3) — DONE:** the Square OAuth callback now EXCHANGES the authorization code for an
  access token (previously it stored the raw code and set square_connected=True without ever
  obtaining a token — the integration was non-functional). New `exchange_square_code` in
  pos_sync.py POSTs to Square's /oauth2/token; the callback stores `square_access_token`
  ENCRYPTED (matching the POS-credential pattern; decrypted before sync use) plus the
  merchant_id, marks connected only on a successful exchange, and on failure records
  status="error" + returns 502. The raw auth_code is no longer stored. 3 new exchange unit
  tests; 2 existing square-callback tests updated to the encrypted-token contract.
  - REQUIRES new env var SQUARE_APPLICATION_SECRET on Render (the Square app's OAuth secret),
    alongside SQUARE_APPLICATION_ID / SQUARE_REDIRECT_URI.
  - Square endpoints are hardcoded to production (connect.squareup.com), consistent with the
    existing authorize + catalog URLs. Real verification needs a live Square OAuth round-trip
    with a production Square app; unit tests cover only the mocked exchange.
- **Test determinism (utcnow flake) — FIXED:** the rotating ~17 failures were a dependency
  (Starlette/jose) calling the deprecated datetime.datetime.utcnow(), promoted to an error by
  `filterwarnings = ["error", ...]` for whichever tests hit that path under pytest-randomly
  ordering. No repo code (source or tests) calls utcnow() — verified across all modules. Added
  a global `ignore:datetime.datetime.utcnow` to filterwarnings (the same pattern 7 tests
  already applied locally). The 7 now-redundant per-test markers can be removed later (harmless).
  Also revealed + fixed one genuine pre-existing failure this masked:
  test_square_callback_rejects_replayed_state (tests/security/) never mocked exchange_square_code,
  so post-G3 its first callback 502'd — added the same monkeypatch mock the other two G3
  square-callback tests use.
- **Square environment switching (connect + sync) — DONE:** OAuth authorize (server.py),
  token exchange + catalog sync (pos_sync.py) now select sandbox vs production via
  SQUARE_ENVIRONMENT (default sandbox), matching _send_to_square and the Clover switch.
  Unblocks sandbox connect testing. FOLLOW-UP (Slice B, call-path): gemini_service.py queue-depth
  orders/search calls (lines ~872, ~903) still hardcode production — non-fatal (try/except → None),
  fix next with a live sandbox call to verify.
- **PR-G** — finishes A3-1: encrypt Google Calendar tokens at rest (reuse encryption_utils, as POS creds already do); complete the Square OAuth token exchange.
- **H1 (C12-6/C15-6 plan-casing) — DONE:** canonical plan casing is UPPERCASE; reads normalized everywhere so a lowercase/mixed-case stored plan can't silently demote a paying Pro customer. get_plan_features() uppercases its input (covers all backend callers); gemini_service + call_pipeline direct reads normalized; frontend isProPlan() helper replaces all `plan === "PRO"` gates; BillingPage sends UPPERCASE. Added backend + frontend case-insensitivity tests. NOTE: the write side was already uppercase-normalized since the audit (server.py:4871 `.upper()`), so the lockout was latent, not active — H1 makes it structurally immune.
- **H2 (C23-1 billing-bypass) — DONE:** POST /api/onboarding/activate no longer flips is_active / auto-provisions a Telnyx number on the caller's word alone. It requires a confirmed subscription — billing_status in {trialing, active} (webhook-set) OR, when the redirect beats the webhook, a live trialing/active subscription verified against Stripe directly (customer id stored at checkout-session creation). No subscription → 402. Backfills billing_status/stripe_subscription_id when resolved via Stripe.
- **H3 (D3-13/A5-4 + D3-14 webhook resilience) — DONE:** Stripe webhook now (1) dedups on event id — seen ids recorded in webhook_events (provider="stripe", 7-day TTL); a replay short-circuits with {received, deduped} before any side effect, mirroring the Square handler — closing duplicate payment-SMS / WS-notify on Stripe retries; and (2) rejects a signature timestamp >300s in the future (400). The future check is one-sided on purpose (construct_event covers the old side; a two-sided abs() check would reject the t=0 placeholder used by mock idempotency tests) — together they form the two-sided ±300s window in production. Flipped both waiting xfail-strict captures to normal passes; deleted the obsolete test_future_timestamp_is_currently_accepted_captures_bug.
- **H4 (A5-1/A5-2 overage integrity) — DONE:** the overage path is extracted into a module-level `_record_call_for_billing()` helper (a clean seam for a future Stripe metered-billing swap). A5-2: monthly_call_count is incremented atomically with find_one_and_update(return_document=AFTER) on the collection that holds the doc, and the overage threshold is decided against that authoritative post-increment count — not a stale pre-fetched value (also drops the 5-collection $inc fan-out for this write). A5-1: the overage InvoiceItem carries idempotency_key=overage:{call_sid} so a retried call-complete can't double-charge. billing_status gate unchanged (== "active": no overage during the free trial). New unit tests: authoritative-count billing + idempotency key, under-limit no-bill, trialing no-bill.
- **H5 (A5-5 refund hardening) — PARKED (not a launch blocker):** `refund_order` refunds a *customer order prepayment* via Stripe Connect (reverse_transfer + refund_application_fee), and order prepayment is disabled-but-dormant for launch (`sms_payment_enabled = False` hardcoded in the call-complete path; the only `payment_status="paid"` setter — the order_payment webhook branch — can never fire). So the refund path cannot reach a refundable order at launch, and A5-5's three gaps (raw-Stripe-error leak, no idempotency key, Stripe-before-DB ordering) cannot manifest. NOT subscription-related — subscription cancel/refund goes through the 7-day trial, the Stripe customer portal, and the customer.subscription.deleted webhook, none of which touch refund_order. **TRIGGER: fix A5-5 (idempotency_key=refund:{call_sid} + generic error + DB-claim-before-Stripe) before re-enabling order prepayment.**
- **C23-5 (revenue chart units) — VERIFIED no-op:** backend pre-divides the chart series by 100 (server.py:2743/2757), so chart + KPI tiles both render dollars. No change; closed.
- **H2b (DEFERRED, defense-in-depth):** the inbound call path (_prefetch_call_session_data) still gates on is_active alone, not billing_status. Adding a billing_status gate there (serve only trialing/active/past_due) is tracked but deferred pending voice-fixture review — it changes the hottest path and a bug = no calls connect.
- **PR-H** — billing idempotency/dedup + the Pro-tier plan-casing lockout (normalize plan value on write).
- **PR-I** — salon/clinic reliability + appointment manual-create parity (do before selling salons).
- **PR-J** — hot-path Mongo write, double lookups, startup migration removal.
- **PR-K** — surface dispatch failures to operators; make Pro features actually deliver (voice, approve/reject aliases).
- **PR-L** — remove fabricated claims (SOC-2, testimonials, fake integrations) + finish RingAI→Duuutah rebrand. LAUNCH-GATING (FTC/legal).
- **PR-M** — publish real legal pages. LAUNCH-GATING (Stripe live mode requires them).
- **PR-N** — config fail-loud, shared constants, admin-debug console leak (C14-1), CI gating + coverage threshold.
- **PR-O** — dead code, stale `ringai-v2.onrender.com` hosts, docstrings, branding strings.

## POS OAuth arc (feature work — 2026-06-13, not audit findings)
Net-new connector + integrations UX, shipped as 4 reviewed slices, all merged to `ringai-deploy`:
- **C1 — Clover v2 OAuth backend** (`900fdb96`): `/integrations/clover/connect` (authorize URL, no state — Clover v2 has none) + authenticated `/integrations/clover/exchange` (ensure_restaurant_access is the CSRF defense replacing the state token). `exchange_clover_code` / `refresh_clover_token` / `get_valid_clover_token` in pos_sync.py; access + refresh tokens encrypted at rest (clover_refresh_token added to ENCRYPTED_CREDENTIAL_FIELDS); sandbox token host `apisandbox.dev.clover.com` (CLOVER_OAUTH_TOKEN_BASE override). Real test_pos_connection checks for Square + Clover. 19 unit tests.
- **C2 — Clover frontend callback page** (`fd73f246`): standalone /integrations/clover/callback page does the authenticated exchange (StrictMode single-fire guard); handles App-Market launch (merchant_id, no code → initiates authorize) + sign-in / error / invalid states.
- **C3 — Integrations page redesign** (`b3ee69d1`): removed Integration-Status / Telnyx-Number / Required-Env-Vars cards; new POSCard with a 3-row connect selector (Square/Clover live Connected badges read fresh from getRestaurant on mount; Toast "Coming soon"); manual-credentials form collapsed under an accordion; Calendar gated to `business_type != "restaurant"`. Backend one-liner: added `pos_type="square"` to square_callback (routing-asymmetry fix).
- **C4 — Square OAuth branded landing** (`f1e76a2d`): square_callback now 303-redirects to a display-only SquareCallbackPage (success/error from query params) instead of raw JSON. Frontend base resolved via FRONTEND_URL → CLOVER_REDIRECT_URI origin. State validation still gates the exchange (bad/replayed state → reason=invalid_state redirect, exchange never runs).

Open follow-ups for this arc:
- **Clover order-push token refresh** — ✔️ SHIPPED (`0b7bebd2`): `get_valid_clover_token` is wired into `_send_to_clover` (gemini_service.py:733) with `db` plumbed through the order-push path.
- **Square live validation** — Clover was validated live; Square OAuth still needs a real sandbox round-trip (Square sandbox app not set up yet).
- **Clover private-app approval** — required before non-dev merchants can connect (functional demo video + legal/privacy docs). External action.
- C4 makes **FRONTEND_URL** load-bearing for the Square landing — covered by the existing LAUNCH_PLAN gate ("point FRONTEND_URL at the canonical www origin"); falls back to CLOVER_REDIRECT_URI origin until set.

Live setup state: Clover sandbox app `0B8DHWXAGS764` (Private); Render has CLOVER_APP_ID / CLOVER_APP_SECRET / CLOVER_REDIRECT_URI + CLOVER_ENV=sandbox.

## Conscious decisions (accepted for launch)
- **A7-15** — on-disconnect last-chance extraction may dispatch a non-explicitly-confirmed order. Accepted: favor capturing genuinely-confirmed orders over consent-strictness; the prompt half was already correct. Revisit post-launch.

## Known issues (tracked, not tied to a specific PR)
- **Gemini Live intermittent stall** — on some calls Gemini pauses ~10s mid-turn (most visible right before/around the readback + `compute_order_total`), and occasionally speaks a guessed total before the tool returns. Confirmed NOT caused by the PR-E3 upsell change — a second call on the same build was smooth. Same root as the audio-clipping chased via the Pipecat upgrade attempt; no clean fix today. Revisit before real customers (dead air on a live call is a real UX risk).

## Parked (NOT in the 12 — fire on external triggers)
- **TOAST-REBUILD-1 / B1-6/7/8** — needs Toast partner-program approval.
- **SQUARE-PRINT-1** — needs a real Square client's KDS hardware to verify.
- **SQUARE-PREPAY-1** — post-launch revenue feature.

## Non-findings launch gates (tracked in LAUNCH_PLAN.md, not here)
Atlas off M0 + backups · Clerk prod keys · staging E2E drill · deliberate-failure drill · point FRONTEND_URL at the canonical www origin.
