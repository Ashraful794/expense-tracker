import calendar
import math
import os
import sqlite3
from datetime import date, datetime

from flask import (
    Flask,
    abort,
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
    CATEGORIES,
    create_user,
    delete_expense as delete_expense_row,
    get_category_breakdown,
    get_db,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_email,
    get_user_by_id,
    init_db,
    insert_expense,
    seed_db,
    update_expense,
)

app =Flask(__name__)
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


@app.route("/analytics")
def analytics():
    if _current_user() is None:
        session.clear()
        return redirect(url_for("login"))
    return render_template("analytics.html")


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

def _validate_expense_form(form):
    """Return (cleaned, error) for the add-expense form; first failure wins."""
    try:
        amount = float((form.get("amount") or "").strip())
    except ValueError:
        amount = None
    if amount is None or not math.isfinite(amount) or amount <= 0:
        return None, "Enter an amount greater than 0."

    category = form.get("category", "")
    if category not in CATEGORIES:
        return None, "Choose a valid category."

    expense_date = _parse_iso_date(form.get("date"))
    if expense_date is None:
        return None, "Enter a valid date."

    description = (form.get("description") or "").strip()
    if len(description) > 200:
        return None, "Description must be 200 characters or fewer."

    return {
        "amount": round(amount, 2),
        "category": category,
        "date": expense_date,
        "description": description or None,
    }, None


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user = _current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "GET":
        values = {"date": _today().isoformat()}
        return render_template(
            "add_expense.html", categories=CATEGORIES, values=values, error=None
        )

    cleaned, error = _validate_expense_form(request.form)
    if error is not None:
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            values=request.form,
            error=error,
        )

    insert_expense(
        user["id"],
        cleaned["amount"],
        cleaned["category"],
        cleaned["date"],
        cleaned["description"],
    )
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    user = _current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user["id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        values = {
            "amount": f"{expense['amount']:.2f}",
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        }
        return render_template(
            "edit_expense.html",
            expense=expense,
            categories=CATEGORIES,
            values=values,
            error=None,
        )

    cleaned, error = _validate_expense_form(request.form)
    if error is not None:
        return render_template(
            "edit_expense.html",
            expense=expense,
            categories=CATEGORIES,
            values=request.form,
            error=error,
        )

    updated = update_expense(
        id,
        user["id"],
        cleaned["amount"],
        cleaned["category"],
        cleaned["date"],
        cleaned["description"],
    )
    if not updated:
        abort(404)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    user = _current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if get_expense_by_id(id, user["id"]) is None:
        abort(404)

    if not delete_expense_row(id, user["id"]):
        abort(404)
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
