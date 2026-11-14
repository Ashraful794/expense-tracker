# Spec: Registration

## Overview
Make the existing `/register` page functional. A visitor submits name, email and password; the server validates the input, hashes the password, stores a new row in `users`, and redirects to the login page. This is Step 2 of the Spendly roadmap: it builds on the Step 1 data layer and creates the accounts that login/logout (Step 3) and every later feature depend on.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`).

## Routes
- `GET /register` — render the registration form (already exists) — public
- `POST /register` — validate form, create user, redirect to `/login` on success; re-render form with an error message (HTTP 200) on validation failure — public

`/login`, `/logout` and other stubs are untouched. Registration does NOT log the user in (sessions belong to Step 3).

## Database changes
No schema changes. The existing `users` table already has `name`, `email` (UNIQUE, NOT NULL) and `password_hash`.

New helper functions in `database/db.py` (verified: neither exists today):
- `create_user(name, email, password)` — hashes the password with `generate_password_hash`, inserts the row with a parameterised query, returns the new user id. Raises `sqlite3.IntegrityError` on duplicate email.
- `get_user_by_email(email)` — returns the matching `sqlite3.Row` or `None`.

## Templates
- **Create:** none
- **Modify:** `templates/register.html`
  - Change the form `action="/register"` to `action="{{ url_for('register') }}"`
  - Re-populate `name` and `email` inputs with the submitted values after a validation error (never re-populate password)
  - Keep the existing `{% if error %}` block for displaying errors

## Files to change
- `app.py` — change `/register` to accept `GET` and `POST`; add form handling; import `request`, `redirect`, `url_for` and the new db helpers
- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `templates/register.html` — as described above

## Files to create
- `tests/test_registration.py` — pytest tests for the registration flow (uses a temporary DB, not the real `expense_tracker.db`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py`, not in the route; the route only reads the form, calls helpers, and renders/redirects
- Server-side validation (do not rely on HTML `required`):
  - name: non-empty after `strip()`
  - email: non-empty, lower-cased and stripped, contains `@` with text on both sides
  - password: minimum 8 characters (matches the form placeholder)
- Duplicate email: catch `sqlite3.IntegrityError` (or check `get_user_by_email` first) and show "An account with that email already exists" — no 500 error
- Use `url_for()` for the redirect and every link; no hardcoded URLs
- Do not implement login, logout, sessions, or any other stub route
- Keep port 5001

## Definition of done
- [ ] `GET /register` renders the form without errors
- [ ] Submitting valid name/email/password creates a row in `users` and redirects to `/login`
- [ ] The stored `password_hash` is a werkzeug hash, not the plaintext password
- [ ] Registering with an already-used email (including different letter case, e.g. `Demo@Spendly.com`) re-renders the form with an error and creates no new row
- [ ] Empty name, invalid email, or password shorter than 8 characters each show a clear error and create no row
- [ ] After a validation error, the name and email fields keep their values and the password field is empty
- [ ] Form `action` uses `url_for('register')`
- [ ] No 500 errors for any of the above cases
- [ ] `pytest tests/test_registration.py` passes
- [ ] App still starts on port 5001 and existing pages (`/`, `/login`, `/terms`, `/privacy`) still load
