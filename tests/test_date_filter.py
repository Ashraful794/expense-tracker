from datetime import date, timedelta

import pytest

import database.db as db
from database.db import init_db, seed_db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

# Seed: first-of-current-month + offset -> amount (see database/db.py seed_db)
FIRST = date.today().replace(day=1)
# The app's "today" is pinned late in the month (after every seed expense) so
# results don't depend on the real date.
TODAY = FIRST + timedelta(days=27)


def _iso(offset):
    return (FIRST + timedelta(days=offset)).isoformat()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_db()
    import app as app_module

    monkeypatch.setattr(app_module, "_today", lambda: TODAY)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    return client


# ---------------------------------------------------------------- helpers

def test_unfiltered_stats(client):
    stats = db.get_summary_stats(1)
    assert stats["total_spent"] == pytest.approx(319.24)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_bounded_range(client):
    stats = db.get_summary_stats(1, _iso(0), _iso(3))
    assert stats["total_spent"] == pytest.approx(140.50)
    assert stats["transaction_count"] == 3
    assert stats["top_category"] == "Bills"
    rows = db.get_recent_transactions(1, date_from=_iso(0), date_to=_iso(3))
    assert len(rows) == 3
    assert len(db.get_category_breakdown(1, _iso(0), _iso(3))) == 3


def test_single_bounds(client):
    assert db.get_summary_stats(1, date_from=_iso(9))["transaction_count"] == 3
    assert db.get_summary_stats(1, date_to=_iso(1))["transaction_count"] == 2


def test_bounds_are_inclusive(client):
    assert db.get_summary_stats(1, _iso(3), _iso(3))["transaction_count"] == 1


def test_empty_range(client):
    far = (FIRST + timedelta(days=400)).isoformat()
    assert db.get_summary_stats(1, far, far) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }
    assert db.get_recent_transactions(1, date_from=far) == []
    assert db.get_category_breakdown(1, date_from=far) == []


def test_limit_respected(client):
    assert len(db.get_recent_transactions(1, limit=3)) == 3


def test_percentages_sum_to_100(client):
    cats = db.get_category_breakdown(1, _iso(0), _iso(5))
    assert sum(c["percent"] for c in cats) == pytest.approx(100, abs=0.2)


def test_other_users_expenses_excluded(client):
    other = db.create_user("Jane Roe", "jane@example.com", "password123")
    assert db.get_summary_stats(other)["transaction_count"] == 0
    assert db.get_recent_transactions(other) == []


def test_null_description_does_not_crash(client):
    conn = db.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date) VALUES (1, 1, 'Food', ?)",
        (_iso(0),),
    )
    conn.commit()
    conn.close()
    assert db.get_recent_transactions(1, date_from=_iso(0), date_to=_iso(0))[0][
        "description"
    ] in ("", "Lunch")


# ------------------------------------------------------------------ route

def test_no_params_unfiltered(logged_in):
    body = logged_in.get("/profile").data
    assert b"319.24" in body


def test_valid_range_filters_all_sections(logged_in):
    body = logged_in.get(
        f"/profile?date_from={_iso(0)}&date_to={_iso(3)}"
    ).data.decode()
    assert "140.50" in body
    assert "Electricity bill" in body
    assert "Pharmacy" not in body
    assert "Movie night" not in body


def test_malformed_bound_is_ignored(logged_in):
    resp = logged_in.get("/profile?date_from=not-a-date")
    assert resp.status_code == 200
    assert b"319.24" in resp.data


def test_malformed_from_with_valid_to_asks_for_both_dates(logged_in):
    body = logged_in.get(f"/profile?date_from=abc&date_to={_iso(1)}").data
    assert b"Please choose both a start and an end date." in body
    assert b"319.24" in body  # unfiltered


def test_reversed_range_flashes_and_is_unfiltered(logged_in):
    resp = logged_in.get(f"/profile?date_from={_iso(5)}&date_to={_iso(1)}")
    assert resp.status_code == 200
    assert b"Start date must be before end date." in resp.data
    assert b"319.24" in resp.data
    assert b"Start date must be before end date." not in logged_in.get("/profile").data


def test_empty_range_shows_zero_state(logged_in):
    body = logged_in.get(
        "/profile?date_from=1999-01-01&date_to=1999-01-31"
    ).data.decode()
    assert "৳0.00" in body
    assert "No transactions in this range." in body
    assert 'class="profile-cat"' not in body


def test_taka_symbol_under_filter(logged_in):
    body = logged_in.get(f"/profile?date_from={_iso(0)}&date_to={_iso(3)}").data
    assert "৳".encode() in body


def test_all_time_preset_is_bare_profile_and_active(logged_in):
    body = logged_in.get("/profile").data.decode()
    assert 'href="/profile"' in body
    assert body.count("profile-preset--active") == 1
    all_time = body.split("All Time")[0].rsplit("<a", 1)[1]
    assert "profile-preset--active" in all_time


def test_preset_links_carry_dates(logged_in):
    body = logged_in.get("/profile").data.decode()
    assert f"date_from={FIRST.isoformat()}" in body
    assert f"date_to={TODAY.isoformat()}" in body


def test_matching_preset_is_active(logged_in):
    today = TODAY.isoformat()
    body = logged_in.get(f"/profile?date_from={FIRST.isoformat()}&date_to={today}").data.decode()
    this_month = body.split("This Month")[0].rsplit("<a", 1)[1]
    assert "profile-preset--active" in this_month
    assert "profile-filter-form--active" not in body


def test_custom_range_highlights_form(logged_in):
    body = logged_in.get(f"/profile?date_from={_iso(0)}&date_to={_iso(3)}").data.decode()
    assert "profile-filter-form--active" in body
    assert f'value="{_iso(0)}"' in body


def test_logged_out_redirects(client):
    resp = client.get(f"/profile?date_from={_iso(0)}")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_sql_injection_string_ignored(logged_in):
    resp = logged_in.get("/profile?date_from=' OR 1=1 --")
    assert resp.status_code == 200
    assert b"319.24" in resp.data


# ---------------------------------------------------------- pure functions

def test_build_presets_fixed_date():
    from app import _build_presets

    preset_list, custom_active = _build_presets(date(2026, 11, 18))
    assert custom_active is False
    presets = {p["label"]: p for p in preset_list}
    assert presets["This Month"]["date_from"] == "2026-11-01"
    assert presets["Last 3 Months"]["date_from"] == "2026-08-18"
    assert presets["Last 6 Months"]["date_from"] == "2026-05-18"
    assert presets["All Time"]["date_from"] is None
    assert presets["All Time"]["date_to"] is None


def test_subtract_months_clamps_day():
    from app import _subtract_months

    assert _subtract_months(date(2026, 8, 31), 6) == date(2026, 2, 28)
    assert _subtract_months(date(2026, 1, 15), 3) == date(2025, 10, 15)
