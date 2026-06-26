# Pre-Launch Review — Combined Tracker

**Repo:** `abhishek96405/RingAI` · **Branch reviewed:** `ringai-deploy` · **Commit:** `fb61db38`
**Date:** 2026-06-20
**Reviewers:** Claude (Opus, GitHub MCP — static read of live code) + Claude Code (local clone — ran tests, git-history forensics)
**Status of this doc:** living tracker. Update the `Status` column as items close. Commit to `audit/` (audit docs branch: `audit/code-review`).

> This is a *new, independent* review round. The prior A/C/D findings live in `audit/AUDIT_FINDINGS.md` and are not duplicated here. Where an item below was also covered by an earlier round, that's noted.

---

## Verdict & score reconciliation

| | Claude | Claude Code |
|---|---|---|
| Overall | 82/100 — "soft-launch with 2 restaurants" | 47/100 — DO NOT LAUNCH |
| Why the gap | Calibrated to a friendly 2-restaurant pilot; **made without knowledge of PL-01 (git-history secrets) and PL-02 (billing doesn't gate service)** | Calibrated to the literal "production-ready, real users + real money" bar |

**Reconciled verdict:** Claude Code's **DO NOT LAUNCH** is correct for a public launch. Both reviews independently documented that the *foundations* (multi-tenant isolation, webhook signature verification, idempotent overage billing) are genuinely strong — the low score reflects **launch-blockers present**, not poor code quality.

**Graduated path:**
1. **Rotate the leaked secrets — today** (PL-01). Non-negotiable, immediate, not even a code task.
2. Your two committed restaurants may run as a **controlled pilot** only after PL-01 + PL-02 (billing gate).
3. The concurrency items (PL-03, PL-04, PL-05, PL-16) are required **before going past a handful of simultaneous calls**.

**On "is it a 9 after we close these?"** — No. Closing these removes *known deductions* and gets you to a launch-ready **~8 with no known blockers**. The 8→9 jump is earned by *positive evidence* — load-test data, cost/error observability, monitoring — not by patching. Two reviews finding 41 issues is also strong evidence more exist that neither caught. Ship the pilot at 8; earn the 9 in production.

---

## Status legend

- `OPEN` — not started
- `WIP` — in progress
- `FIXED` — code merged, not yet verified
- `VERIFIED` — fix confirmed (test added / behavior re-checked / load-tested as applicable)
- `WONTFIX` — accepted risk (document why)

## Close-out gates (do not mark VERIFIED until these pass)

- **Concurrency items (PL-03, PL-04, PL-05, PL-16):** verified only after the **50-concurrent-call load test** passes with no audio dropouts and stable memory.
- **Billing items (PL-02, PL-07):** verified only after **new automated tests** cover the state transitions. Claude Code's key warning: the worst bugs pass all 1695 existing tests *because those paths are never exercised* (the call-billing path isn't driven; the AI client is always mocked). Fixes without tests are not trustworthy here.
- **Secret rotation (PL-01):** verified only after old credentials are confirmed **revoked** (not just replaced) and prod still functions on the new ones.

---

## 🔴 CRITICAL — launch blockers

