"""
Migrations service: creates the database tables.

The whole database schema lives in this file, in the SCHEMA list below. Each
entry is one SQL statement. They run in order, top to bottom, every time this
service is called.

Every statement uses "IF NOT EXISTS", so running this again on a database
that already has the tables does nothing. That makes it safe to call as often
as you like.

    POST /api/migrations   create any missing tables
    GET  /api/migrations   list which tables exist

Run it after starting the dev environment, and again after any schema change:

    curl -X POST http://localhost:3001/api/migrations

To add a column to an existing table, add a new
"ALTER TABLE ... ADD COLUMN IF NOT EXISTS ..." statement at the end of the
list, because CREATE TABLE IF NOT EXISTS skips tables that already exist.
"""

import logging
import os

from lib.auth import ROLE_DB_ADMIN, current_user, hash_password, require_role
from lib.database import get_connection
from lib.request import http_method, json_body, path_segments
from lib.responses import HttpError, json_response, method_not_allowed

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------
#
# Four kinds of rules keep the data clean:
#   NOT NULL      the column must have a value
#   CHECK (...)   the value must pass the test (for example, priority 1 to 5)
#   UNIQUE        no two rows can have the same value
#   REFERENCES    the value must be the id of a row in another table
#
# "ON DELETE ..." says what happens when the referenced row is deleted:
#   RESTRICT   refuse to delete it while rows still point at it
#   CASCADE    delete the pointing rows as well
#   SET NULL   keep the pointing rows but clear the reference

