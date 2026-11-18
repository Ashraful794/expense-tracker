"""Tests for Step 6: date-range filter on GET /profile.

Based on .claude/specs/06-date-filter.md. Seed expenses (demo user) are dated
first-of-current-month + offsets 0,1,3,5,7,9,11,13:

    +0  12.50  Food           Lunch
    +1   8.00  Transport      Bus pass top-up
    +3 120.00  Bills          Electricity bill
    +5  45.00  Health         Pharmacy
    +7  30.00  Entertainment  Movie night
    +9  65.99  Shopping       New shoes
    +11 15.00  Other          Miscellaneous
    +13 22.75  Food           Groceries
"""
import re
from datetime import date, timedelta

import pytest

import database.db as db
from database.db import init_db, seed_db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
REVERSED_MSG = b"Start date must be before end date."
ONE_BOUND_MSG = b"Please choose both a start and an end date."

FIRST = date.today().replace(day=1)
# The app's "today" is pinned so results don't depend on the real date: late
# in the month, after every seed expense (offsets 0-13).
TODAY = FIRST + timedelta(days=27)
FUTURE_MSG = b"Dates cannot be in the future."

DESCRIPTIONS = {
    0: "Lunch",
    1: "Bus pass top-up",
    3: "Electricity bill",
    5: "Pharmacy",
    7: "Movie night",
    9: "New shoes",
    11: "Miscellaneous",
    13: "Groceries",
}


def d(offset):
    """ISO date string for first-of-month + offset days."""
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


def _login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def _get(client, **params):
    return client.get("/profile", query_string=params)


def _body(client, **params):
    resp = _get(client, **params)
    assert resp.status_code == 200
    return resp.data.decode()


def _assert_unfiltered(body):
    """All seed descriptions, total and count must be present (Step 5 view)."""
    for desc in DESCRIPTIONS.values():
        assert desc in body, f"{desc!r} missing from unfiltered view"
    assert "319.24" in body, "Expected full total 319.24 in unfiltered view"


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_filtered_profile_redirects_to_login_when_logged_out(self, client):
        resp = _get(client, date_from=d(0), date_to=d(3))
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")

    def test_malformed_filter_logged_out_still_redirects(self, client):
        resp = _get(client, date_from="not-a-date")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# Unfiltered behaviour (Step 5 parity)                                #
# ------------------------------------------------------------------ #

class TestUnfiltered:
    def test_no_params_shows_all_expenses(self, client):
        _login(client)
        _assert_unfiltered(_body(client))

    def test_no_params_shows_no_error_flash(self, client):
        _login(client)
        resp = _get(client)
        assert REVERSED_MSG not in resp.data

    def test_no_params_shows_rupee_symbol(self, client):
        _login(client)
        assert "₹" in _body(client)

    def test_empty_params_fall_back_to_unfiltered(self, client):
        _login(client)
        _assert_unfiltered(_body(client, date_from="", date_to=""))


# ------------------------------------------------------------------ #
# Custom range happy paths                                            #
# ------------------------------------------------------------------ #

