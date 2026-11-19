import re
from datetime import date, timedelta

import pytest

import database.db as db
from database.db import init_db, seed_db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

FIRST = date.today().replace(day=1)
TODAY = FIRST + timedelta(days=27)
CATEGORY_LIST = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


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


def _count():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


def _row(expense_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


def _latest():
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


def _valid(**overrides):
    data = {
        "amount": "50.00",
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------ unit tests

class TestInsertExpense:
    def test_insert_with_description_saves_row(self, client):
        new_id = db.insert_expense(1, 50.0, "Food", "2026-03-20", "Lunch")
        row = _row(new_id)
        assert row is not None, "Expected row to exist"
        assert row["user_id"] == 1
        assert row["amount"] == pytest.approx(50.0)
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_insert_none_description_stores_null(self, client):
        new_id = db.insert_expense(1, 12.5, "Bills", "2026-03-21", None)
        assert _row(new_id)["description"] is None

    def test_insert_returns_new_id_and_increments_count(self, client):
        before = _count()
        new_id = db.insert_expense(1, 5.0, "Other", "2026-03-22", "x")
        assert isinstance(new_id, int)
        assert _count() == before + 1
        second = db.insert_expense(1, 6.0, "Other", "2026-03-22", "y")
        assert second != new_id

    def test_categories_constant(self):
        assert list(db.CATEGORIES) == CATEGORY_LIST


# ------------------------------------------------------------ auth guard

class TestAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_unauthenticated_redirects_and_no_insert(self, client):
        before = _count()
        resp = client.post("/expenses/add", data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _count() == before, "No row must be inserted when logged out"


# ------------------------------------------------------------ GET form

class TestGetForm:
    def test_get_authenticated_renders_form(self, logged_in):
        resp = logged_in.get("/expenses/add")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert re.search(r"<form[^>]*method=[\"']post[\"']", html, re.I)
        assert 'name="amount"' in html
        assert 'name="category"' in html
        assert 'name="date"' in html
        assert 'name="description"' in html

    def test_get_has_seven_category_options(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        select = re.search(
            r"<select[^>]*name=[\"']category[\"'][^>]*>(.*?)</select>", html, re.S
        )
        assert select, "Expected category <select>"
        # Skip the disabled empty-value placeholder; only real categories count.
        options = re.findall(
            r"<option[^>]*value=\"([^\"]+)\"[^>]*>", select.group(1)
        )
        assert options == CATEGORY_LIST

    def test_get_default_date_is_today(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert TODAY.isoformat() in html

    def test_get_shows_no_error(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert 'class="expense-error"' not in html


# ------------------------------------------------------------ valid POST

class TestValidPost:
    def test_valid_post_redirects_to_profile_and_saves(self, logged_in):
        before = _count()
        resp = logged_in.post("/expenses/add", data=_valid())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")
        assert _count() == before + 1
        row = _latest()
        assert row["user_id"] == 1
        assert row["amount"] == pytest.approx(50.0)
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    @pytest.mark.parametrize("desc", ["", "   ", "\t \n"])
    def test_blank_description_stored_as_null(self, logged_in, desc):
        resp = logged_in.post("/expenses/add", data=_valid(description=desc))
        assert resp.status_code == 302
        assert _latest()["description"] is None

    def test_missing_description_field_stored_as_null(self, logged_in):
        data = _valid()
        del data["description"]
        resp = logged_in.post("/expenses/add", data=data)
        assert resp.status_code == 302
        assert _latest()["description"] is None

    def test_description_is_stripped(self, logged_in):
        logged_in.post("/expenses/add", data=_valid(description="  Lunch  "))
        assert _latest()["description"] == "Lunch"

    def test_future_date_allowed(self, logged_in):
        future = (TODAY + timedelta(days=365)).isoformat()
        resp = logged_in.post("/expenses/add", data=_valid(date=future))
        assert resp.status_code == 302
        assert _latest()["date"] == future

    @pytest.mark.parametrize("category", CATEGORY_LIST)
    def test_every_category_accepted(self, logged_in, category):
        resp = logged_in.post("/expenses/add", data=_valid(category=category))
        assert resp.status_code == 302
        assert _latest()["category"] == category

    def test_sql_injection_description_stored_verbatim(self, logged_in):
        payload = "x'); DROP TABLE expenses; --"
        resp = logged_in.post("/expenses/add", data=_valid(description=payload))
        assert resp.status_code == 302
        assert _latest()["description"] == payload
        assert _count() >= 9, "expenses table must remain intact"

    def test_new_expense_visible_on_profile(self, logged_in):
        logged_in.post(
            "/expenses/add",
            data=_valid(
                description="UniqueLunchMarker", date=TODAY.isoformat(), amount="12.34"
            ),
        )
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "UniqueLunchMarker" in html
        assert "12.34" in html


# ------------------------------------------------------------ invalid POST

INVALID_CASES = [
    pytest.param({"amount": ""}, id="empty-amount"),
    pytest.param({"amount": "0"}, id="zero-amount"),
    pytest.param({"amount": "-5"}, id="negative-amount"),
    pytest.param({"amount": "abc"}, id="non-numeric-amount"),
    pytest.param({"amount": "nan"}, id="nan-amount"),
    pytest.param({"amount": "inf"}, id="inf-amount"),
    pytest.param({"category": "Gambling"}, id="bad-category"),
    pytest.param({"category": ""}, id="empty-category"),
    pytest.param({"date": "not-a-date"}, id="bad-date"),
    pytest.param({"date": "2026-02-30"}, id="impossible-date"),
    pytest.param({"date": ""}, id="empty-date"),
    pytest.param({"description": "a" * 201}, id="long-description"),
]


class TestInvalidPost:
    @pytest.mark.parametrize("override", INVALID_CASES)
    def test_invalid_input_rerenders_with_error_and_no_insert(
        self, logged_in, override
    ):
        before = _count()
        resp = logged_in.post("/expenses/add", data=_valid(**override))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "expense-error" in html, "Expected error message div"
        assert _count() == before, "No row may be inserted on invalid input"

    @pytest.mark.parametrize("field", ["amount", "category", "date"])
    def test_missing_field_rerenders_with_error(self, logged_in, field):
        data = _valid()
        del data[field]
        before = _count()
        resp = logged_in.post("/expenses/add", data=data)
        assert resp.status_code == 200
        assert "expense-error" in resp.get_data(as_text=True)
        assert _count() == before

    def test_description_of_exactly_200_chars_accepted(self, logged_in):
        resp = logged_in.post("/expenses/add", data=_valid(description="a" * 200))
        assert resp.status_code == 302
        assert len(_latest()["description"]) == 200

    def test_values_preserved_on_error(self, logged_in):
        resp = logged_in.post(
            "/expenses/add",
            data=_valid(
                amount="0",
                category="Health",
                date="2026-04-05",
                description="KeepMeText",
            ),
        )
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "2026-04-05" in html
        assert "KeepMeText" in html
        selected = re.search(
            r"<option[^>]*selected[^>]*>\s*([^<]*?)\s*</option>", html
        )
        assert selected and selected.group(1) == "Health"

    def test_invalid_post_does_not_redirect(self, logged_in):
        resp = logged_in.post("/expenses/add", data=_valid(amount="nan"))
        assert "Location" not in resp.headers


# ------------------------------------------------------------ navigation

class TestNavigation:
    def test_navbar_has_add_expense_link_when_logged_in(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "/expenses/add" in html
        assert "Add Expense" in html

    def test_profile_has_add_expense_link(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert html.count('href="/expenses/add"') >= 2, (
            "Expected both navbar and profile page links"
        )

    def test_navbar_hides_add_expense_when_logged_out(self, client):
        html = client.get("/").get_data(as_text=True)
        assert "/expenses/add" not in html
