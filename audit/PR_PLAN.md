# Duuutah AI — Remaining-Fixes PR Plan (post-blocker backlog)

**Created:** 2026-06-11 · **Base:** `ringai-deploy` @ `3e024467` (all 6 launch-blockers resolved)
**Findings source of truth:** `audit/AUDIT_FINDINGS.md`
**Legend:** ⬜ not started · 🔧 in progress · 🔍 in review · ✔️ merged

Sequences every still-open audit finding into 12 reviewable PRs, walked in
document order (§A → §B → §C → §D), grouped by theme (not by severity). Each PR
merges to `ringai-deploy` independently. Update the Status column as PRs land.

## Already done (context)
- 6 launch-blockers ✔️: A1-1, A1-2 (PR-C) · A3-1 CSRF-half, A6-2, C5-1 (PR-B) · A7-1, A7-2 (PR-A)
- D3-1 ✔️ verified · prepayment disabled-but-dormant · Clover per-unit + order-integrity shipped

## The 12-PR sequence

| PR | Status | Theme | Findings |
|----|--------|-------|----------|
| PR-D | ✔️ | Latent-500 / crash hardening | A8-1, A8-2, D3-2, D3-3, D3-4, D3-5, D3-6, D3-9, D3-10, D3-12, D3-15 |
| PR-E | ✔️ | Order & money accuracy (E1 accuracy · E2 modifier upcharges · E2.1 modifier display · E3 menu-driven upsell — all merged) | A7-3, A7-6, A7-8, A7-9, A7-11, A7-12, A7-14, A7-15, D3-7, D3-8, D3-11 |
| PR-F | 🔧 | Endpoint auth & abuse limits (F1 — authz holes A6-1/A6-3/A6-4) | A6-1, A6-3, A6-4, A6-5, A6-6/7/8, A2-1, A2-2, A4-1, A4-2, B4-10 |
| PR-G | ⬜ | Token-at-rest encryption & POS OAuth (finishes A3-1) | B3-7, A5-3, A4-4 |
| PR-H | ⬜ | Billing integrity & plan-casing | A5-1, A5-2, A5-5, A5-4/D3-13, D3-14, C23-1, C23-5, C12-6, C15-6 |
| PR-I | ⬜ | Booking-vertical reliability | A3-2, B2-1, A8-7, B2-7, C17-1, C17-4, C18-2, C15-8 |
| PR-J | ⬜ | Performance & startup | A1-3, A2-8/A3-3, A5-6, A1-4, A1-7, A1-5 |
| PR-K | ⬜ | Operator failure-visibility & Pro features | C9-1, C9-3, C16-3, A7-17, C24-1/B5-38, C12-1/A8-6, C21-4, C21-1/B5-26, C22-1 |
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
- **PR-G** — finishes A3-1: encrypt Google Calendar tokens at rest (reuse encryption_utils, as POS creds already do); complete the Square OAuth token exchange.
- **PR-H** — billing idempotency/dedup + the Pro-tier plan-casing lockout (normalize plan value on write).
- **PR-I** — salon/clinic reliability + appointment manual-create parity (do before selling salons).
- **PR-J** — hot-path Mongo write, double lookups, startup migration removal.
- **PR-K** — surface dispatch failures to operators; make Pro features actually deliver (voice, approve/reject aliases).
- **PR-L** — remove fabricated claims (SOC-2, testimonials, fake integrations) + finish RingAI→Duuutah rebrand. LAUNCH-GATING (FTC/legal).
- **PR-M** — publish real legal pages. LAUNCH-GATING (Stripe live mode requires them).
- **PR-N** — config fail-loud, shared constants, admin-debug console leak (C14-1), CI gating + coverage threshold.
- **PR-O** — dead code, stale `ringai-v2.onrender.com` hosts, docstrings, branding strings.

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