SCHEMA = [
    # --- branches --------------------------------------------------------
    # The company sites. Every user belongs to exactly one, and a facility
    # admin can only manage the accounts at their own branch.
    """
    CREATE TABLE IF NOT EXISTS branches (
        id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name       TEXT        NOT NULL UNIQUE CHECK (name <> ''),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # The branches ACME has today. ON CONFLICT DO NOTHING makes this safe to
    # run every time: an existing branch is simply left alone.
    "INSERT INTO branches (name) VALUES ('Princeton-Plainsboro') ON CONFLICT (name) DO NOTHING",
    "INSERT INTO branches (name) VALUES ('Miami') ON CONFLICT (name) DO NOTHING",

    # --- users -----------------------------------------------------------
    # Emails are stored in lower case (the users service does this), so a
    # plain UNIQUE rule is enough to stop the same address signing up twice.
    # ON DELETE RESTRICT: a branch cannot be removed while it has people.
    """
    CREATE TABLE IF NOT EXISTS users (
        id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        email         TEXT        NOT NULL UNIQUE,
        password_hash TEXT        NOT NULL,
        name          TEXT        NOT NULL CHECK (name <> ''),
        role          TEXT        NOT NULL DEFAULT 'employee'
                                  CHECK (role IN ('db_admin', 'facility_admin', 'engineer', 'employee')),
        branch_id     BIGINT      NOT NULL REFERENCES branches (id) ON DELETE RESTRICT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,

    # --- buildings -------------------------------------------------------
    # Defined by a facility admin for their own branch: a name, how many
    # floors above ground (1..floors) and how many below (B1..Bm). The
    # ticket form offers a branch's buildings as a dropdown.
    """
    CREATE TABLE IF NOT EXISTS buildings (
        id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        branch_id       BIGINT      NOT NULL REFERENCES branches (id) ON DELETE RESTRICT,
        name            TEXT        NOT NULL CHECK (name <> ''),
        floors          SMALLINT    NOT NULL CHECK (floors BETWEEN 1 AND 200),
        basement_floors SMALLINT    NOT NULL DEFAULT 0 CHECK (basement_floors BETWEEN 0 AND 20),
        -- true: room 1 on floor 5 is shown as "501" (or "5001" past 99 rooms)
        room_numbers_include_floor BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # Upgrades for a buildings table made before branches and basements.
    # Every line is safe to re-run: "IF NOT EXISTS" and "IF EXISTS" make the
    # ALTERs no-ops the second time, and the UPDATE only touches NULLs.
    # Buildings that existed before branches belong to Princeton-Plainsboro.
    "ALTER TABLE buildings ADD COLUMN IF NOT EXISTS branch_id BIGINT REFERENCES branches (id) ON DELETE RESTRICT",
    """
    UPDATE buildings
    SET branch_id = (SELECT id FROM branches WHERE name = 'Princeton-Plainsboro')
    WHERE branch_id IS NULL
    """,
    "ALTER TABLE buildings ALTER COLUMN branch_id SET NOT NULL",
    """
    ALTER TABLE buildings
    ADD COLUMN IF NOT EXISTS basement_floors SMALLINT NOT NULL DEFAULT 0
        CHECK (basement_floors BETWEEN 0 AND 20)
    """,
    "ALTER TABLE buildings ADD COLUMN IF NOT EXISTS room_numbers_include_floor BOOLEAN NOT NULL DEFAULT FALSE",
    # Names used to be unique across the company; now they are unique per
    # branch (ignoring case), so Miami can have its own "HQ".
    "ALTER TABLE buildings DROP CONSTRAINT IF EXISTS buildings_name_key",
    "CREATE UNIQUE INDEX IF NOT EXISTS buildings_branch_name_idx ON buildings (branch_id, LOWER(name))",

    # --- building_floors -------------------------------------------------
    # One row per floor of a building, saying how many rooms it has (0 =
    # not specified, so the ticket form takes any room number). Floors are
    # numbered 1..floors above ground and -1..-basement_floors below
    # (the app shows -1 as "B1"). Deleting a building deletes its floors.
    """
    CREATE TABLE IF NOT EXISTS building_floors (
        building_id BIGINT   NOT NULL REFERENCES buildings (id) ON DELETE CASCADE,
        floor       SMALLINT NOT NULL CHECK (floor <> 0),
        rooms       SMALLINT NOT NULL DEFAULT 0 CHECK (rooms BETWEEN 0 AND 500),
        PRIMARY KEY (building_id, floor)
    )
    """,
    # Buildings made before this table existed get a row per floor, with
    # rooms unspecified. ON CONFLICT DO NOTHING keeps existing rows as is.
    """
    INSERT INTO building_floors (building_id, floor, rooms)
    SELECT b.id, f, 0
    FROM buildings b, generate_series(1, b.floors) AS f
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO building_floors (building_id, floor, rooms)
    SELECT b.id, f, 0
    FROM buildings b, generate_series(-b.basement_floors, -1) AS f
    ON CONFLICT DO NOTHING
    """,

    # --- locations -------------------------------------------------------
    # One exact place: a building, a floor on it, and optionally a room.
    # Tickets point at a location row, and the same place is reused by
    # every ticket reported there.
    # "UNIQUE NULLS NOT DISTINCT" makes two rows with room = NULL count as
    # the same place (plain UNIQUE would treat every NULL as different).
    # The floor number is checked against the building's floors in the
    # incidents service, because a CHECK cannot look at another table. Here
    # it only has to be non-zero: positive above ground, negative for
    # basements (-1 is "B1").
    """
    CREATE TABLE IF NOT EXISTS locations (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        building_id BIGINT      NOT NULL REFERENCES buildings (id) ON DELETE RESTRICT,
        floor       SMALLINT    NOT NULL CHECK (floor <> 0),
        room        INTEGER     CHECK (room >= 1),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE NULLS NOT DISTINCT (building_id, floor, room)
    )
    """,
    "CREATE INDEX IF NOT EXISTS locations_building_id_idx ON locations (building_id)",

    # --- incidents -------------------------------------------------------
    # A ticket. reported_by is who filed it, assigned_to is the engineer
    # working on it (NULL until an admin assigns someone). branch_id is the
    # branch the ticket was filed at (the reporter's branch): facility
    # admins only see and manage the tickets at their own branch, and it is
    # stored on the ticket so it survives a deleted reporter or no location.
    # Both point at users with ON DELETE SET NULL: when an account is
    # deleted its tickets stay, and the API shows "Deleted user" instead.
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        title       TEXT        NOT NULL CHECK (title <> ''),
        description TEXT        NOT NULL DEFAULT '',
        status      TEXT        NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open', 'assigned', 'in_progress', 'blocked', 'resolved', 'closed')),
        priority    SMALLINT    NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
        -- What kind of problem it is (plumbing, electrical, ...). The list
        -- is repeated in the incidents service (models/incident.py).
        category    TEXT        NOT NULL DEFAULT 'other'
                                CHECK (category IN ('plumbing', 'electrical', 'hvac', 'structural', 'doors_and_locks', 'elevators', 'furniture', 'appliances', 'safety', 'cleaning', 'other')),
        location_id BIGINT      REFERENCES locations (id) ON DELETE RESTRICT,
        branch_id   BIGINT      NOT NULL REFERENCES branches (id) ON DELETE RESTRICT,
        reported_by BIGINT      REFERENCES users (id) ON DELETE SET NULL,
        assigned_to BIGINT      REFERENCES users (id) ON DELETE SET NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ,
        -- An engineer cannot set "blocked" or "resolved" alone: the wish is
        -- recorded here until a facility admin approves or rejects it.
        pending_status       TEXT CHECK (pending_status IN ('blocked', 'resolved')),
        pending_requested_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
        pending_requested_at TIMESTAMPTZ,
        pending_note         TEXT
    )
    """,
    # Upgrade for incidents tables made before approvals existed (no-ops after).
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS pending_status TEXT CHECK (pending_status IN ('blocked', 'resolved'))",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS pending_requested_by BIGINT REFERENCES users (id) ON DELETE SET NULL",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS pending_requested_at TIMESTAMPTZ",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS pending_note TEXT",
    # Upgrade for incidents tables made before categories existed: every
    # older ticket becomes 'other' (the DEFAULT fills the new column).
    """
    ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'other'
        CHECK (category IN ('plumbing', 'electrical', 'hvac', 'structural', 'doors_and_locks', 'elevators', 'furniture', 'appliances', 'safety', 'cleaning', 'other'))
    """,
    # Indexes make the ticket list filters fast.
    "CREATE INDEX IF NOT EXISTS incidents_status_idx      ON incidents (status)",
    "CREATE INDEX IF NOT EXISTS incidents_priority_idx    ON incidents (priority)",
    "CREATE INDEX IF NOT EXISTS incidents_category_idx    ON incidents (category)",
    "CREATE INDEX IF NOT EXISTS incidents_reported_by_idx ON incidents (reported_by)",
    "CREATE INDEX IF NOT EXISTS incidents_assigned_to_idx ON incidents (assigned_to)",
    # The ticket list's default order (most urgent, then newest, then id as
    # the tie-breaker). With this index a page of the list is an index
    # range scan: PostgreSQL reads the rows for that page and nothing else.
    "CREATE INDEX IF NOT EXISTS incidents_list_order_idx ON incidents (priority, created_at DESC, id DESC)",

    # --- messages --------------------------------------------------------
    # The conversation on a ticket. Status and assignment changes are also
    # saved here as messages, so the thread shows the ticket's history.
    # ON DELETE CASCADE: deleting a ticket deletes its messages too.
    # ON DELETE SET NULL: deleting a user keeps their messages, unsigned.
    """
    CREATE TABLE IF NOT EXISTS messages (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        incident_id BIGINT      NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
        user_id     BIGINT      REFERENCES users (id) ON DELETE SET NULL,
        message     TEXT        NOT NULL CHECK (message <> ''),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS messages_incident_id_idx ON messages (incident_id)",
    # A thread is read newest-first one page at a time (keyset pagination on
    # created_at, id); this index serves that order directly.
    "CREATE INDEX IF NOT EXISTS messages_thread_idx ON messages (incident_id, created_at DESC, id DESC)",

    # --- refresh_tokens --------------------------------------------------
    # Long-lived tokens that can be exchanged for a new short-lived access
    # token (see lib/auth.py). Only the SHA-256 hash is stored, so a copy of
    # the database cannot be used to log in as anyone. revoked_at is set when
    # a token is used (it is replaced by a new one), on logout, or when the
    # user is demoted.
    """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id    BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        token_hash TEXT        NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS refresh_tokens_user_id_idx ON refresh_tokens (user_id)",

    # --- ticket_reads ----------------------------------------------------
    # Remembers when each user last looked at each ticket. The inbox uses it:
    # a message is "unread" if it is newer than the user's last_read_at for
    # that ticket (or the user has never opened the ticket).
    """
    CREATE TABLE IF NOT EXISTS ticket_reads (
        user_id      BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        incident_id  BIGINT      NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
        last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, incident_id)
    )
    """,

    # --- clean-up from an earlier version of this schema ----------------
    # Older databases have triggers that set updated_at and resolved_at
    # automatically. The services now set those columns themselves, so the
    # triggers are removed. Harmless on a fresh database.
    "DROP TRIGGER IF EXISTS users_set_updated_at ON users",
    "DROP TRIGGER IF EXISTS locations_set_updated_at ON locations",
    "DROP TRIGGER IF EXISTS incidents_set_updated_at ON incidents",
    "DROP TRIGGER IF EXISTS incidents_set_resolved_at ON incidents",
    "DROP TRIGGER IF EXISTS messages_set_updated_at ON messages",
    "DROP FUNCTION IF EXISTS set_updated_at()",
    "DROP FUNCTION IF EXISTS set_incident_resolved_at()",
]

# The tables the schema above creates. GET uses this to report what is missing.
TABLES = ["branches", "users", "buildings", "building_floors", "locations", "incidents", "messages", "refresh_tokens", "ticket_reads"]


def apply_schema():
    """
    Run every statement in SCHEMA, in order, as one transaction.

    PostgreSQL DDL is transactional, so a statement that fails half-way
    down the list leaves the database exactly as it was: the whole run is
    rolled back and the error is raised for the handler to report.
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            replace_old_locations_table(cursor)
            for statement in SCHEMA:
                cursor.execute(statement)
            restore_incident_location_link(cursor)
            allow_deleting_users_with_history(cursor)
            add_assigned_status(cursor)
            add_branches_to_users(cursor)
            add_users_directory_index(cursor)
            add_branches_to_incidents(cursor)
            allow_basement_floors(cursor)
            add_db_admin_role(cursor)
            ensure_db_admin_account(cursor)
            move_id_counters_past_existing_rows(cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


# ---------------------------------------------------------------------------
# Upgrading databases created by an earlier version
# ---------------------------------------------------------------------------
#
# An earlier version of the locations table stored building and floor as
# free text. The table now points at the buildings table instead, and a
# table's shape cannot be changed with CREATE TABLE IF NOT EXISTS. So, if the
# old shape is found, the old table is removed before SCHEMA runs (which then
# creates the new one). Tickets keep everything except their old location.
#
# Later, user deletion changed: tickets and messages used to block it
# (ON DELETE RESTRICT), now they are kept with the user link cleared
# (ON DELETE SET NULL). allow_deleting_users_with_history() makes that change
# on an existing database.
#
# Later still, an "assigned" status was added between "open" and
# "in_progress". add_assigned_status() widens the CHECK rule on an existing
# table and moves open-but-assigned tickets to the new status.
#
# Then branches arrived. add_branches_to_users() adds users.branch_id to an
# existing table and puts every existing account in Princeton-Plainsboro,
# the original site.
#
# Basement floors came next: allow_basement_floors() relaxes the CHECK on
# locations.floor from ">= 1" to "<> 0" so negative floor numbers are allowed.
# (The buildings changes for branches and basements are plain idempotent SQL
# in SCHEMA, because ADD COLUMN IF NOT EXISTS needs no "if".)
#
# The db_admin role came last: add_db_admin_role() widens the role CHECK on
# an existing users table.
#
# All of these functions do nothing on a database that is already up to
# date, and on a brand-new project they would not exist at all.

def replace_old_locations_table(cursor):
    """Drop the old free-text locations table if it is still there."""
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'locations'
          AND column_name = 'building'
        """
    )
    if cursor.fetchone() is None:
        return  # already the new shape (or no table yet)

    logger.info("Old locations table found; replacing it")
    cursor.execute("UPDATE incidents SET location_id = NULL")
    # CASCADE also removes the foreign key from incidents to this table;
    # restore_incident_location_link() puts it back on the new table.
    cursor.execute("DROP TABLE locations CASCADE")


