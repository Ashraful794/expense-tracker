import sqlite3
from contextlib import closing
from datetime import date

import pytest
from werkzeug.security import check_password_hash

from database.db import get_db, init_db, seed_db

CATEGORIES = {"Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"}


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def seeded(db_path):
    init_db(db_path)
    seed_db(db_path)
    return db_path


def test_schema(db_path):
    init_db(db_path)
    with closing(get_db(db_path)) as conn:
        users = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        expenses = {r["name"] for r in conn.execute("PRAGMA table_info(expenses)")}
        fks = conn.execute("PRAGMA foreign_key_list(expenses)").fetchall()
    assert users == {"id", "name", "email", "password_hash", "created_at"}
    assert expenses == {"id", "user_id", "amount", "category", "date", "description", "created_at"}
    assert fks[0]["table"] == "users"


def test_init_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)


def test_seed_contents(seeded):
    with closing(get_db(seeded)) as conn:
        user = conn.execute("SELECT * FROM users").fetchall()
        expenses = conn.execute("SELECT * FROM expenses").fetchall()
    assert len(user) == 1
    assert user[0]["email"] == "demo@spendly.com"
    assert user[0]["password_hash"] != "demo123"
    assert check_password_hash(user[0]["password_hash"], "demo123")
    assert len(expenses) == 8
    assert {e["category"] for e in expenses} == CATEGORIES
    month = date.today().strftime("%Y-%m")
    assert all(e["date"].startswith(month) for e in expenses)


def test_seed_not_duplicated(seeded):
    seed_db(seeded)
    with closing(get_db(seeded)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 8


def test_foreign_key_enforced(seeded):
    with closing(get_db(seeded)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
                (9999, 1.0, "Food", "2026-01-01"),
            )


def test_unique_email(seeded):
    with closing(get_db(seeded)) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other", "demo@spendly.com", "x"),
            )


def test_get_user_by_id(seeded):
    from database.db import get_user_by_email, get_user_by_id

    demo = get_user_by_email("demo@spendly.com", seeded)
    row = get_user_by_id(demo["id"], seeded)
    assert row["email"] == "demo@spendly.com"
    assert get_user_by_id(99999, seeded) is None
