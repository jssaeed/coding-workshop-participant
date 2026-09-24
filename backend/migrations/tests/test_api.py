"""
Integration tests for the migrations service against the real test database.

These are the only tests that drop the test database's schema, to see the
migration build it from nothing. The schema is put back afterwards so the
other tests (and services) find it again.
"""

import pytest

import function
from lib import auth


@pytest.fixture
def fresh(db):
    """An empty test database; the schema is re-applied when the test ends."""
    db.drop_everything()
    yield db
    db.apply_schema()


def table_names(db):
    return {r["table_name"] for r in db.fetch_all("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}


class TestFirstRun:
    def test_creates_every_table_the_branches_and_the_db_admin(self, api, fresh):
        status, data = api(function.handler, "POST", "/api/migrations")
        assert status == 200
        assert data["message"] == "Schema applied"
        assert data["tables"] == function.TABLES
        assert set(function.TABLES) <= table_names(fresh)

        branches = fresh.fetch_all("SELECT id, name FROM branches ORDER BY id")
        assert branches == [{"id": 1, "name": "Princeton-Plainsboro"}, {"id": 2, "name": "Miami"}]

        admin = fresh.fetch_one("SELECT email, name, role, branch_id, password_hash FROM users")
        assert (admin["email"], admin["name"], admin["role"], admin["branch_id"]) == (function.DB_ADMIN_EMAIL, "admin", "db_admin", 1)
        assert auth.check_password(function.DB_ADMIN_PASSWORD, admin["password_hash"])

    def test_get_before_any_migration_reports_everything_missing(self, api, fresh):
        status, data = api(function.handler, "GET", "/api/migrations")
        assert (status, data) == (200, {"tables": [], "missing": function.TABLES})


class TestAfterFirstRun:
    def test_running_again_is_safe_and_needs_a_db_admin(self, api, db):
        root = db.fetch_one("SELECT id, email, role FROM users WHERE role = 'db_admin'")
        if root is None:
            root = db.create_user("db_admin", email="admin@admin.com")
        db.create_user("employee")
        building = db.create_building()

        assert api(function.handler, "POST", "/api/migrations")[0] == 401
        assert api(function.handler, "GET", "/api/migrations")[0] == 401
        assert api(function.handler, "POST", "/api/migrations", user=db.create_user("facility_admin"))[0] == 403

        status, data = api(function.handler, "POST", "/api/migrations", user=root)
        assert status == 200
        assert data["tables"] == function.TABLES
        # nothing was dropped
        assert db.count("users") == 3
        assert db.count("buildings", "id = %s", (building["id"],)) == 1

        status, data = api(function.handler, "GET", "/api/migrations", user=root)
        assert (status, data) == (200, {"tables": function.TABLES, "missing": []})

    def test_the_db_admin_account_is_restored_if_demoted(self, api, db):
        root = db.create_user("db_admin")
        db.create_user("employee", email=function.DB_ADMIN_EMAIL, name="renamed")
        api(function.handler, "POST", "/api/migrations", user=root)
        row = db.fetch_one("SELECT role, name FROM users WHERE email = %s", (function.DB_ADMIN_EMAIL,))
        assert row == {"role": "db_admin", "name": "admin"}


class TestSeed:
    def test_replaces_the_data_with_the_sample_set(self, api, db):
        root = db.create_user("db_admin")
        db.create_incident(db.create_user()["id"])
        db.create_refresh_token(root["id"])

        status, data = api(function.handler, "POST", "/api/migrations/seed", user=root, body={"confirm": "RESET"})
        assert status == 200
        assert data["message"] == "Sample data loaded"
        rows = data["rows"]
        assert rows["users"] > 0 and rows["incidents"] > 0 and rows["buildings"] > 0
        assert rows["refresh_tokens"] == 0
        assert db.count("incidents") == rows["incidents"]
        assert db.count("users", "role = 'db_admin'") >= 1

        # the id counters continue after the sample ids, so new rows do not collide
        new = db.create_user()
        assert new["id"] > rows["users"]

    def test_without_confirmation_nothing_changes(self, api, db):
        root = db.create_user("db_admin")
        db.create_incident(root["id"])
        status, _ = api(function.handler, "POST", "/api/migrations/seed", user=root, body={})
        assert status == 400
        assert db.count("incidents") == 1