def restore_incident_location_link(cursor):
    """Re-add incidents.location_id -> locations(id) if it is missing."""
    cursor.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = 'incidents_location_id_fkey'"
    )
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        ALTER TABLE incidents
        ADD CONSTRAINT incidents_location_id_fkey
        FOREIGN KEY (location_id) REFERENCES locations (id) ON DELETE RESTRICT
        """
    )


def allow_deleting_users_with_history(cursor):
    """
    Let incidents.reported_by and messages.user_id be NULL, cleared when
    the user is deleted (ON DELETE SET NULL) instead of blocking the delete.
    """
    for table, column in [("incidents", "reported_by"), ("messages", "user_id")]:
        constraint = f"{table}_{column}_fkey"

        # confdeltype is the ON DELETE rule: 'r' = RESTRICT, 'n' = SET NULL
        cursor.execute(
            "SELECT confdeltype FROM pg_constraint WHERE conname = %s",
            (constraint,),
        )
        row = cursor.fetchone()
        if row is not None and row["confdeltype"] == "n":
            continue  # already up to date

        logger.info("Upgrading %s.%s to ON DELETE SET NULL", table, column)
        cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
        cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        cursor.execute(
            f"""
            ALTER TABLE {table}
            ADD CONSTRAINT {constraint}
            FOREIGN KEY ({column}) REFERENCES users (id) ON DELETE SET NULL
            """
        )


def add_assigned_status(cursor):
    """
    Allow status = 'assigned' on an existing incidents table, and move any
    ticket that is still 'open' but has an engineer to 'assigned'.
    """
    cursor.execute(
        """
        SELECT pg_get_constraintdef(oid) AS rule
        FROM pg_constraint
        WHERE conname = 'incidents_status_check'
        """
    )
    row = cursor.fetchone()
    if row is not None and "assigned" not in row["rule"]:
        logger.info("Adding 'assigned' to the allowed incident statuses")
        cursor.execute("ALTER TABLE incidents DROP CONSTRAINT incidents_status_check")
        cursor.execute(
            """
            ALTER TABLE incidents
            ADD CONSTRAINT incidents_status_check
            CHECK (status IN ('open', 'assigned', 'in_progress', 'blocked', 'resolved', 'closed'))
            """
        )

    # Safe to run every time: it only touches tickets in the old state.
    cursor.execute(
        "UPDATE incidents SET status = 'assigned' WHERE status = 'open' AND assigned_to IS NOT NULL"
    )
    if cursor.rowcount:
        logger.info("Moved %s open-but-assigned tickets to 'assigned'", cursor.rowcount)


def add_branches_to_users(cursor):
    """
    Give an existing users table its branch_id column. Accounts created
    before branches existed all belong to Princeton-Plainsboro.
    """
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'branch_id'
        """
    )
    if cursor.fetchone() is not None:
        return  # already there

    logger.info("Adding branch_id to users; existing accounts go to Princeton-Plainsboro")
    cursor.execute(
        "ALTER TABLE users ADD COLUMN branch_id BIGINT REFERENCES branches (id) ON DELETE RESTRICT"
    )
    cursor.execute(
        """
        UPDATE users
        SET branch_id = (SELECT id FROM branches WHERE name = 'Princeton-Plainsboro')
        WHERE branch_id IS NULL
        """
    )
    cursor.execute("ALTER TABLE users ALTER COLUMN branch_id SET NOT NULL")