class TestCustomRange:
    def test_range_filters_transactions(self, client):
        _login(client)
        body = _body(client, date_from=d(0), date_to=d(3))
        for off in (0, 1, 3):
            assert DESCRIPTIONS[off] in body, f"offset {off} should be included"
        for off in (5, 7, 9, 11, 13):
            assert DESCRIPTIONS[off] not in body, f"offset {off} should be excluded"

    def test_range_filters_summary_total(self, client):
        _login(client)
        body = _body(client, date_from=d(0), date_to=d(3))
        # 12.50 + 8.00 + 120.00
        assert "140.50" in body
        assert "319.24" not in body

    def test_range_filters_transaction_count(self, client):
        _login(client)
        body = _body(client, date_from=d(0), date_to=d(3))
        assert re.search(r">\s*3\s*<", body), "Expected a transaction count of 3"

    def test_range_filters_category_breakdown(self, client):
        _login(client)
        body = _body(client, date_from=d(0), date_to=d(3))
        for cat in ("Food", "Transport", "Bills"):
            assert cat in body
        for cat in ("Shopping", "Entertainment", "Health"):
            assert cat not in body, f"{cat} should not appear in filtered view"

    def test_middle_range_excludes_both_ends(self, client):
        _login(client)
        body = _body(client, date_from=d(5), date_to=d(9))
        for off in (5, 7, 9):
            assert DESCRIPTIONS[off] in body
        for off in (0, 1, 3, 11, 13):
            assert DESCRIPTIONS[off] not in body
        # 45.00 + 30.00 + 65.99
        assert "140.99" in body

    def test_bounds_are_inclusive_single_day(self, client):
        _login(client)
        body = _body(client, date_from=d(3), date_to=d(3))
        assert DESCRIPTIONS[3] in body
        assert "120.00" in body
        for off in (0, 1, 5, 7, 9, 11, 13):
            assert DESCRIPTIONS[off] not in body

    def test_lower_bound_inclusive_upper_bound_exclusive_neighbour(self, client):
        _login(client)
        body = _body(client, date_from=d(1), date_to=d(2))
        assert DESCRIPTIONS[1] in body
        assert DESCRIPTIONS[0] not in body
        assert DESCRIPTIONS[3] not in body

    def test_range_covering_everything_matches_unfiltered(self, client):
        _login(client)
        body = _body(client, date_from=d(-400), date_to=TODAY.isoformat())
        _assert_unfiltered(body)

    def test_range_amounts_keep_rupee_symbol(self, client):
        _login(client)
        assert "₹" in _body(client, date_from=d(0), date_to=d(3))

    def test_filter_does_not_modify_database(self, client):
        _login(client)
        conn = db.get_db()
        before = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        _get(client, date_from=d(0), date_to=d(3))
        conn = db.get_db()
        after = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert before == after == 8


# ------------------------------------------------------------------ #
# Empty range                                                         #
# ------------------------------------------------------------------ #

class TestEmptyRange:
    def test_range_with_no_expenses_returns_200(self, client):
        _login(client)
        assert _get(client, date_from="1999-01-01", date_to="1999-12-31").status_code == 200

    def test_range_with_no_expenses_shows_zero_total(self, client):
        _login(client)
        body = _body(client, date_from="1999-01-01", date_to="1999-12-31")
        assert "₹0.00" in body
        assert "319.24" not in body

    def test_range_with_no_expenses_hides_all_transactions(self, client):
        _login(client)
        body = _body(client, date_from="1999-01-01", date_to="1999-12-31")
        for desc in DESCRIPTIONS.values():
            assert desc not in body

    def test_range_with_no_expenses_has_empty_category_breakdown(self, client):
        _login(client)
        body = _body(client, date_from="1999-01-01", date_to="1999-12-31")
        for cat in ("Shopping", "Entertainment", "Health", "Bills", "Transport"):
            assert cat not in body

    def test_user_without_expenses_sees_zero_in_any_range(self, client):
        db.create_user("Empty User", "empty@example.com", "password123")
        _login(client, "empty@example.com", "password123")
        body = _body(client, date_from=d(0), date_to=d(3))
        assert "₹0.00" in body
        for desc in DESCRIPTIONS.values():
            assert desc not in body


# ------------------------------------------------------------------ #
# User isolation                                                      #
# ------------------------------------------------------------------ #

class TestIsolation:
    def test_filter_only_includes_own_expenses(self, client):
        other_id = db.create_user("Other Person", "other@example.com", "password123")
        conn = db.get_db()
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (other_id, 999.00, "Food", d(0), "SecretOtherUserExpense"),
        )
        conn.commit()
        conn.close()
        _login(client)
        body = _body(client, date_from=d(0), date_to=d(3))
        assert "SecretOtherUserExpense" not in body
        assert "140.50" in body


# ------------------------------------------------------------------ #
# Reversed range                                                      #
# ------------------------------------------------------------------ #

