# Duuutah AI — Test Findings

This file is the bug log discovered while building and running the automated
test suite. Each entry follows the template below. **The test suite never
fixes production code.** Bugs are recorded here for human triage.

## Template

```
## YYYY-MM-DD — <one-line summary>
- **File:** `backend/<file>.py`
- **Line(s):** N
- **Severity:** critical | high | medium | low
- **Symptom:** what's wrong (what tests observed)
- **Expected:** what should happen
- **Suggested fix:** one paragraph
- **Test:** `backend/tests/<path>::test_name`
```

Severity guide:
- **critical** — data loss, security breach, payment failure, customer harm
- **high** — feature broken for a significant slice of tenants
- **medium** — incorrect output in a specific scenario; workarounds exist
- **low** — cosmetic or low-impact edge case

## Findings

_None yet. Findings are appended in chronological order as later commits
add tests that surface them._
