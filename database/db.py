import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
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


def get_user_by_email(email, db_path=None):
    """Return the user row matching the email, or None."""
    conn = get_db(db_path)
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()
