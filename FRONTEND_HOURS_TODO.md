# Operating hours — split periods + kitchen last-call offset

Backend is fully implemented and backward compatible. The **settings** hours
editor (`frontend/src/pages/dashboard/settings/HoursTab.tsx`) is done. One piece
is intentionally left on the old single-period shape; see "Remaining" below.

## JSON the API now accepts/returns

`operating_hours` is keyed by lowercase weekday (`"monday"` … `"sunday"`). Each
day is one of two shapes — the backend reads **both**:

### New canonical shape (what the settings UI now writes)
```json
"monday": {
  "closed": false,
  "last_call_offset_minutes": 30,
  "periods": [
    { "open": "10:00", "close": "15:00" },
    { "open": "18:00", "close": "22:00" }
  ]
}
```
- `periods`: list of `{ "open": "HH:MM", "close": "HH:MM" }` (24h local time). One
  entry = normal day; multiple = split hours (e.g. lunch + dinner).
- `last_call_offset_minutes`: int ≥ 0, optional (default 0). Order-taking stops
  this many minutes before **each** period's close. Reservation/appointment slot
  generation ignores it (bookings use the posted close).
- `closed: true` → closed all day (periods ignored).

### Old shape (still valid — do not need to migrate)
```json
"monday": { "closed": false, "open": "09:00", "close": "21:00" }
```
Read as a single period with a 0-minute offset.

A partial-update `PATCH`/`PUT` of the config may send either shape per day; the
backend normalizes on read. Prefer sending the new shape on write.

## What HoursTab.tsx now does
- Reads either shape via `normalizeDayHours()` (`.../settings/constants.ts`).
- Per day: Closed toggle, a **Last call (min)** number input, and a list of
  time ranges with **Add time range** / remove-range (✕) controls.
- Always writes the new `{ closed, last_call_offset_minutes, periods }` shape.

## Remaining (deferred, non-blocking)
`frontend/src/pages/Onboarding.tsx` still uses its own inline single-period
editor and submits the **old** `{ closed, open, close }` shape. This is safe —
the backend reads it as one period, 0 offset — so new restaurants onboard fine
and owners add split hours / last-call afterward in Settings. To finish the UI
consistently, port the two HoursTab additions (multiple `periods` rows + the
`last_call_offset_minutes` input) into Onboarding's `updateHours`/render block
and submit the new shape there too.
