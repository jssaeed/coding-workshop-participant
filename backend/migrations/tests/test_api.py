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

    def test_creates_the_list_indexes(self, api, fresh):
        api(function.handler, "POST", "/api/migrations")
        names = {r["indexname"] for r in fresh.fetch_all("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
        assert {"incidents_list_order_idx", "incidents_category_idx", "messages_thread_idx", "users_branch_created_idx"} <= names

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


def constraint_rule(db, name):
    row = db.fetch_one("SELECT pg_get_constraintdef(oid) AS rule FROM pg_constraint WHERE conname = %s", (name,))
    return None if row is None else row["rule"]


def column_names(db, table):
    rows = db.fetch_all("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s", (table,))
    return {r["column_name"] for r in rows}


class TestUpgrades:
    """
    A database made by an earlier version of the schema is brought up to
    date by the same migration. Each test puts one table back into its old
    shape, runs the migration, and checks the new shape and the data.
    """

    @pytest.fixture
    def old(self, db):
        yield db
        db.apply_schema()  # put the schema back whatever the test did to it

    def migrate(self, api):
        # The users table is empty here, so there is no db admin yet and the migration is open
        status, data = api(function.handler, "POST", "/api/migrations")
        assert (status, data["message"]) == (200, "Schema applied")

    def test_category_is_added_with_other_for_existing_tickets(self, api, old):
        old.execute("ALTER TABLE incidents DROP COLUMN category")
        ticket = old.execute("INSERT INTO incidents (title, branch_id) VALUES ('Made before categories', 1) RETURNING id")["id"]

        self.migrate(api)

        assert old.fetch_one("SELECT category FROM incidents WHERE id = %s", (ticket,)) == {"category": "other"}
        assert "'plumbing'" in constraint_rule(old, "incidents_category_check")
        assert "incidents_category_idx" in {r["indexname"] for r in old.fetch_all("SELECT indexname FROM pg_indexes WHERE tablename = 'incidents'")}
        with pytest.raises(Exception):
            old.execute("INSERT INTO incidents (title, branch_id, category) VALUES ('Bad', 1, 'magic')")
        assert old.count("incidents") == 1

    def test_old_free_text_locations_table_is_replaced(self, api, old):
        old.execute("DROP TABLE locations CASCADE")  # takes incidents' foreign key with it
        old.execute("CREATE TABLE locations (id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, building TEXT NOT NULL, floor INTEGER NOT NULL)")
        place = old.execute("INSERT INTO locations (building, floor) VALUES ('HQ', 3) RETURNING id")["id"]
        ticket = old.execute("INSERT INTO incidents (title, branch_id, location_id) VALUES ('Old', 1, %s) RETURNING id", (place,))["id"]

        self.migrate(api)

        columns = column_names(old, "locations")
        assert "building_id" in columns and "building" not in columns
        assert constraint_rule(old, "incidents_location_id_fkey") is not None
        # the old place could not be carried over, so the ticket keeps everything but its location
        assert old.fetch_one("SELECT title, location_id FROM incidents WHERE id = %s", (ticket,)) == {"title": "Old", "location_id": None}

    def test_user_links_stop_blocking_deletion(self, api, old):
        for table, column in [("incidents", "reported_by"), ("messages", "user_id")]:
            old.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_{column}_fkey")
            old.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_fkey FOREIGN KEY ({column}) REFERENCES users (id) ON DELETE RESTRICT")
            old.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")

        self.migrate(api)

        author = old.create_user()
        ticket = old.create_incident(author["id"])
        message = old.create_message(ticket, author["id"])
        old.execute("DELETE FROM users WHERE id = %s", (author["id"],))  # would have been refused before
        assert old.fetch_one("SELECT reported_by FROM incidents WHERE id = %s", (ticket,)) == {"reported_by": None}
        assert old.fetch_one("SELECT user_id FROM messages WHERE id = %s", (message,)) == {"user_id": None}

    def test_assigned_status_is_added_and_open_tickets_with_an_engineer_move_to_it(self, api, old):
        old.execute("ALTER TABLE incidents DROP CONSTRAINT incidents_status_check")
        old.execute("ALTER TABLE incidents ADD CONSTRAINT incidents_status_check CHECK (status IN ('open', 'in_progress', 'blocked', 'resolved', 'closed'))")
        engineer = old.create_user("engineer")
        taken = old.create_incident(engineer["id"], assigned_to=engineer["id"], status="open")
        free = old.create_incident(engineer["id"], status="open")

        self.migrate(api)

        assert "'assigned'" in constraint_rule(old, "incidents_status_check")
        assert old.fetch_one("SELECT status FROM incidents WHERE id = %s", (taken,)) == {"status": "assigned"}
        assert old.fetch_one("SELECT status FROM incidents WHERE id = %s", (free,)) == {"status": "open"}

    def test_branch_columns_are_added_and_filled_in(self, api, old):
        old.execute("ALTER TABLE incidents DROP COLUMN branch_id")
        old.execute("ALTER TABLE users DROP COLUMN branch_id CASCADE")  # also drops the index on it
        reporter = old.execute("INSERT INTO users (email, password_hash, name, role) VALUES ('old@acme.inc', 'x', 'Old', 'employee') RETURNING id")["id"]
        miami = old.create_building(branch_id=2, name="Violent Crimes")
        place = old.create_location(miami["id"], 1)
        located = old.execute("INSERT INTO incidents (title, reported_by, location_id) VALUES ('At Miami', %s, %s) RETURNING id", (reporter, place["id"]))["id"]
        unlocated = old.execute("INSERT INTO incidents (title, reported_by) VALUES ('Nowhere', %s) RETURNING id", (reporter,))["id"]

        self.migrate(api)

        # accounts from before branches belong to Princeton-Plainsboro (1)
        assert old.fetch_one("SELECT branch_id FROM users WHERE id = %s", (reporter,)) == {"branch_id": 1}
        # a ticket takes its building's branch, else its reporter's
        assert old.fetch_one("SELECT branch_id FROM incidents WHERE id = %s", (located,)) == {"branch_id": 2}
        assert old.fetch_one("SELECT branch_id FROM incidents WHERE id = %s", (unlocated,)) == {"branch_id": 1}
        names = {r["indexname"] for r in old.fetch_all("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
        assert {"incidents_branch_id_idx", "users_branch_created_idx"} <= names

    def test_basement_floors_become_allowed(self, api, old):
        old.execute("ALTER TABLE locations DROP CONSTRAINT locations_floor_check")
        old.execute("ALTER TABLE locations ADD CONSTRAINT locations_floor_check CHECK (floor >= 1)")

        self.migrate(api)

        assert constraint_rule(old, "locations_floor_check") == "CHECK ((floor <> 0))"
        hq = old.create_building(basement_floors=1)
        assert old.create_location(hq["id"], -1)["id"] > 0

    def test_db_admin_role_is_added_and_the_account_created(self, api, old):
        old.execute("ALTER TABLE users DROP CONSTRAINT users_role_check")
        old.execute("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('facility_admin', 'engineer', 'employee'))")

        self.migrate(api)

        assert "'db_admin'" in constraint_rule(old, "users_role_check")
        assert old.count("users", "role = 'db_admin' AND email = %s", (function.DB_ADMIN_EMAIL,)) == 1


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
        # The sample tickets are spread over the categories (the CHECK rule
        # on the column already refuses anything outside the list).
        assert db.count("incidents", "category = 'plumbing'") > 0
        assert db.count("incidents", "category <> 'other'") > db.count("incidents", "category = 'other'")

        # The file sets ids by hand, so the id counters must have moved past
        # them: every new row gets an id above the highest one loaded.
        seeded_admin = db.fetch_one("SELECT id FROM users WHERE role = 'db_admin'")["id"]
        seeded_ticket = db.fetch_one("SELECT MIN(id) AS id FROM incidents")["id"]
        for table, make in [
            ("users", lambda: db.create_user()["id"]),
            ("incidents", lambda: db.create_incident(seeded_admin)),
            ("messages", lambda: db.create_message(seeded_ticket, seeded_admin)),
        ]:
            highest = db.fetch_one(f"SELECT MAX(id) AS n FROM {table}")["n"]
            assert make() == highest + 1, table

    def test_migration_moves_id_counters_past_rows_with_hand_set_ids(self, api, db):
        root = db.create_user("db_admin")
        # Like a restored dump: a row whose id was set by hand, ahead of the counter.
        db.execute(
            "INSERT INTO users (id, email, password_hash, name, role, branch_id) "
            "OVERRIDING SYSTEM VALUE VALUES (500, 'far@acme.inc', 'x', 'Far', 'employee', 1)"
        )
        assert api(function.handler, "POST", "/api/migrations", user=root)[0] == 200
        assert db.create_user()["id"] == 501

    def test_without_confirmation_nothing_changes(self, api, db):
        root = db.create_user("db_admin")
        db.create_incident(root["id"])
        status, _ = api(function.handler, "POST", "/api/migrations/seed", user=root, body={})
        assert status == 400
        assert db.count("incidents") == 1
