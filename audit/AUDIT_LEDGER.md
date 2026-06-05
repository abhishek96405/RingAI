# Duuutah AI — Full Codebase Audit Ledger

> **Purpose:** This is the single source of truth that guarantees we review **every file and every line** before launch, across multiple sessions, without ever losing the thread. My memory resets between chats — this ledger does not. At the start of each session I read this file, pick up exactly where we left off, do the work, and update the status here.
>
> **Recommended:** commit this file to the repo (e.g. `audit/AUDIT_LEDGER.md` on a `audit/code-review` branch). Then any future session can read it directly from GitHub and we never lose state.

**Repo:** `abhishek96405/RingAI` · branch `ringai-deploy` · pinned audit commit `020ef519`
**Started:** June 5, 2026 · **Status legend:** ⬜ not started · 🟦 in progress · ✅ reviewed · 🔧 fix prompt issued · ✔️ fix merged · 📂 dir needs enumeration

---

## How each file is reviewed (the per-file protocol)

For **every** file, in one of the sessions below, I check and record:

1. **Purpose & correctness** — what it does, and whether it does it correctly (logic bugs, edge cases, race conditions).
2. **Security** — authz/tenancy enforcement, input validation, injection, secrets, PII handling.
3. **Error handling & resilience** — broad/bare excepts, swallowed errors, timeouts, retries, idempotency.
4. **Performance** — N+1 queries, missing indexes, blocking calls in async paths, payload sizes.
5. **Dead code / debt** — unused functions, duplicated logic, stubs, TODO/FIXME, debug leftovers.
6. **Standards** — naming, typing, logging (not `print`), config-via-env, structure.
7. **Rating 1–10** + a Problem/Risk/Fix entry for each issue, and (where actionable) a ready-to-paste Claude Code prompt.

Findings roll up into the main launch-readiness doc; nothing is reviewed without a recorded outcome here.

---

## Repo shape (sizing)

- **Backend:** ~16,700 lines of Python across 28 files. Three giants dominate: `server.py` (5,799 lines), `call_pipeline.py` (2,092), `gemini_service.py` (2,163).
- **Frontend:** React 18 + TS + Vite + Tailwind + shadcn/ui, scaffolded originally via **Lovable**. ~52 deps. Notable big component: `Onboarding.tsx` (37 KB).
- **Tests:** backend `tests/` + frontend `src/test/` (Vitest), `.coveragerc`, CI in `.github/workflows/`.

---

## MANIFEST + STATUS

### Backend (`/backend`)
| File | Lines/Size | Session | Status | Notes |
|---|---|---|---|---|
| server.py | 5,799 | A1–A6 | 🟦 | Launch-critical parts reviewed (CORS, webhooks, startup); full route sweep pending |
| call_pipeline.py | 2,092 | A9–A10 | ⬜ | Live-call state machine |
| gemini_service.py | 2,163 | A7–A8 | 🟦 | `send_order_to_kitchen` reviewed; rest pending |
| appointment_service.py | 918 | B3 | ⬜ | salon/clinic booking; known dead function_call path |
| reservation_service.py | 762 | B3 | ⬜ | slot-data consistency issue to investigate |
| telnyx_service.py | 679 | B2 | ⬜ | webhook sig verify confirmed good |
| auto_learning_service.py | 498 | B4 | ⬜ | |
| toast_integration.py | 428 | B2 | ⬜ | gated on partner approval |
| calendar_service.py | 338 | B3 | ⬜ | Google Calendar |
| security_utils.py | 276 | B1 | ✅ | reviewed; `get_secure_cors_origins` unused |
| websocket_notifications.py | 270 | B4 | ⬜ | in-process; multi-instance risk |
| test_mode.py | 263 | B4 | ⬜ | |
| payment_service.py | 262 | B2 | ✅ | Stripe; reviewed |
| language_prompts.py | 227 | B4 | ⬜ | |
| security_middleware.py | 224 | B1 | ✅ | CORS helper + mongo sanitize reviewed |
| rate_limiting.py | 219 | B1 | ⬜ | in-process limiter; Redis at scale |
| eta_service.py | 212 | B4 | ⬜ | |
| reminder_service.py | 189 | B4 | ⬜ | |
| pos_sync.py | 177 | B2 | 🟦 | POS sync |
| encryption_utils.py | 149 | B1 | ⬜ | token-at-rest |
| scheduler_service.py | 144 | B4 | ✅ | reviewed; guard ok, double-registered, cleanup stub |
| seed_clover.py | 109 | B4 | ⬜ | seed script |
| oauth_state_service.py | 103 | B1 | ⬜ | OAuth CSRF state |
| delivery_utils.py | 82 | B4 | ⬜ | |
| auth_helpers.py | 59 | B1 | ✅ | Clerk JWT verify — solid; set audience |
| **temp_migrate.py** | 37 | — | 🔧 DELETE | **committed PII** — remove (P0-4) |
| **temp_debug.py** | 13 | — | 🔧 DELETE | debug leftover — remove |
| **debug_gemini_methods.py** | 13 | — | 🔧 DELETE | debug leftover — remove |
| requirements.txt | — | B0 | ✅ | `telnyx` unpinned; dev tools + ML bloat |
| requirements-dev.txt | — | B0 | ⬜ | |
| pyproject.toml / runtime.txt | — | B0 | ✅ | Python 3.11.9 |
| backend/assets/ | dir | B0 | 📂 | ambient audio (cafe_ambience_8k_mono.wav) |
| backend/tests/ | dir | D1 | 📂 | unit + integration + security suites |

