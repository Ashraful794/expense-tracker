# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the existing `/profile` route so users can
narrow the transaction list, summary stats, and category breakdown to a specific
period. The filter is driven entirely by query-string parameters (`date_from` and
`date_to`) on `GET /profile`, requiring no new routes. A compact filter bar
with four quick-select presets ("This Month", "Last 3 Months", "Last 6 Months",
"All Time") and two `<input type="date">` fields lets users pick any custom range.
All three data sections (summary stats, recent transactions, category breakdown)
must respect the active date filter.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column must exist)
- Step 4: Profile page UI (template with all four sections must exist)
- Step 5: Backend connection (`get_summary_stats`, `get_recent_transactions`,
  `get_category_breakdown` in `database/db.py` must exist and be wired to
  the `/profile` route)

## Routes
No new routes. The existing `GET /profile` route is modified to read optional
query parameters:
- `date_from` — ISO date string `YYYY-MM-DD`, inclusive lower bound
- `date_to`   — ISO date string `YYYY-MM-DD`, inclusive upper bound

Both parameters are required to filter; a range needs a start and an end.
- Both valid and `date_from <= date_to`: the range is applied (equal dates give
  a single-day range).
- Both absent or malformed: the "All Time" (unfiltered) view, silently.
- Exactly one valid date (the other absent or malformed): flash "Please choose
  both a start and an end date." and show the unfiltered view.
- Either date after today: flash "Dates cannot be in the future." and show the
  unfiltered view. Today itself is allowed.
- `date_from > date_to`: flash "Start date must be before end date." and show
  the unfiltered view.

Checks run in this order: both dates present, not in the future, From <= To;
the first failure wins and flashes once. "Today" is the server's local date,
read once per request (`_today()` in `app.py`) and also sent to the template
as the `max` of both date inputs, so a user in another timezone may be off by
up to a day. "All Time" (bare `/profile`) is not validated and still lists any
future-dated rows, such as the demo data early in a month.

The route never errors out. The custom form also uses `required` on both date
inputs and a small vanilla-JS helper in `static/js/main.js` (keeps To >= From)
for immediate feedback; the server checks above are authoritative because URLs
can be typed by hand. The DB helpers themselves still accept a single bound and
use `>=` / `<=` rather than `BETWEEN`.

## Database changes
No database changes. The `expenses.date` column (`TEXT`, `YYYY-MM-DD`) already
supports `BETWEEN` comparison in SQLite.

## Templates
- **Modify**: `templates/profile.html`
  - Add a filter bar section above the summary stats row containing:
    - Four quick-select preset buttons: "This Month", "Last 3 Months",
      "Last 6 Months", "All Time" — each a link to `/profile` with the
      appropriate `date_from`/`date_to` query params
    - A custom range sub-form with two `<input type="date">` fields
      (`date_from`, `date_to`) and an "Apply" submit button
    - The currently active preset or custom range must be visually highlighted
      (active state on the button)
  - No structural changes to any existing section; only Jinja variables fed
    to them change when the filter is active

## Files to change
- `app.py`
  - In the `profile()` view: read `date_from` and `date_to` from
    `request.args`; validate they are well-formed ISO dates; pass them to each
    query helper; pass the validated values back to the template so the filter
    bar can reflect the active state
- `database/db.py` (CLAUDE.md: all DB logic lives here; Step 5 helpers are added in this step)
  - `get_summary_stats(user_id, date_from=None, date_to=None)` — add optional
    date-range params; when both are provided, add `AND date BETWEEN ? AND ?`
    to the `expenses` queries
  - `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None)` —
    same pattern; ordering and limit remain unchanged
  - `get_category_breakdown(user_id, date_from=None, date_to=None)` — same
    pattern; percentage recalculation logic remains unchanged
- `templates/profile.html` — add filter bar (see Templates section)
- `static/css/profile.css` — add styles for the filter bar and active-preset
  button state using CSS variables only

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format dates into SQL; use `?`
  placeholders even for the date-range bounds
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Date validation in `app.py`: attempt `datetime.strptime(value, "%Y-%m-%d")`;
  on `ValueError`, treat the param as absent. If only one of the two ends up
  valid, flash "Please choose both a start and an end date." and apply no filter
- Preset links must be generated with `url_for("profile", date_from=..., date_to=...)`
  — never hardcoded URL strings in the template
- When `date_from` and `date_to` are both absent, all three query helpers must
  behave identically to their Step 5 behaviour (unfiltered)
- If `date_from > date_to` after validation, treat both as absent (no filter)
  and flash a user-visible error message: "Start date must be before end date."
- The "All Time" preset must pass no query params (clean `/profile` URL)
- Preset date calculations (e.g. "This Month" → first day of current month)
  must be computed in `app.py`, not in the template

## Definition of done
- [ ] Visiting `/profile` with no query params returns the same data as Step 5
  (unfiltered, all expenses)
- [ ] Clicking "This Month" filters all three sections to the current calendar
  month only
- [ ] Clicking "Last 3 Months" filters to expenses in the 3-month window ending
  today
- [ ] Clicking "Last 6 Months" filters to expenses in the 6-month window ending
  today
- [ ] Clicking "All Time" removes any active filter and shows all expenses
- [ ] Submitting a custom date range with valid `date_from` and `date_to` shows
  only expenses within that range in all three sections
- [ ] Submitting a range where `date_from > date_to` shows a flash error and
  falls back to the unfiltered view
- [ ] Submitting a malformed date string (e.g. `date_from=not-a-date`) does not
  crash the app — it silently falls back to the unfiltered view
- [ ] Submitting only one date (From or To, via the form or a typed URL) shows
  the flash "Please choose both a start and an end date." and the unfiltered view
- [ ] In the browser, Apply is blocked while either date is empty, and the To
  picker cannot be set before From; From and To on the same day is allowed
- [ ] Neither date picker allows a date after today; a hand-typed URL with a
  future date shows the flash "Dates cannot be in the future." and the
  unfiltered view
- [ ] The active preset button or custom-range fields visually indicate which
  filter is currently applied
- [ ] All amounts continue to display the ₹ symbol regardless of the active filter
- [ ] A user with no expenses in the selected range sees ₹0.00 total spent, 0
  transactions, and an empty category breakdown — no errors