def add_users_directory_index(cursor):
    """
    The employee directory: one branch's accounts, newest first, by page.
    Created here rather than in SCHEMA because the column has to exist
    first (see add_branches_to_users). Safe to run every time.
    """
    cursor.execute("CREATE INDEX IF NOT EXISTS users_branch_created_idx ON users (branch_id, created_at DESC, id DESC)")


def add_branches_to_incidents(cursor):
    """
    Give an existing incidents table its branch_id column. A ticket made
    before this belongs to its building's branch, else its reporter's
    branch, else Princeton-Plainsboro. The index is created here rather
    than in SCHEMA because the column has to exist first.
    """
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'incidents' AND column_name = 'branch_id'
        """
    )
    if cursor.fetchone() is None:
        logger.info("Adding branch_id to incidents, from each ticket's building or reporter")
        cursor.execute(
            "ALTER TABLE incidents ADD COLUMN branch_id BIGINT REFERENCES branches (id) ON DELETE RESTRICT"
        )
        cursor.execute(
            """
            UPDATE incidents i
            SET branch_id = COALESCE(
                (SELECT b.branch_id FROM locations l JOIN buildings b ON b.id = l.building_id WHERE l.id = i.location_id),
                (SELECT u.branch_id FROM users u WHERE u.id = i.reported_by),
                (SELECT id FROM branches WHERE name = 'Princeton-Plainsboro')
            )
            WHERE branch_id IS NULL
            """
        )
        cursor.execute("ALTER TABLE incidents ALTER COLUMN branch_id SET NOT NULL")

    cursor.execute("CREATE INDEX IF NOT EXISTS incidents_branch_id_idx ON incidents (branch_id)")


def allow_basement_floors(cursor):
    """Let locations.floor be negative (basements) on an existing table."""
    cursor.execute(
        "SELECT pg_get_constraintdef(oid) AS rule FROM pg_constraint WHERE conname = 'locations_floor_check'"
    )
    row = cursor.fetchone()
    if row is None or ">= 1" not in row["rule"]:
        return  # already the new rule (or no constraint to fix)

    logger.info("Allowing basement floors in locations")
    cursor.execute("ALTER TABLE locations DROP CONSTRAINT locations_floor_check")
    cursor.execute("ALTER TABLE locations ADD CONSTRAINT locations_floor_check CHECK (floor <> 0)")


def add_db_admin_role(cursor):
    """Allow role = 'db_admin' on an existing users table."""
    cursor.execute(
        "SELECT pg_get_constraintdef(oid) AS rule FROM pg_constraint WHERE conname = 'users_role_check'"
    )
    row = cursor.fetchone()
    if row is None or "db_admin" in row["rule"]:
        return  # already allowed

    logger.info("Adding 'db_admin' to the allowed roles")
    cursor.execute("ALTER TABLE users DROP CONSTRAINT users_role_check")
    cursor.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT users_role_check
        CHECK (role IN ('db_admin', 'facility_admin', 'engineer', 'employee'))
        """
    )