### Frontend (`/frontend`)
| File / Dir | Notes | Session | Status |
|---|---|---|---|
| package.json | scripts ok; **@sentry/react absent**; Lovable tagger dep | C1 | ✅ |
| **bun.lock + bun.lockb + package-lock.json** | **3 lockfiles / 2 package managers — standardize on one** | C1 | 🔧 |
| vite.config.ts / vitest.config.ts | Lovable `componentTagger` (dev-only, ok) | C1 | ✅ |
| tailwind.config.ts / postcss / eslint / tsconfig*.json | config | C1 | ⬜ |
| vercel.json | SPA rewrite — correct | C1 | ✅ |
| index.html | | C1 | ⬜ |
| src/main.tsx, App.tsx, App.css, index.css, vite-env.d.ts | app shell | C1 | ⬜ |
| src/lib/api.ts | axios + Clerk token interceptor, env-driven — clean | C1 | ✅ |
| src/lib/utils.ts | | C1 | ⬜ |
| src/context/ | auth/app context | C1 | 📂 |
| src/hooks/ | custom hooks | C1 | 📂 |
| src/pages/Login.tsx, Signup.tsx | auth screens | C2 | ⬜ |
| src/pages/Index.tsx, NotFound.tsx, PaymentSuccessPage.tsx | | C2 | ⬜ |
| src/components/ProtectedRoute.tsx, NavLink.tsx | routing/auth guards | C2 | ⬜ |
| src/pages/Onboarding.tsx | 37 KB — its own session | C3 | ⬜ |
| src/pages/dashboard/ | core app screens | C4 | 📂 |
| src/components/landing/ | marketing site | C5 | 📂 |
| src/components/layout/ | app chrome | C5 | 📂 |
| src/components/ui/ | shadcn primitives (generated — quick scan) | C6 | 📂 |
| src/test/ | frontend tests | D2 | 📂 |
| public/, src/assets/ | static assets | B0 | 📂 |

### Root / infra
| File / Dir | Session | Status |
|---|---|---|
| .github/workflows/ | D2 | 📂 (CI pipeline) |
| .gitignore | B0 | ✅ (good) |
| .coveragerc | D2 | ⬜ |
| README.md, frontend/README.md, test_result.md | D2 | ⬜ |
| memory/ | B0 | 📂 |
| test_reports/ | — | (gitignored artifact; skip) |
| tests/ (root) | D1 | 📂 |
| **stray file** `peaks, generates ambient-only frames when silent.` | — | 🔧 DELETE |

---

## SESSION PLAN (each = one focused chat)

**Batch 0 — finalize inventory (quick):** expand all 📂 dirs, read remaining configs. Output: 100% manifest.

**Phase A — Backend core (highest risk):**
- A1 `server.py` ① app/middleware/CORS/startup/auth deps/health
- A2 `server.py` ② restaurant / menu / onboarding routes
- A3 `server.py` ③ order / reservation routes
- A4 `server.py` ④ Telnyx + call-control webhooks + media stream
- A5 `server.py` ⑤ Stripe/Square/POS webhooks + billing routes
- A6 `server.py` ⑥ admin/analytics/remaining routes + **full route-by-route tenancy audit (all 95 endpoints)**
- A7 `gemini_service.py` ① pipeline/LLM service, prompts, function-calling
- A8 `gemini_service.py` ② kitchen dispatch, POS senders, queue depth, upsell
- A9 `call_pipeline.py` ① session/state machine, frame handlers
- A10 `call_pipeline.py` ② order extraction, post-call, dispatch integration

**Phase B — Backend services:**
- B1 security cluster: auth_helpers, security_utils, security_middleware, encryption_utils, oauth_state_service, rate_limiting
- B2 integrations: payment_service, telnyx_service, pos_sync, toast_integration
- B3 booking: reservation_service, appointment_service, calendar_service
- B4 remaining: scheduler, reminder, websocket_notifications, eta, delivery_utils, auto_learning, language_prompts, test_mode, seed_clover

**Phase C — Frontend:**
- C1 config + app shell + lib + context + hooks
- C2 auth pages + routing guards + small pages
- C3 `Onboarding.tsx`
- C4 `pages/dashboard/`
- C5 `components/landing` + `components/layout`
- C6 `components/ui` (shadcn — quick scan)

**Phase D — Tests + infra:**
- D1 backend tests + root tests
- D2 frontend tests + `.github/workflows` + remaining config/docs

**~23 focused sessions total.** We go at your pace; the ledger holds the line.

---

## CHANGELOG
- 2026-06-05 — Ledger created. Launch-critical pass complete (CORS, Clerk JWT, Stripe/Square/Telnyx webhooks, kitchen dispatch, scheduler, deps, frontend API client). 7 P0 launch blockers identified (see Launch Readiness Audit). Repo fully mapped at top level + key dirs.
