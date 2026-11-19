import pytest

import database.db as db
from database.db import init_db, seed_db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
ANALYTICS_HREF = b'href="/analytics"'


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


def _analytics_link_tag(body):
    start = body.index(ANALYTICS_HREF)
    tag_start = body.rfind(b"<a", 0, start)
    tag_end = body.index(b">", start)
    return body[tag_start:tag_end + 1]


def test_analytics_redirects_when_logged_out(client):
    resp = client.get("/analytics")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_analytics_logged_in_content_and_active_link(client):
    _login(client)
    resp = client.get("/analytics")
    assert resp.status_code == 200
    assert b"Advanced Analytics" in resp.data
    assert b"Coming Soon" in resp.data
    tag = _analytics_link_tag(resp.data)
    assert b"active" in tag
    assert b'aria-current="page"' in tag


def test_profile_has_analytics_link_not_active(client):
    _login(client)
    resp = client.get("/profile")
    assert resp.status_code == 200
    tag = _analytics_link_tag(resp.data)
    assert b"active" not in tag
    assert b"aria-current" not in tag


@pytest.mark.parametrize("path", ["/login", "/"])
def test_logged_out_pages_hide_analytics_link(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert ANALYTICS_HREF not in resp.data


@pytest.mark.parametrize(
    "path", ["/static/img/analytics-clock.svg", "/static/css/analytics.css"]
)
def test_analytics_static_assets_load(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    resp.close()