# ---------------------------------------------------------------------------
# The db admin account
# ---------------------------------------------------------------------------
#
# Every deployment gets one db admin account, created (or put back) by the
# migration. It manages roles across every branch and is the only account
# allowed to run this migration once it exists.
#
# The password is fixed because this is a workshop project. In a real
# system the first admin would be created by someone with direct database
# access, and the password would come from a secret, never from code.

DB_ADMIN_EMAIL = "admin@admin.com"
DB_ADMIN_PASSWORD = "admin123"
DB_ADMIN_NAME = "admin"
DB_ADMIN_BRANCH = "Princeton-Plainsboro"


# Tables whose id is handed out by PostgreSQL (GENERATED ALWAYS AS IDENTITY).
ID_TABLES = ["branches", "users", "buildings", "locations", "incidents", "messages", "refresh_tokens"]


def move_id_counters_past_existing_rows(cursor):
    """
    Make sure the next id PostgreSQL hands out is above every id a table
    already holds.

    Normally that is automatic. But seed.sql inserts rows with fixed ids
    (OVERRIDING SYSTEM VALUE), which does not move the counter, so the next
    ordinary INSERT would be given an id that is already taken and fail with
    "duplicate key". The same happens after restoring a dump. This runs on
    every migration and after every seed load, and does nothing when the
    counters are already ahead.
    """
    for table in ID_TABLES:
        cursor.execute(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {table}")
        max_id = cursor.fetchone()["max_id"]

        cursor.execute("SELECT pg_get_serial_sequence(%s, 'id') AS counter", (table,))
        counter = cursor.fetchone()["counter"]  # e.g. "public.users_id_seq"

        # is_called = False means last_value is the NEXT id; True means the
        # next id is last_value + 1.
        cursor.execute(f"SELECT last_value, is_called FROM {counter}")
        row = cursor.fetchone()
        next_id = row["last_value"] + 1 if row["is_called"] else row["last_value"]

        if max_id >= next_id:
            logger.info("Moving %s ids past %s", table, max_id)
            cursor.execute("SELECT setval(%s, %s, false)", (counter, max_id + 1))


def ensure_db_admin_account(cursor):
    """Create the db admin account, or make sure it still has the role."""
    cursor.execute("SELECT id, role, name FROM users WHERE email = %s", (DB_ADMIN_EMAIL,))
    existing = cursor.fetchone()

    if existing is None:
        logger.info("Creating the db admin account")
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, name, role, branch_id)
            VALUES (%s, %s, %s, %s, (SELECT id FROM branches WHERE name = %s))
            """,
            (DB_ADMIN_EMAIL, hash_password(DB_ADMIN_PASSWORD), DB_ADMIN_NAME, ROLE_DB_ADMIN, DB_ADMIN_BRANCH),
        )
    elif existing["role"] != ROLE_DB_ADMIN or existing["name"] != DB_ADMIN_NAME:
        logger.info("Restoring the db admin account's role")
        cursor.execute(
            "UPDATE users SET role = %s, name = %s, updated_at = NOW() WHERE id = %s",
            (ROLE_DB_ADMIN, DB_ADMIN_NAME, existing["id"]),
        )


def db_admin_exists():
    """True once the users table exists and holds a db admin."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.users') IS NOT NULL AS has_table")
            if not cursor.fetchone()["has_table"]:
                return False
            cursor.execute("SELECT 1 FROM users WHERE role = %s LIMIT 1", (ROLE_DB_ADMIN,))
            return cursor.fetchone() is not None
    finally:
        connection.rollback()  # a read: end the transaction either way


