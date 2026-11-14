import sqlite3
from contextlib import closing

import pytest
from werkzeug.security import check_password_hash

import database.db as db
from database.db import create_user, get_db, get_user_by_email, init_db, seed_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_db()
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _count_users():
    with closing(get_db()) as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def _post(client, name="Alice", email="alice@example.com", password="password1"):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def test_get_register_ok(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b'action="/register"' in response.data


def test_register_success_redirects_to_login(client):
    response = _post(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_register_stores_hashed_password(client):
    _post(client, password="s3cretpass")
    user = get_user_by_email("alice@example.com")
    assert user["name"] == "Alice"
    assert user["password_hash"] != "s3cretpass"
    assert check_password_hash(user["password_hash"], "s3cretpass")


def test_email_is_normalised(client):
    _post(client, email="  New@Example.COM ")
    assert get_user_by_email("new@example.com") is not None


@pytest.mark.parametrize("email", ["demo@spendly.com", "Demo@Spendly.com"])
def test_duplicate_email_rejected(client, email):
    before = _count_users()
    response = _post(client, email=email)
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert _count_users() == before


def test_duplicate_after_registration(client):
    before = _count_users()
    _post(client)
    response = _post(client)
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert _count_users() == before + 1


@pytest.mark.parametrize(
    "name,email,password,message",
    [
        ("", "a@b.com", "password1", b"Name is required."),
        ("   ", "a@b.com", "password1", b"Name is required."),
        ("Al", "", "password1", b"Email is required."),
        ("Al", "noatsign", "password1", b"valid email"),
        ("Al", "@x.com", "password1", b"valid email"),
        ("Al", "a@", "password1", b"valid email"),
        ("Al", "a@b@c.com", "password1", b"valid email"),
        ("Al", "a b@c.com", "password1", b"valid email"),
        ("Al", "a@b.com", "short12", b"at least 8 characters"),
    ],
)
def test_invalid_input_rejected(client, name, email, password, message):
    before = _count_users()
    response = _post(client, name=name, email=email, password=password)
    assert response.status_code == 200
    assert message in response.data
    assert _count_users() == before


def test_password_exactly_eight_chars_ok(client):
    assert _post(client, password="12345678").status_code == 302


def test_values_repopulated_but_not_password(client):
    response = _post(client, password="short12")
    assert b'value="Alice"' in response.data
    assert b'value="alice@example.com"' in response.data
    assert b"short12" not in response.data


def test_repopulated_values_are_escaped(client):
    response = _post(client, name='"><script>x</script>', password="short12")
    assert b"<script>x</script>" not in response.data


def test_empty_post_no_server_error(client):
    response = client.post("/register", data={})
    assert response.status_code == 200
    assert b"Name is required." in response.data


def test_create_user_duplicate_raises(client):
    create_user("A", "dup@example.com", "password1")
    with pytest.raises(sqlite3.IntegrityError):
        create_user("B", "dup@example.com", "password2")


def test_get_user_by_email_missing_returns_none(client):
    assert get_user_by_email("nobody@example.com") is None


@pytest.mark.parametrize("path", ["/", "/login", "/terms", "/privacy"])
def test_existing_pages_load(client, path):
    assert client.get(path).status_code == 200