class TestReversedRange:
    def test_reversed_range_flashes_error(self, client):
        _login(client)
        resp = _get(client, date_from=d(5), date_to=d(1))
        assert resp.status_code == 200
        assert REVERSED_MSG in resp.data, "Expected reversed-range flash message"

    def test_reversed_range_falls_back_to_unfiltered(self, client):
        _login(client)
        _assert_unfiltered(_body(client, date_from=d(5), date_to=d(1)))

    def test_flash_not_repeated_on_next_request(self, client):
        _login(client)
        _get(client, date_from=d(5), date_to=d(1))
        resp = _get(client)
        assert REVERSED_MSG not in resp.data

    def test_equal_dates_are_not_an_error(self, client):
        _login(client)
        resp = _get(client, date_from=d(3), date_to=d(3))
        assert REVERSED_MSG not in resp.data

    def test_valid_range_has_no_error_flash(self, client):
        _login(client)
        resp = _get(client, date_from=d(0), date_to=d(3))
        assert REVERSED_MSG not in resp.data


# ------------------------------------------------------------------ #
# Malformed / partial input                                           #
# ------------------------------------------------------------------ #

MALFORMED = [
    "not-a-date",
    "2026-13-45",
    "2026-02-30",
    "31/12/2026",
    "2026/01/01",
    "20260101",
    "2026-1-1x",
    "'; DROP TABLE expenses; --",
    "<script>alert(1)</script>",
    " ",
    "9" * 500,
]


class TestMalformedInput:
    @pytest.mark.parametrize("bad", MALFORMED)
    def test_malformed_date_from_does_not_crash(self, client, bad):
        _login(client)
        assert _get(client, date_from=bad).status_code == 200

    @pytest.mark.parametrize("bad", MALFORMED)
    def test_malformed_date_to_does_not_crash(self, client, bad):
        _login(client)
        assert _get(client, date_to=bad).status_code == 200

    @pytest.mark.parametrize("bad", MALFORMED)
    def test_both_malformed_fall_back_to_unfiltered(self, client, bad):
        _login(client)
        _assert_unfiltered(_body(client, date_from=bad, date_to=bad))

    def test_malformed_date_from_with_valid_date_to_asks_for_both(self, client):
        _login(client)
        resp = _get(client, date_from="not-a-date", date_to=d(1))
        assert ONE_BOUND_MSG in resp.data
        _assert_unfiltered(resp.data.decode())

    def test_valid_date_from_with_malformed_date_to_asks_for_both(self, client):
        _login(client)
        resp = _get(client, date_from=d(5), date_to="not-a-date")
        assert ONE_BOUND_MSG in resp.data
        _assert_unfiltered(resp.data.decode())

    def test_malformed_date_alone_shows_no_flash(self, client):
        _login(client)
        resp = _get(client, date_from="not-a-date")
        assert ONE_BOUND_MSG not in resp.data
        assert REVERSED_MSG not in resp.data

    def test_malformed_date_shows_no_reversed_error(self, client):
        _login(client)
        resp = _get(client, date_from="not-a-date", date_to=d(3))
        assert REVERSED_MSG not in resp.data

    def test_sql_injection_attempt_leaves_data_intact(self, client):
        _login(client)
        _get(client, date_from="2026-01-01' OR '1'='1", date_to="x'; DROP TABLE expenses;--")
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count == 8, "expenses table must be untouched by injection attempt"

    def test_only_date_from_is_rejected_with_flash(self, client):
        _login(client)
        resp = _get(client, date_from=d(5))
        assert resp.status_code == 200
        assert ONE_BOUND_MSG in resp.data
        assert REVERSED_MSG not in resp.data
        _assert_unfiltered(resp.data.decode())

    def test_only_date_to_is_rejected_with_flash(self, client):
        _login(client)
        resp = _get(client, date_to=d(1))
        assert resp.status_code == 200
        assert ONE_BOUND_MSG in resp.data
        _assert_unfiltered(resp.data.decode())

    def test_no_dates_and_valid_range_show_no_one_bound_flash(self, client):
        _login(client)
        assert ONE_BOUND_MSG not in _get(client).data
        assert ONE_BOUND_MSG not in _get(client, date_from=d(0), date_to=d(3)).data

    def test_one_bound_flash_not_repeated(self, client):
        _login(client)
        _get(client, date_from=d(5))
        assert ONE_BOUND_MSG not in _get(client).data

    def test_reversed_range_shows_only_reversed_message(self, client):
        _login(client)
        resp = _get(client, date_from=d(5), date_to=d(1))
        assert REVERSED_MSG in resp.data
        assert ONE_BOUND_MSG not in resp.data

    def test_date_inputs_are_required_and_js_is_loaded(self, client):
        _login(client)
        body = _body(client)
        for name in ("date_from", "date_to"):
            tag = re.search(r'<input[^>]*name="%s"[^>]*>' % name, body).group(0)
            assert "required" in tag
        assert "js/main.js" in body

    def test_unknown_params_are_ignored(self, client):
        _login(client)
        _assert_unfiltered(_body(client, foo="bar"))


