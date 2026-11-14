import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_db,
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


# Hardcoded profile data (Step 4). Mirrors seed_db(); Step 5 replaces these
# constants with real database queries. Only the user identity is real.
PROFILE_STATS = {
    "total_spent": 319.24,
    "transaction_count": 8,
    "top_category": "Bills",
}

PROFILE_TRANSACTIONS = [  # newest first
    {"date": "14 Nov 2026", "description": "Groceries", "category": "Food", "slug": "food", "amount": 22.75},
    {"date": "12 Nov 2026", "description": "Miscellaneous", "category": "Other", "slug": "other", "amount": 15.00},
    {"date": "10 Nov 2026", "description": "New shoes", "category": "Shopping", "slug": "shopping", "amount": 65.99},
    {"date": "8 Nov 2026", "description": "Movie night", "category": "Entertainment", "slug": "entertainment", "amount": 30.00},
    {"date": "6 Nov 2026", "description": "Pharmacy", "category": "Health", "slug": "health", "amount": 45.00},
    {"date": "4 Nov 2026", "description": "Electricity bill", "category": "Bills", "slug": "bills", "amount": 120.00},
    {"date": "2 Nov 2026", "description": "Bus pass top-up", "category": "Transport", "slug": "transport", "amount": 8.00},
    {"date": "1 Nov 2026", "description": "Lunch", "category": "Food", "slug": "food", "amount": 12.50},
]

PROFILE_CATEGORIES = [  # highest total first
    {"name": "Bills", "slug": "bills", "total": 120.00, "percent": 37.6},
    {"name": "Shopping", "slug": "shopping", "total": 65.99, "percent": 20.7},
    {"name": "Health", "slug": "health", "total": 45.00, "percent": 14.1},
    {"name": "Food", "slug": "food", "total": 35.25, "percent": 11.0},
    {"name": "Entertainment", "slug": "entertainment", "total": 30.00, "percent": 9.4},
    {"name": "Other", "slug": "other", "total": 15.00, "percent": 4.7},
    {"name": "Transport", "slug": "transport", "total": 8.00, "percent": 2.5},
]


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


@app.route("/profile")
def profile():
    user = _current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login"))
    return render_template(
        "profile.html",
        user={
            "name": user["name"],
            "email": user["email"],
            "initials": _initials(user["name"]),
            "member_since": _member_since(user["created_at"]),
        },
        stats=PROFILE_STATS,
        transactions=PROFILE_TRANSACTIONS,
        categories=PROFILE_CATEGORIES,
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
