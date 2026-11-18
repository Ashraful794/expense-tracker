import calendar
import os
import sqlite3
from datetime import date, datetime

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_category_breakdown,
    get_db,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
# The fallback key is for local development only; set SECRET_KEY in production.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


def _is_valid_email(email):
    """Minimal check: one '@' with text on both sides and no whitespace."""
    local, _, domain = email.partition("@")
    return bool(local) and bool(domain) and "@" not in domain and not any(
        ch.isspace() for ch in email
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = None
    if not name:
        error = "Name is required."
    elif not email:
        error = "Email is required."
    elif not _is_valid_email(email):
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."

    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = "An account with that email already exists"

    if error is not None:
        return render_template("register.html", error=error, name=name, email=email)
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.")
        return render_template("login.html", email=email)

    session.clear()
    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


def _current_user():
    """Return the logged-in user's row (cached for the request), or None."""
    if "current_user" not in g:
        user_id = session.get("user_id")
        g.current_user = get_user_by_id(user_id) if user_id else None
    return g.current_user


def _initials(name):
    """Return up to two uppercase initials from a display name."""
    return "".join(word[0] for word in name.split()[:2]).upper()


def _member_since(created_at):
    """Format a SQLite 'YYYY-MM-DD HH:MM:SS' timestamp as 'November 2026'."""
    try:
        return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")
    except (TypeError, ValueError):
        return ""


@app.context_processor
def inject_nav_user():
    user = _current_user()
    return {"nav_user_name": user["name"]} if user else {}


def _parse_iso_date(value):
    """Return a normalised 'YYYY-MM-DD' string, or None if absent/malformed."""
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _subtract_months(d, months):
    """Return d shifted back by whole months, clamping to the month's last day."""
    # Count months since year 0 so the borrow across years is one divmod.
    year, month_index = divmod(d.year * 12 + (d.month - 1) - months, 12)
    month = month_index + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _build_presets(today, date_from=None, date_to=None):
    """Return the filter presets plus whether the custom range is active.

    Each preset is a dict with label, date_from, date_to and active (True when
    it matches the current filter). The custom form is active when a filter is
    set that matches no preset.
    """
    today_iso = today.isoformat()
    ranges = [
        ("This Month", today.replace(day=1).isoformat(), today_iso),
        ("Last 3 Months", _subtract_months(today, 3).isoformat(), today_iso),
        ("Last 6 Months", _subtract_months(today, 6).isoformat(), today_iso),
        ("All Time", None, None),
    ]
    presets = [
        {
            "label": label,
            "date_from": start,
            "date_to": end,
            "active": (start, end) == (date_from, date_to),
        }
        for label, start, end in ranges
    ]
    custom_active = bool(date_from or date_to) and not any(
        p["active"] for p in presets
    )
    return presets, custom_active


def _today():
    """Return today's (server-local) date; tests patch this for fixed dates."""
    return date.today()


def _read_date_filter(args, today):
    """Return validated (date_from, date_to) from query args.

    Both dates are required and may not be after today. A single valid date,
    a future date or a reversed range flashes an error and yields no filter;
    equal dates are allowed (one day).
    """
    date_from = _parse_iso_date(args.get("date_from"))
    date_to = _parse_iso_date(args.get("date_to"))
    if bool(date_from) != bool(date_to):
        flash("Please choose both a start and an end date.")
        return None, None
    if date_from and date_to and max(date_from, date_to) > today.isoformat():
        flash("Dates cannot be in the future.")
        return None, None
    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.")
        return None, None
    return date_from, date_to


@app.route("/profile")
def profile():
    user = _current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    today = _today()
    date_from, date_to = _read_date_filter(request.args, today)
    presets, custom_active = _build_presets(today, date_from, date_to)

    return render_template(
        "profile.html",
        user={
            "name": user["name"],
            "email": user["email"],
            "initials": _initials(user["name"]),
            "member_since": _member_since(user["created_at"]),
        },
        stats=get_summary_stats(user["id"], date_from, date_to),
        transactions=get_recent_transactions(user["id"], date_from=date_from, date_to=date_to),
        categories=get_category_breakdown(user["id"], date_from, date_to),
        presets=presets,
        date_from=date_from,
        date_to=date_to,
        custom_active=custom_active,
        max_date=today.isoformat(),
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
