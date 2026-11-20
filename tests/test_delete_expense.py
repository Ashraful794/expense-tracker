import pytest

import database.db as db
from database.db import init_db, seed_db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_db()
    import app as app_module

    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    return client


def _exists(expense_id):
    conn = db.get_db()
    try:
        return (
            conn.execute(
                "SELECT 1 FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
            is not None
        )
    finally:
        conn.close()


def _count():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


def _demo_expense_id():
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT id FROM expenses WHERE user_id = 1 ORDER BY id LIMIT 1"
        ).fetchone()["id"]
    finally:
        conn.close()


@pytest.fixture
def other_expense_id(client):
    other_id = db.create_user("Other", "other@example.com", "password123")
    return db.insert_expense(other_id, 10.0, "Food", "2026-01-05", "Not yours")


class TestDeleteExpenseHelper:
    def test_deletes_own_expense(self, client):
        expense_id = _demo_expense_id()
        assert db.delete_expense(expense_id, 1) == 1
        assert not _exists(expense_id)

    def test_wrong_user_deletes_nothing(self, client):
        expense_id = _demo_expense_id()
        assert db.delete_expense(expense_id, 999) == 0
        assert _exists(expense_id)

    def test_nonexistent_id_is_a_noop(self, client):
        before = _count()
        assert db.delete_expense(99999, 1) == 0
        assert _count() == before


class TestDeleteExpenseRoute:
    def test_unauthenticated_post_redirects_to_login(self, client):
        expense_id = _demo_expense_id()
        resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _exists(expense_id)

    def test_deletes_own_expense_and_redirects(self, logged_in):
        expense_id = _demo_expense_id()
        before = _count()
        resp = logged_in.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")
        assert not _exists(expense_id)
        assert _count() == before - 1

    def test_deleted_expense_gone_from_profile(self, logged_in):
        expense_id = _demo_expense_id()
        conn = db.get_db()
        try:
            description = conn.execute(
                "SELECT description FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()["description"]
        finally:
            conn.close()
        assert description in logged_in.get("/profile").get_data(as_text=True)

        logged_in.post(f"/expenses/{expense_id}/delete")
        resp = logged_in.get("/profile")
        assert description not in resp.get_data(as_text=True)

    def test_other_users_expense_returns_404(self, logged_in, other_expense_id):
        resp = logged_in.post(f"/expenses/{other_expense_id}/delete")
        assert resp.status_code == 404
        assert _exists(other_expense_id)

    def test_nonexistent_id_returns_404(self, logged_in):
        assert logged_in.post("/expenses/99999/delete").status_code == 404

    def test_get_returns_405(self, logged_in):
        expense_id = _demo_expense_id()
        assert logged_in.get(f"/expenses/{expense_id}/delete").status_code == 405
        assert _exists(expense_id)

    def test_get_logged_out_returns_405(self, client):
        assert client.get("/expenses/1/delete").status_code == 405


class TestProfileDeleteButton:
    def test_each_row_has_delete_form(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        expense_id = _demo_expense_id()
        assert f'action="/expenses/{expense_id}/delete"' in html
        assert 'class="btn-delete"' in html
        assert 'data-confirm="Delete this expense?"' in html
        assert "Edit</a>" in html

    def test_rows_carry_confirm_detail(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        attr = html.split("data-confirm-detail=", 1)[1].split(">", 1)[0]
        assert "৳" in attr

    def test_confirm_dialog_rendered_once(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert html.count('id="confirm-dialog"') == 1
        assert 'id="confirm-dialog-cancel"' in html
        assert 'id="confirm-dialog-ok"' in html

    def test_confirm_dialog_not_on_other_pages(self, client):
        assert "confirm-dialog" not in client.get("/login").get_data(as_text=True)

    def test_detail_is_escaped(self, logged_in):
        from datetime import date

        payload = '"><script>x</script>'
        db.insert_expense(1, 5.0, "Food", date.today().isoformat(), payload)
        html = logged_in.get("/profile").get_data(as_text=True)
        assert payload not in html