def require_db_admin(event):
    """
    Only a db admin may run or inspect the migration.

    The very first run has nobody to check against (it is what creates the
    users table and the account), so until a db admin exists the endpoint
    is open. After that, a valid db admin token is required.
    """
    if not db_admin_exists():
        return
    caller = current_user(event)
    require_role(caller, [ROLE_DB_ADMIN])


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------
#
# seed.sql (next to this file) holds the accounts, buildings and tickets from
# local development. A db admin can load it into a deployment to have
# something to look at. It REPLACES what is in these tables, so the request
# has to say {"confirm": "RESET"}. Temporary: for a real system the sample
# data would live in a test fixture, never in a production deployment.

SEED_FILE = os.path.join(os.path.dirname(__file__), "seed.sql")
# Emptied before loading. refresh_tokens is not in the file but is cleared
# too, because it points at users that are about to be replaced.
SEED_TABLES = ["users", "buildings", "building_floors", "locations", "incidents",
               "messages", "refresh_tokens", "ticket_reads"]


def load_seed():
    """Empty the seed tables and load seed.sql. Returns rows per table."""
    with open(SEED_FILE, encoding="utf-8") as file:
        sql = file.read()

    # One transaction: the tables are never left empty if the file fails
    # to load half-way.
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE {', '.join(SEED_TABLES)} RESTART IDENTITY CASCADE")
            cursor.execute(sql)
            # The file sets ids by hand; the counters must move past them.
            move_id_counters_past_existing_rows(cursor)
            counts = {}
            for table in SEED_TABLES:
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table}")
                counts[table] = cursor.fetchone()["n"]
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return counts