| ID | Title | Source | Location | Fix summary | Needs new tests? | Status |
|---|---|---|---|---|---|---|
| PL-01 | Live secrets in git history (Google OAuth secret, Google API key, Mongo creds) | CC | `git log --all` → `backend/.env`, `frontend/.env`; blob @ `65e3efdb` | **Rotate all 3 now** (Google Cloud key + OAuth secret, Atlas password). Then purge history (`git filter-repo --path backend/.env --path frontend/.env --invert-paths` + force-push) or accept rotation as mitigation. Add `gitleaks` pre-commit. | n/a | OPEN |
| PL-02 | Cancelled / past-due / trial-expired tenants keep full AI call service forever | CC | `server.py:4256` (gate), `:5410-5421` (webhook), `:5354/5366` (trial write) | Gate call-admission on `is_active AND (status=="active" OR valid trial)`; flip `is_active=False` on `subscription.deleted`/`payment_failed`; add trial-expiry sweep in `scheduler_service.py` (nothing reads `trial_ends_at` today); handle payment-recovery re-activation; decide grace window. | **Yes** | OPEN |
| PL-03 | Blocking synchronous SDK calls freeze the asyncio event loop for ALL concurrent calls | Both | `gemini_service.py:198,510,2063,2104,2260` (sync OpenAI client); `server.py:126,5143,5160` (sync `stripe.*`); `reservation_service.py:428`; `appointment_service.py:624` | `AsyncOpenAI`+`await`, or wrap every sync call in `await asyncio.to_thread(...)`. **Gemini-text calls first** (hottest — fire mid-call), Stripe second. `grep to_thread|run_in_executor` = 0 matches today. | Yes (assert non-blocking under concurrency) | OPEN |
| PL-04 | Zero query indexes — every hot query is a full collection scan | Both | `server.py:6333-6334` (only 2 indexes, both TTL) | Idempotent startup index hook: `users.id` (unique), `memberships(user_id,restaurant_id)`, `call_records(restaurant_id,started_at)`, `active_calls.call_sid` + `started_at`, `webhook_events(provider,event_id)` (unique), business collections `.id`+`.stripe_customer_id`, `menu_items.restaurant_id`. **Watch:** `unique=True` fails if dupes already exist — dedup first. (Claude rated MEDIUM, CC CRITICAL — tracked as CRITICAL.) | — | OPEN |
| PL-05 | No admission control — unlimited concurrent Gemini sessions; limits only bill after the fact | CC (+ Claude M5) | `server.py:4820-5102` (media WS), `:121-123` (limit only for overage), `rate_limiting.py:137` wired only to dashboard socket | Before `create_call_pipeline`: reject when active calls for restaurant ≥ plan cap, when monthly limit exceeded and plan disallows overage, when global active ≥ ceiling; per-`from_number` throttle via existing `rate_checker`. Note: unpaid tenants (`billing_status != "active"`) are uncapped **and** free. | Yes | OPEN |

---

## 🟠 HIGH