# ------------------------------------------------------------------ #
# No dates after today                                                #
# ------------------------------------------------------------------ #

TOMORROW = (TODAY + timedelta(days=1)).isoformat()


class TestNoFutureDates:
    def test_both_inputs_have_max_today(self, client):
        _login(client)
        body = _body(client)
        for name in ("date_from", "date_to"):
            tag = re.search(r'<input[^>]*name="%s"[^>]*>' % name, body).group(0)
            assert 'max="%s"' % TODAY.isoformat() in tag

    def test_future_date_to_is_rejected(self, client):
        _login(client)
        resp = _get(client, date_from=d(0), date_to=TOMORROW)
        assert resp.status_code == 200
        assert FUTURE_MSG in resp.data
        _assert_unfiltered(resp.data.decode())

    def test_future_date_from_is_rejected(self, client):
        _login(client)
        resp = _get(client, date_from=TOMORROW, date_to=TOMORROW)
        assert FUTURE_MSG in resp.data
        _assert_unfiltered(resp.data.decode())

    def test_today_is_accepted(self, client):
        _login(client)
        resp = _get(client, date_from=TODAY.isoformat(), date_to=TODAY.isoformat())
        assert FUTURE_MSG not in resp.data
        assert REVERSED_MSG not in resp.data

    def test_future_and_reversed_shows_only_future_message(self, client):
        _login(client)
        resp = _get(client, date_from=TOMORROW, date_to=d(0))
        assert FUTURE_MSG in resp.data
        assert REVERSED_MSG not in resp.data

    def test_future_date_with_missing_other_asks_for_both(self, client):
        _login(client)
        resp = _get(client, date_to=TOMORROW)
        assert ONE_BOUND_MSG in resp.data
        assert FUTURE_MSG not in resp.data

    def test_future_flash_not_repeated(self, client):
        _login(client)
        _get(client, date_from=d(0), date_to=TOMORROW)
        assert FUTURE_MSG not in _get(client).data

    def test_valid_past_range_has_no_future_flash(self, client):
        _login(client)
        assert FUTURE_MSG not in _get(client, date_from=d(0), date_to=d(3)).data


# ------------------------------------------------------------------ #
# Presets and filter bar                                              #
# ------------------------------------------------------------------ #

def _anchor_for(body, label):
    """Return (opening_tag, href) of the <a> whose text is `label`."""
    m = re.search(
        r"<a\b([^>]*)>\s*" + re.escape(label) + r"\s*</a>", body, re.IGNORECASE
    )
    assert m, f"Expected an <a> link labelled {label!r}"
    attrs = m.group(1)
    href = re.search(r'href="([^"]*)"', attrs)
    assert href, f"{label!r} link has no href"
    return attrs, href.group(1).replace("&amp;", "&")


