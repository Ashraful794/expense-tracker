import re
from pathlib import Path

import pytest

import database.db as db
from database.db import init_db, seed_db

ROOT = Path(__file__).resolve().parent.parent
DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_db()
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    return client.post(
        "/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )


def test_profile_redirects_when_logged_out(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_logged_out_redirect_lands_on_login(client):
    resp = client.get("/profile", follow_redirects=True)
    assert resp.status_code == 200
    assert b'name="password"' in resp.data


def test_profile_returns_200_when_logged_in(client):
    _login(client)
    assert client.get("/profile").status_code == 200


def test_profile_shows_user_card(client):
    _login(client)
    body = client.get("/profile").data
    assert b"Demo User" in body
    assert b"demo@spendly.com" in body
    assert b"DU" in body


def test_profile_shows_summary_stats(client):
    _login(client)
    body = client.get("/profile").data
    assert b"319.24" in body
    assert b"Bills" in body
    assert b"Transactions" in body


def test_profile_shows_transaction_rows(client):
    _login(client)
    body = client.get("/profile").data.decode()
    tbody = body.split("<tbody>")[1].split("</tbody>")[0]
    assert tbody.count("<tr>") >= 3
    assert tbody.count("profile-badge ") >= 3


def test_profile_shows_category_breakdown(client):
    _login(client)
    body = client.get("/profile").data.decode()
    assert body.count('class="profile-cat"') >= 3
    assert body.count("<progress") >= 3


def test_navbar_logged_in_shows_username_and_signout(client):
    _login(client)
    body = client.get("/profile").data
    assert b"Demo User" in body
    assert b'href="/logout"' in body
    assert b"Sign out" in body
    assert b"Sign in" not in body
    assert b"Get started" not in body


def test_navbar_logged_out_has_no_username(client):
    body = client.get("/login").data
    assert b"Sign in" in body
    assert b"Get started" in body
    assert b"nav-user" not in body


def test_profile_shows_the_logged_in_user_not_demo(client):
    db.create_user("Jane Roe", "jane@example.com", "password123")
    client.post(
        "/login", data={"email": "jane@example.com", "password": "password123"}
    )
    body = client.get("/profile").data
    assert b"Jane Roe" in body
    assert b"jane@example.com" in body
    assert b"JR" in body
    assert b"Demo User" not in body
    assert b"demo@spendly.com" not in body


def test_profile_with_deleted_user_session_redirects_to_login(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 99999
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


@pytest.mark.parametrize(
    "name, expected",
    [("Jane Roe", "JR"), ("madonna", "M"), ("  ada   lovelace  byron ", "AL")],
)
def test_initials(name, expected):
    from app import _initials

    assert _initials(name) == expected


def test_profile_template_has_no_hex_inline_style_or_hardcoded_urls():
    src = (ROOT / "templates" / "profile.html").read_text(encoding="utf-8")
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", src) is None
    assert "style=" not in src
    assert 'href="/' not in src


def test_profile_css_uses_tokens_only():
    css = (ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", css) is None
    assert "rgba" not in css
    assert "box-shadow" not in css


def test_profile_data_is_consistent():
    from app import PROFILE_CATEGORIES, PROFILE_STATS, PROFILE_TRANSACTIONS

    total = PROFILE_STATS["total_spent"]
    assert sum(t["amount"] for t in PROFILE_TRANSACTIONS) == pytest.approx(total)
    assert sum(c["total"] for c in PROFILE_CATEGORIES) == pytest.approx(total)
    assert sum(c["percent"] for c in PROFILE_CATEGORIES) == pytest.approx(100, abs=0.2)
    assert len(PROFILE_TRANSACTIONS) == PROFILE_STATS["transaction_count"]
    top = max(PROFILE_CATEGORIES, key=lambda c: c["total"])
    assert top["name"] == PROFILE_STATS["top_category"]
