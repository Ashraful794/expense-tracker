import pytest

import database.db as db
from database.db import init_db, seed_db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
GENERIC_ERROR = b"Invalid email or password."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_db()
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def _user_id(client):
    with client.session_transaction() as sess:
        return sess.get("user_id")


def test_get_login_renders_form(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b'name="email"' in resp.data
    assert b'name="password"' in resp.data
    assert b'action="/login"' in resp.data


def test_valid_login_sets_session_and_redirects_home(client):
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    assert isinstance(_user_id(client), int)


def test_login_email_is_trimmed_and_case_insensitive(client):
    resp = _login(client, "  Demo@Spendly.COM ", DEMO_PASSWORD)
    assert resp.status_code == 302
    assert _user_id(client) is not None


@pytest.mark.parametrize(
    "email,password",
    [(DEMO_EMAIL, "wrong-password"), ("nobody@example.com", DEMO_PASSWORD)],
)
def test_bad_credentials_flash_generic_error(client, email, password):
    resp = _login(client, email, password)
    assert resp.status_code == 200
    assert GENERIC_ERROR in resp.data
    assert _user_id(client) is None


def test_empty_post_does_not_500(client):
    resp = client.post("/login", data={})
    assert resp.status_code == 200
    assert GENERIC_ERROR in resp.data
    assert _user_id(client) is None


def test_failed_login_keeps_email_but_not_password(client):
    resp = _login(client, DEMO_EMAIL, "wrong-password")
    assert b'value="demo@spendly.com"' in resp.data
    assert b"wrong-password" not in resp.data


def test_logout_clears_session_and_redirects_home(client):
    _login(client)
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    assert _user_id(client) is None


def test_logout_is_not_the_stub_string(client):
    resp = client.get("/logout")
    assert b"coming in Step 3" not in resp.data


def test_logout_when_logged_out_is_harmless(client):
    resp = client.get("/logout")
    assert resp.status_code == 302