def existing_tables():
    """Return the names from TABLES that exist in the database."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            rows = cursor.fetchall()
    finally:
        connection.rollback()  # end the read-only transaction

    found = [row["table_name"] for row in rows]
    return [name for name in TABLES if name in found]


def handler(event=None, context=None):
    """
    Lambda entry point.

    POST creates the tables, GET only reports them.
    POST /api/migrations/seed loads the sample data (db admin only).
    """
    method = http_method(event or {})
    segments = path_segments(event or {}, "migrations")

    try:
        require_db_admin(event or {})

        # /api/migrations/seed
        if segments == ["seed"]:
            if method != "POST":
                return method_not_allowed(method)
            if json_body(event).get("confirm") != "RESET":
                raise HttpError(400, "Send {\"confirm\": \"RESET\"}: this replaces every account, building and ticket")
            counts = load_seed()
            logger.info("Sample data loaded: %s", counts)
            return json_response(200, {"message": "Sample data loaded", "rows": counts})

        if segments:
            return json_response(404, {"error": "Not found"})

        if method == "POST":
            apply_schema()
            tables = existing_tables()
            logger.info("Schema applied, tables: %s", tables)
            return json_response(200, {"message": "Schema applied", "tables": tables})

        if method == "GET":
            tables = existing_tables()
            missing = [name for name in TABLES if name not in tables]
            return json_response(200, {"tables": tables, "missing": missing})

        return method_not_allowed(method)

    except HttpError as error:
        return error.to_response()
    except Exception as error:
        # Throw away the half-done transaction, or the reused connection
        # would refuse every later request with "transaction is aborted".
        get_connection().rollback()
        logger.error("Migration failed: %s", error)
        return json_response(500, {"error": "Migration failed", "detail": str(error)})
