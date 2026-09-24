"""
Unit tests for the migrations handler without a database: who may call it,
the seed guard, and the error safety nets.
"""

import pytest

import function
from _testing.events import call
from _testing.fakes import FakeConnection, caller
from lib.responses import HttpError


@pytest.fixture
def guarded(monkeypatch, no_database):
    """A database that already has a db admin, so a token is required."""
    monkeypatch.setattr(function, "db_admin_exists", lambda: True)
    monkeypatch.setattr(function, "apply_schema", lambda: None)
    monkeypatch.setattr(function, "existing_tables", lambda: list(function.TABLES))
    monkeypatch.setattr(function, "load_seed", lambda: {"users": 13})
    return no_database


def sign_in_as(monkeypatch, role):
    monkeypatch.setattr(function, "current_user", lambda event: caller(role))


class TestAccess:
    def test_first_run_on_a_fresh_database_is_open(self, guarded, monkeypatch):
        monkeypatch.setattr(function, "db_admin_exists", lambda: False)
        status, data = call(function.handler, "POST", "/api/migrations")
        assert status == 200
        assert data == {"message": "Schema applied", "tables": function.TABLES}

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_after_that_a_token_is_required(self, guarded, method):
        status, data = call(function.handler, method, "/api/migrations")
        assert (status, data) == (401, {"error": "Authentication required"})

    @pytest.mark.parametrize("role", ["employee", "engineer", "facility_admin"])
    def test_only_a_db_admin(self, guarded, monkeypatch, role):
        sign_in_as(monkeypatch, role)
        status, data = call(function.handler, "POST", "/api/migrations", token="x")
        assert (status, data) == (403, {"error": "Access denied"})

    def test_db_admin_can_apply_and_inspect(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        assert call(function.handler, "POST", "/api/migrations", token="x")[0] == 200
        status, data = call(function.handler, "GET", "/api/migrations", token="x")
        assert (status, data) == (200, {"tables": function.TABLES, "missing": []})

    def test_missing_tables_are_reported(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        monkeypatch.setattr(function, "existing_tables", lambda: ["branches", "users"])
        _, data = call(function.handler, "GET", "/api/migrations", token="x")
        assert data["missing"] == [t for t in function.TABLES if t not in ("branches", "users")]


class TestRouting:
    def test_other_methods_are_405(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        status, data = call(function.handler, "DELETE", "/api/migrations", token="x")
        assert (status, data) == (405, {"error": "Method DELETE not allowed"})

    def test_unknown_paths_are_404(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        status, data = call(function.handler, "GET", "/api/migrations/tables", token="x")
        assert (status, data) == (404, {"error": "Not found"})

    def test_handler_tolerates_a_missing_event(self, guarded):
        assert function.handler()["statusCode"] == 401


class TestSeed:
    def test_requires_confirmation(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        status, data = call(function.handler, "POST", "/api/migrations/seed", token="x", body={})
        assert status == 400
        assert "RESET" in data["error"]
        status, _ = call(function.handler, "POST", "/api/migrations/seed", token="x", body={"confirm": "reset"})
        assert status == 400

    def test_loads_with_confirmation(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        status, data = call(function.handler, "POST", "/api/migrations/seed", token="x", body={"confirm": "RESET"})
        assert (status, data) == (200, {"message": "Sample data loaded", "rows": {"users": 13}})

    def test_seed_is_post_only_and_db_admin_only(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        assert call(function.handler, "GET", "/api/migrations/seed", token="x")[0] == 405
        sign_in_as(monkeypatch, "facility_admin")
        assert call(function.handler, "POST", "/api/migrations/seed", token="x", body={"confirm": "RESET"})[0] == 403


class TestFailures:
    def test_a_failed_migration_rolls_back_and_reports_500(self, guarded, monkeypatch):
        sign_in_as(monkeypatch, "db_admin")
        connection = FakeConnection()
        monkeypatch.setattr(function, "get_connection", lambda: connection)

        def broken():
            raise RuntimeError("syntax error at or near")

        monkeypatch.setattr(function, "apply_schema", broken)
        status, data = call(function.handler, "POST", "/api/migrations", token="x")
        assert status == 500
        assert data["error"] == "Migration failed"
        assert connection.rollbacks == 1

    def test_http_errors_keep_their_status(self, guarded, monkeypatch):
        def denied(event):
            raise HttpError(401, "Token has expired")

        monkeypatch.setattr(function, "current_user", denied)
        status, data = call(function.handler, "GET", "/api/migrations", token="x")
        assert (status, data) == (401, {"error": "Token has expired"})
