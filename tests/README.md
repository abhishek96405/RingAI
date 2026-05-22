# Duuutah AI — Test Suite

This directory hosts cross-cutting test docs and any future repository-root
test files. The bulk of the backend suite lives in [backend/tests/](../backend/tests/);
the frontend suite lives in [frontend/src/test/](../frontend/src/test/).

The suite is built in six commits. This file is committed in commit 1 and
extended as later commits land.

## Quick start

### Backend

```bash
# One-time setup
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt

# Run the full default suite (offline, all externals mocked)
pytest

# Run a single marker
pytest -m unit
pytest -m "integration or webhook"
pytest -m security

# Run a single file or test
pytest backend/tests/unit/test_language_prompts.py
pytest backend/tests/unit/test_language_prompts.py::test_english_prompt

# Parallel execution
pytest -n auto

# Coverage HTML report
pytest && open test_reports/coverage_html/index.html
```

### Frontend

```bash
cd frontend
npm ci
npm run test           # watch off, single run
npm run test:watch     # watch mode
npm run test:coverage  # with coverage report
```

## Test layout

```
backend/tests/
  conftest.py         — root fixtures (db, clients, mocks, two-tenant setup)
  factories/          — Mongo-shape factories (one per entity)
  fixtures/           — JSON canned responses (Gemini, Telnyx, Stripe, etc.)
  unit/               — fast, no I/O, pure logic
  integration/        — in-process FastAPI app + mongomock + mocked externals
  webhooks/           — webhook payload + signature verification
  security/           — tenant isolation, auth, rate-limiting, input validation
  voice/              — pipecat pipeline tests with mocked frames
  e2e_in_process/     — full in-process flows with mocked externals

frontend/src/test/
  setup.ts            — jsdom shims (matchMedia, ResizeObserver)
  utils/              — render helpers, MSW server, mock-Clerk
  unit/               — non-DOM logic
  components/         — component tests
  pages/              — page-level tests via React Router
```

## Markers

| Marker | Meaning | Default run? |
|---|---|---|
| `unit` | Fast, no I/O. <100ms per test. | yes |
| `integration` | Requires the in-process FastAPI app + mongomock + mocked externals. | yes |
| `webhook` | Webhook payload + signature tests. | yes |
| `security` | Tenant isolation, auth, rate-limiting, input validation. | yes |
| `voice` | Pipecat pipeline tests with mocked frames. | yes |
| `e2e_in_process` | Full in-process flows with mocked externals. | yes |
| `live` | Hits real external APIs against a deployed backend. | **no** |
| `slow` | Takes >1 second. | yes |

`live` is excluded by default. The two pre-existing test files
(`test_ringai_api.py`, `test_test_mode.py`) are tagged `live` at collection
time and run only via `pytest --run-live`.

## How to add a new test

1. **Pick the right directory.** If the test reaches the FastAPI app, it
   belongs in `integration/`. If it tests one function with mocks for its
   collaborators, it belongs in `unit/`. If it tests cross-tenant safety, it
   belongs in `security/`.
2. **Read the module under test first.** Tests written from guesses tend to
   pin implementation details rather than behavior.
3. **Use factories, not inline dicts.** `make_restaurant(name="…")` keeps
   shape drift contained to one file when production schemas change.
4. **Mock at the boundary.** Never mock the function under test; mock its
   collaborators. For HTTP, use the `respx_mock` fixture from `conftest.py`.
5. **Name tests like `test_<unit>_<scenario>_<expected>`.** Example:
   `test_create_appointment_with_conflict_returns_409`.

## Mocking conventions

| External | How it's mocked |
|---|---|
| MongoDB | `mongomock-motor` via the `async_db` fixture. `server.db` is patched per test. |
| Gemini (REST and SDK) | Tests patch `gemini_service` module-level clients. Fixtures live in `backend/tests/fixtures/gemini_responses/*.json`. |
| Gemini Live (pipecat) | The pipecat `GeminiMultimodalLiveLLMService` is replaced by a stub frame source. |
| Telnyx | `respx_mock` on `api.telnyx.com`. Webhook payloads in `fixtures/telnyx_webhooks/`. |
| Stripe | `respx_mock` on `api.stripe.com`. Signed webhook events constructed in-test. |
| Clerk | `auth_helpers.verify_clerk_token` is monkeypatched to return deterministic claims. |
| Google Calendar | `respx_mock` on `googleapis.com`. Token + events fixtures provided. |
| Google Maps | `respx_mock` on `maps.googleapis.com`. |
| Square | `respx_mock` on `connect.squareup.com` and `connect.squareupsandbox.com`. |
| Clover | `respx_mock` on `*.clover.com`. |

The autouse `_block_unknown_outbound_http` fixture in `conftest.py` raises
on any unmocked outbound HTTP, so an accidental real call surfaces as a
visible test failure rather than a silent network round-trip.

## Updating Gemini response fixtures

When Gemini's output format changes:

1. Capture the new payload in a fresh dev call (or from production logs,
   stripped of PII).
2. Save it to `backend/tests/fixtures/gemini_responses/<descriptor>.json`
   with the smallest realistic example.
3. Update the tests that consume it. Use `syrupy` snapshots where the
   exact prompt or response shape is being pinned.

## Reading coverage reports

After any test run, HTML coverage is at:

- Backend: `test_reports/coverage_html/index.html`
- Frontend: `frontend/coverage/index.html`

Files not under `backend/tests/`, `backend/temp_*.py`, `backend/debug_*.py`
or `backend/seed_*.py` are tracked. Coverage drops more than 2 percentage
points fail PRs starting two weeks after the suite is merged (warning-only
during the initial window — see `.github/workflows/tests.yml`).

## Bisecting a failure

`pytest-randomly` randomises test execution order. If a test passes alone
but fails in the suite, get the seed from the run summary and reproduce:

```bash
pytest -p randomly --randomly-seed=<SEED> backend/tests/path::test_name
```

To check ordering hygiene more broadly:

```bash
pytest -p randomly --randomly-seed=last
```

## Discovering bugs

The suite never modifies production code to make a test pass. When a test
captures buggy behavior:

1. The first test pins the **current** (incorrect) behavior so the diff
   stays green.
2. A second test marked `@pytest.mark.xfail(strict=True, reason="…")`
   documents the **expected** behavior.
3. An entry is appended to [tests/FINDINGS.md](FINDINGS.md) with file,
   line, severity, symptom, expected, suggested fix.

When a bug is fixed in a separate change, the `xfail` marker is removed
and the pinned-bug test is updated.