| ID | Title | Source | Location | Fix summary | Status |
|---|---|---|---|---|---|
| PL-06 | Webhook idempotency is non-atomic (find-then-insert, no unique index) | CC | `server.py:5282-5289` (Stripe), `5923-5943` (Square) | Unique index on `(provider,event_id)` + insert-first / catch `DuplicateKeyError`. Concurrent retries currently both pass `find_one` → duplicate SMS/order-paid/notify. | OPEN |
| PL-07 | Missing `invoice.payment_succeeded` handler — monthly counter never resets | CC | `server.py:5293-5431` (handles `invoice.paid` only) | `elif event_type in ("invoice.paid","invoice.payment_succeeded")`. If Stripe is configured to send `payment_succeeded`, `monthly_call_count` never zeroes → over-billing from month 2. **Verify which event your Stripe config sends.** | OPEN |
| PL-08 | Square OAuth token never refreshed | CC | `pos_sync.py:288-299` (Clover correct at `:102-181`) | Persist encrypted `refresh_token`+`expires_at`; add `get_valid_square_token()` mirroring Clover. ~30 days post-connect, all Square sync/order-push 401s permanently. | OPEN |
| PL-09 | Square webhook blocked by Cloudflare bypass list | CC | `server.py:6229-6243` (`CF_BYPASS_PREFIXES`) | Add `"/api/webhooks/square"` (handler at `:5870` already HMAC-verifies). Stripe webhook path is in the list; Square's is not — with `CF_SECRET_TOKEN` set, Square's servers get 403 and Square disables the endpoint. **Verify in Cloudflare.** | OPEN |
| PL-10 | CI does not gate deployment | Both | `.github/workflows/tests.yml`; no in-repo deploy step | Enable required-check gating in Vercel + Render; branch protection on `ringai-deploy`. Red CI doesn't stop a deploy today. **Dashboard config — verify there.** | OPEN |
| PL-11 | ORDER_CONFIRMED while restaurant CLOSED → dead air, no dispatch | CC | `call_pipeline.py:538-540` | Returns after AI says "confirmed" and after `_order_confirmed_handled=True`, before teardown/dispatch. Block the order before the AI confirms, or fire teardown + fallback speech. | OPEN |
| PL-12 | Menu price unvalidated | CC | `server.py:916` (`price: int`, no bounds; appt price bounded at `:1896`) | `price: int = Field(ge=0, le=10_000_000)` on create + update. Negative/zero/huge currently accepted → corrupt totals. | OPEN |
| PL-13 | Restaurant set `is_active=True` even when Telnyx provisioning fails | CC + Claude | `server.py:3358` (set before provision), `:3423-3431` (failure only logs) | Only activate after a number is bound, or expose `provisioning_pending` + retry. Otherwise a paid "live" tenant has no inbound routing. | OPEN |
| PL-14 | Entire post-call record dropped on any failure | CC | `server.py:4925-4965/5075` (one try wraps build+construct+insert) | Persist minimal `CallRecord(status="incomplete")` fallback; always `delete_one(active_calls)`. Any raise loses the record + leaves a stale active_calls row. | OPEN |
| PL-15 | Gemini Live has no reconnection | Both | `call_pipeline.py:2385-2395` | Bounded reconnect loop w/ exponential backoff preserving `LLMContext`; customer message on final failure. Mid-call WS drop = dead air today. (Partial-order salvage on disconnect exists — keep it.) | OPEN |
| PL-16 | Single-process in-memory session registry | Both | `server.py:147` (`_ACTIVE_SESSIONS`) | **Pin `--workers 1` explicitly** (no worker count committed anywhere) or move state to Redis (`REDIS_URL` already read in `rate_limiting.py`). With >1 worker, `call.bridged`/`call.hangup` can hit a worker without the session → transfers don't release, caps go per-worker. | OPEN |
| PL-17 | Encryption key management fragile (Clerk fallback + hardcoded default) | Claude | `encryption_utils.py:26-50` | Resolves `ENCRYPTION_SECRET_KEY` → `CLERK_SECRET_KEY` → hardcoded default string. Using Clerk's secret as the encryption key means **rotating Clerk (PL-01!) silently breaks decryption of all stored POS creds** (`decrypt_value` returns `""`). Require a dedicated key, remove both fallbacks, fail-fast if unset. **Needs a decrypt-old/re-encrypt-new migration for existing data.** | OPEN |
| PL-18 | `encrypt_value` is fail-open — plaintext credential stored | Claude | `encryption_utils.py:~99` | On any encryption error it logs and returns plaintext, which is then written to Mongo. Change to `raise` — never persist plaintext. (Distinct from PL-20's alternate plaintext path.) | OPEN |

---

## 🟡 MEDIUM

| ID | Title | Source | Location | Fix summary | Status |
|---|---|---|---|---|---|
| PL-19 | Clerk JWT issuer/audience optional; alg taken from token | CC | `auth_helpers.py:40-59` | Require issuer+audience in prod; pin `algorithms=["RS256"]`. | OPEN |
| PL-20 | `RestaurantUpdate` lets owner write POS secrets/billing fields in plaintext | CC | `server.py:656-677,1345-1403` | Remove `clover_api_token`/`square_access_token`/`toast_client_secret`/`stripe_account_id`/`billing_status` from `RestaurantUpdate` — they bypass the encrypted `/pos/credentials` path + allow billing-state corruption. | OPEN |
| PL-21 | Telnyx signature skipped when backend URL contains `localhost` | CC | `server.py:4520-4527,4670` | Gate the skip on an explicit `ENV=development` flag, not URL string match — otherwise a proxied/misconfigured URL disables verification. | OPEN |
| PL-22 | Mongo client has no `maxPoolSize`/timeouts | CC + Claude | `server.py:296` | Set `maxPoolSize`, `serverSelectionTimeoutMS=5000`, etc. Default = 100/worker + 30s hang on Atlas blips. | OPEN |
| PL-23 | No Mongo error handling on the live-call path | CC | `server.py:4865` etc. | Short selection timeout + narrow retry/fallback. Transient Atlas failover → 500/aborted call today. | OPEN |
| PL-24 | Clerk JWT passed in the WebSocket URL (logged) | CC | `useWebSocketNotifications.ts:76` | Mint a short-TTL WS ticket, or send token as first WS message. Token currently lands in CF/Render access logs. | OPEN |
| PL-25 | `.env.example` uses `REACT_APP_` but code reads `import.meta.env.VITE_` | CC | `frontend/.env.example`, `main.tsx:7`, `api.ts:5` | Rewrite the example to the actual `VITE_*` vars — a deployer copying it gets the "Configuration error" screen + localhost API. | OPEN |
| PL-26 | Transfer destination not validated; no fallback prompt | CC | `call_pipeline.py:695-791` | `normalize_e164` the number; speak an apology before hangup. (Transcript saved first — good.) | OPEN |
| PL-27 | Untracked fire-and-forget tasks (leak + late side-effects) | CC | `call_pipeline.py:492,694,956,996,1677,…` | Per-session task set; cancel in `finally`. | OPEN |
| PL-28 | POS 401 not retried; Toast sandbox host == prod | CC | `gemini_service.py:778`, `toast_integration.py:26-38` | Force-refresh+retry on 401; set the real Toast sandbox URL. | OPEN |
| PL-29 | Gemini Live: no max-output-tokens, no hard PRO duration cap; live cost hardcoded `0.0` | CC | `call_pipeline.py:1175,2227` | Absolute per-call wall-clock kill + real cost constant. (Ties to cost observability gap.) | OPEN |
| PL-30 | No fail-fast env validation at startup | Claude | `server.py:~295` (`MONGO_URL`/`DB_NAME` default to localhost) | Startup check that `sys.exit(1)`s on any missing required var — misconfigured deploy currently boots "healthy" and fails at runtime. | OPEN |

---

## 🔵 LOW

| ID | Title | Source | Location | Fix summary | Status |
|---|---|---|---|---|---|
| PL-31 | Unescaped user input in `$regex` (ReDoS / CPU stall) | CC | `server.py:2467,2918` | `re.escape(...)`. | OPEN |
| PL-32 | Overage `InvoiceItem.create` failure swallowed, no retry (under-billing) | CC | `server.py:4969` | Write a `pending_overage` doc for reconciliation. (Double-charge guard `idempotency_key=overage:{call_sid}` correctly present.) | OPEN |
| PL-33 | `telnyx` (no version) + `soundfile>=0.12.1` unpinned | Both | `requirements.txt` | Pin both. (Also note: `google-auth==2.49.0.dev0` is a pre-release.) | OPEN |
| PL-34 | `is_open` defaults to OPEN on timezone parse error | CC | `appointment_service.py:267-273` | Default to CLOSED/unknown. | OPEN |
| PL-35 | `sanitize_mongo_query` imported but never called | CC | `server.py:344` | Wire on raw-body routes or remove (latent; all routes use Pydantic today). | OPEN |
| PL-36 | Duplicate `call.initiated` double-answers | CC | `server.py:4542-4574` | Dedup on `call_control_id`. | OPEN |
| PL-37 | Committed `test_reports/coverage.xml` covers only `test_mode.py` (false confidence) | CC | `test_reports/coverage.xml` | Regenerate full coverage; ensure `.coveragerc` scope. | OPEN |
| PL-38 | `pytest` from repo root fails collection (`TestModeStatus` has `__init__`) | CC | `backend/test_mode.py` | Rename the class or add `__test__ = False`. `pytest tests/` is clean. | OPEN |
| PL-39 | `VITE_ADMIN_CLERK_ID` leaks admin Clerk ID into public bundle | Claude | `AdminPage.tsx:12` | Cosmetic info leak — backend enforces `ADMIN_USER_ID` server-side (not a bypass). Move admin check fully server-side if desired. | OPEN |
| PL-40 | Some endpoints return `detail=str(e)` (internal error text) | Claude | `server.py:1291,1398,1445,5824` | Map to generic messages (refund route leaks Stripe error text). | OPEN |
| PL-41 | No Clerk webhook (user deletions/email changes don't propagate) | Claude | — (lazy sync in `get_current_user`) | Optional — add a `svix`-verified Clerk webhook, or accept as designed (`WONTFIX` candidate). | OPEN |
| PL-42 | Dependency CVE scan never run by **either** review | Both | `requirements.txt`, `frontend/package.json` | Run `pip-audit` + `npm audit --audit-level=high`; triage any High/Critical CVEs (each becomes its own tracked item); add both to CI. **This is an unperformed check, not a clean bill of health.** | OPEN |
| PL-43 | Dev/localhost origins always in the production CORS allowlist | Claude | `server.py:246` (`get_cors_origins`) | Gate the localhost defaults behind a non-prod check. Not exploitable; hygiene. | OPEN |
| PL-44 | Dead Twilio env vars linger (Telnyx is the live telephony integration) | CC | env / config | Remove unused Twilio config to avoid future confusion. Hygiene only. | OPEN |

---

## Remediation sequence (suggested)

Not "all in one day." Front-load the blockers; separate the risky state-machine/migration work from the mechanical batch. Map to your PR flow.

**Day 1 — safe mechanical batch + the non-negotiable rotation (low regression risk):**
- PL-01 (rotate secrets — do this FIRST, it's console work)
- PL-03 (`to_thread` wrapping — Gemini-text first, then Stripe)
- PL-04 (startup index hook — handle existing dupes before `unique=True`)
- PL-16 (pin `--workers 1`), PL-30 (env fail-fast), PL-12 (menu price bounds), PL-33 (pin deps)

**Day 2–3 — state machine, migration, features (require new tests; do not rush):**
- PL-02 (billing gate + revoke + trial sweep) — biggest risk if rushed: can cut off a *paying* customer
- PL-05 (admission control)
- PL-17 + PL-18 (encryption key + fail-closed; needs re-encrypt migration)
- PL-06 (atomic webhook idempotency), PL-07 (`invoice.payment_succeeded`), PL-08 (Square OAuth refresh), PL-09 (Square CF bypass)

**Day 3–4 — resilience + remaining highs/mediums:**
- PL-11, PL-13, PL-14, PL-15, PL-19–PL-29

**Then:** 50-concurrent-call load test — only after it passes can PL-03/04/05/16 move to VERIFIED.

**Opportunistic:** all LOW items (PL-31–PL-41).

---

## What is built correctly — DO NOT regress

Both reviews independently confirmed these. Protect them while remediating:

1. **Webhook authenticity** — Stripe `construct_event` on raw bytes + ±300s replay window; Square HMAC-SHA256 with `hmac.compare_digest`; Telnyx Ed25519 with timestamp tolerance. (Signature verification is excellent; only the *dedup* is racy — see PL-06.)
2. **Multi-tenant isolation** — every by-id route looks up the doc then enforces a `db.memberships` check on its `restaurant_id`; cross-tenant returns 404, with tests in `tests/security/test_tenant_isolation_calls.py`.
3. **Billing-bypass-at-activation closed** — `/onboarding/activate` independently verifies a real Stripe subscription (402 otherwise). (The *continuation* path is the gap — PL-02.)
4. **Atomic, idempotent overage billing** — `find_one_and_update($inc, ReturnDocument.AFTER)` + Stripe `idempotency_key=overage:{call_sid}`.
5. **Encryption-at-rest + OAuth CSRF** — POS/calendar secrets `encrypt_value`'d; OAuth uses signed single-use state, trusts stored `restaurant_id` not the callback param. (Key *management* is the weak spot — PL-17/18.)
6. **Fail-closed POS dispatch + clean teardown** — failures become `DISPATCH_FAILED` with operator alerts (never fake success); `finally` blocks always hang up + unregister; zombie sweeper backstop.

---

## Notes / open verifications (confirm outside the repo)

- PL-01: confirm the recovered blobs are real and old creds are revoked.
- PL-07: confirm which invoice event your Stripe webhook config emits.
- PL-09 / PL-10: Cloudflare bypass + Vercel/Render deploy gating are dashboard settings — verify there.
- PL-16: confirm Render start command stays single-worker (`uvicorn server:app --host 0.0.0.0 --port $PORT` — no `--workers`, currently correct by accident).
- Python runtime: `runtime.txt` pins `3.11.9` (deploy target); Claude Code's local run reported 3.13 — confirm Render honors `runtime.txt`.
- Test count: 1695 passed / 1 skipped / 5 xfailed @ `fb61db38` (Claude Code ran the suite).
- **PL-42:** neither review ran a dependency vulnerability scan. Run `pip-audit` + `npm audit` before launch — results may add new findings to this tracker.