class TestFilterBar:
    @pytest.mark.parametrize(
        "label", ["This Month", "Last 3 Months", "Last 6 Months", "All Time"]
    )
    def test_preset_labels_present(self, client, label):
        _login(client)
        assert label in _body(client)

    def test_filter_bar_has_two_date_inputs_and_apply(self, client):
        _login(client)
        body = _body(client)
        assert len(re.findall(r'<input[^>]*type="date"', body)) >= 2
        assert 'name="date_from"' in body
        assert 'name="date_to"' in body
        assert "Apply" in body

    def test_all_time_preset_links_to_clean_profile_url(self, client):
        _login(client)
        _, href = _anchor_for(_body(client), "All Time")
        assert href.rstrip("/").endswith("/profile")
        assert "?" not in href, "All Time must pass no query params"

    def test_this_month_preset_starts_first_of_month(self, client):
        _login(client)
        _, href = _anchor_for(_body(client), "This Month")
        assert f"date_from={FIRST.isoformat()}" in href
        assert f"date_to={TODAY.isoformat()}" in href

    @pytest.mark.parametrize("label", ["Last 3 Months", "Last 6 Months"])
    def test_multi_month_presets_end_today(self, client, label):
        _login(client)
        _, href = _anchor_for(_body(client), label)
        assert "date_from=" in href
        assert f"date_to={TODAY.isoformat()}" in href

    def test_preset_links_use_profile_route(self, client):
        _login(client)
        body = _body(client)
        for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
            _, href = _anchor_for(body, label)
            assert "/profile" in href

    def test_this_month_preset_link_is_followable(self, client):
        _login(client)
        _, href = _anchor_for(_body(client), "This Month")
        assert client.get(href).status_code == 200

    @pytest.mark.parametrize("today_offset", [0, 4, 27])
    def test_this_month_range_shows_only_expenses_up_to_today(
        self, client, monkeypatch, today_offset
    ):
        import app as app_module

        today = FIRST + timedelta(days=today_offset)
        monkeypatch.setattr(app_module, "_today", lambda: today)
        _login(client)
        body = _body(client, date_from=FIRST.isoformat(), date_to=today.isoformat())
        for off, desc in DESCRIPTIONS.items():
            if off <= today_offset:
                assert desc in body, f"{desc} (offset {off}) should be in range"
            else:
                assert desc not in body, f"{desc} (offset {off}) is in the future"

    def test_last_3_and_6_month_ranges_include_current_month_expenses(self, client):
        _login(client)
        today_offset = (TODAY - FIRST).days
        visible = [DESCRIPTIONS[o] for o in DESCRIPTIONS if o <= today_offset]
        for label in ("Last 3 Months", "Last 6 Months"):
            _, href = _anchor_for(_body(client), label)
            body = client.get(href).data.decode()
            for desc in visible:
                assert desc in body, f"{desc} missing under {label}"

    def test_custom_range_values_reflected_in_inputs(self, client):
        _login(client)
        body = _body(client, date_from=d(0), date_to=d(3))
        assert d(0) in body
        assert d(3) in body
        assert re.search(r'<input[^>]*name="date_from"[^>]*value="%s"' % d(0), body) or \
            re.search(r'<input[^>]*value="%s"[^>]*name="date_from"' % d(0), body), \
            "date_from input should show the active value"
        assert re.search(r'<input[^>]*name="date_to"[^>]*value="%s"' % d(3), body) or \
            re.search(r'<input[^>]*value="%s"[^>]*name="date_to"' % d(3), body), \
            "date_to input should show the active value"

    def test_all_time_is_highlighted_when_unfiltered(self, client):
        _login(client)
        attrs, _ = _anchor_for(_body(client), "All Time")
        assert "active" in attrs, "All Time should be active with no filter"

    def test_this_month_highlighted_for_its_exact_range(self, client):
        _login(client)
        body = _body(client, date_from=FIRST.isoformat(), date_to=TODAY.isoformat())
        this_month, _ = _anchor_for(body, "This Month")
        all_time, _ = _anchor_for(body, "All Time")
        assert "active" in this_month
        assert "active" not in all_time

    def test_no_preset_highlighted_for_custom_range(self, client):
        _login(client)
        body = _body(client, date_from="1999-01-01", date_to="1999-01-31")
        for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
            attrs, _ = _anchor_for(body, label)
            assert "active" not in attrs, f"{label} must not be active for custom range"
