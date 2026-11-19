import os
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)


CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)


def get_db(db_path=None):
    """Return a SQLite connection with Row access and foreign keys enabled."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    """Create all tables if they do not already exist."""
    conn = get_db(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db(db_path=None):
    """Insert a demo user and sample expenses; no-op if users already exist."""
    conn = get_db(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cur.lastrowid

        first = date.today().replace(day=1)
        samples = [
            (0, 12.50, "Food", "Lunch"),
            (1, 8.00, "Transport", "Bus pass top-up"),
            (3, 120.00, "Bills", "Electricity bill"),
            (5, 45.00, "Health", "Pharmacy"),
            (7, 30.00, "Entertainment", "Movie night"),
            (9, 65.99, "Shopping", "New shoes"),
            (11, 15.00, "Other", "Miscellaneous"),
            (13, 22.75, "Food", "Groceries"),
        ]
        rows = [
            (user_id, amount, category, (first + timedelta(days=offset)).isoformat(), desc)
            for offset, amount, category, desc in samples
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def create_user(name, email, password, db_path=None):
    """Insert a new user with a hashed password and return the new user id.

    Raises sqlite3.IntegrityError if the email is already registered.
    """
    conn = get_db(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_expense(user_id, amount, category, date, description, db_path=None):
    """Insert an expense for the user and return the new expense id.

    Callers validate the values; this helper only persists them.
    """
    conn = get_db(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id, db_path=None):
    """Return the expense as a dict if it belongs to the user, else None."""
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_expense(
    expense_id, user_id, amount, category, date, description, db_path=None
):
    """Update the user's expense and return the number of rows changed.

    Scoped by user_id so one user can never modify another's expense; returns
    0 (without raising) when no matching row exists.
    """
    conn = get_db(db_path)
    try:
        cur = conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, "
            "description = ? WHERE id = ? AND user_id = ?",
            (amount, category, date, description, expense_id, user_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_user_by_id(user_id, db_path=None):
    """Return the user row matching the id, or None."""
    conn = get_db(db_path)
    try:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()


def _date_clause(date_from, date_to):
    """Return (sql_fragment, params) for optional inclusive date bounds.

    Only fixed SQL fragments are concatenated; values always go in params.
    """
    sql, params = "", []
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    return sql, params


def _fetch_expenses(select_sql, user_id, date_from, date_to, tail_sql="",
                    tail_params=(), db_path=None):
    """Run a user-scoped, optionally date-filtered expenses query.

    select_sql and tail_sql are fixed SQL strings written in this module;
    every value (user id, dates, limit) is passed as a parameter.
    """
    clause, params = _date_clause(date_from, date_to)
    conn = get_db(db_path)
    try:
        return conn.execute(
            select_sql + " WHERE user_id = ?" + clause + " " + tail_sql,
            [user_id, *params, *tail_params],
        ).fetchall()
    finally:
        conn.close()


def _slugify(category):
    """Return a CSS-class-safe slug for a category name, e.g. 'Food' -> 'food'."""
    return category.lower().replace(" ", "-")


def _format_date(iso_date):
    """Format 'YYYY-MM-DD' as '14 Nov 2026' (no zero padding); raw on failure."""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return iso_date
    return f"{d.day} {d:%b %Y}"


def get_summary_stats(user_id, date_from=None, date_to=None, db_path=None):
    """Return total spent, transaction count and top category for the range."""
    # One grouped query; ordering matches get_category_breakdown so the top
    # category is always that function's first row.
    rows = _fetch_expenses(
        "SELECT category, SUM(amount) AS total, COUNT(*) AS n FROM expenses",
        user_id, date_from, date_to,
        "GROUP BY category ORDER BY total DESC, category",
        db_path=db_path,
    )
    return {
        "total_spent": round(sum(r["total"] for r in rows), 2),
        "transaction_count": sum(r["n"] for r in rows),
        "top_category": rows[0]["category"] if rows else "—",
    }


def get_recent_transactions(
    user_id, limit=10, date_from=None, date_to=None, db_path=None
):
    """Return the newest expenses in the range, formatted for display."""
    rows = _fetch_expenses(
        "SELECT id, date, description, category, amount FROM expenses",
        user_id, date_from, date_to,
        "ORDER BY date DESC, id DESC LIMIT ?", (limit,),
        db_path=db_path,
    )
    return [
        {
            "id": r["id"],
            "date": _format_date(r["date"]),
            "description": r["description"] or "",
            "category": r["category"],
            "slug": _slugify(r["category"]),
            "amount": r["amount"],
        }
        for r in rows
    ]


def get_category_breakdown(user_id, date_from=None, date_to=None, db_path=None):
    """Return per-category totals and percentage share, highest first."""
    rows = _fetch_expenses(
        "SELECT category, SUM(amount) AS total FROM expenses",
        user_id, date_from, date_to,
        "GROUP BY category ORDER BY total DESC, category",
        db_path=db_path,
    )
    grand = sum(r["total"] for r in rows)
    return [
        {
            "name": r["category"],
            "slug": _slugify(r["category"]),
            "total": round(r["total"], 2),
            "percent": round(r["total"] / grand * 100, 1) if grand else 0.0,
        }
        for r in rows
    ]


def get_user_by_email(email, db_path=None):
    """Return the user row matching the email, or None."""
    conn = get_db(db_path)
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()
