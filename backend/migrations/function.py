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

from lib.database import get_connection
from lib.request import http_method
from lib.responses import json_response, method_not_allowed

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
    # --- users -----------------------------------------------------------
    # Emails are stored in lower case (the users service does this), so a
    # plain UNIQUE rule is enough to stop the same address signing up twice.
    """
    CREATE TABLE IF NOT EXISTS users (
        id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        email         TEXT        NOT NULL UNIQUE,
        password_hash TEXT        NOT NULL,
        name          TEXT        NOT NULL CHECK (name <> ''),
        role          TEXT        NOT NULL DEFAULT 'employee'
                                  CHECK (role IN ('facility_admin', 'engineer', 'employee')),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,

    # --- locations -------------------------------------------------------
    # Where an incident happened. "room" is stored as '' instead of NULL when
    # not given, because UNIQUE treats every NULL as different and would then
    # allow the same building + floor to be added many times.
    """
    CREATE TABLE IF NOT EXISTS locations (
        id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        building   TEXT        NOT NULL CHECK (building <> ''),
        floor      TEXT        NOT NULL CHECK (floor <> ''),
        room       TEXT        NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (building, floor, room)
    )
    """,

    # --- incidents -------------------------------------------------------
    # A ticket. reported_by is who filed it, assigned_to is the engineer
    # working on it (NULL until an admin assigns someone).
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        title       TEXT        NOT NULL CHECK (title <> ''),
        description TEXT        NOT NULL DEFAULT '',
        status      TEXT        NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open', 'in_progress', 'blocked', 'resolved', 'closed')),
        priority    SMALLINT    NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
        location_id BIGINT      REFERENCES locations (id) ON DELETE RESTRICT,
        reported_by BIGINT      NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
        assigned_to BIGINT      REFERENCES users (id) ON DELETE SET NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ
    )
    """,
    # Indexes make the ticket list filters fast.
    "CREATE INDEX IF NOT EXISTS incidents_status_idx      ON incidents (status)",
    "CREATE INDEX IF NOT EXISTS incidents_priority_idx    ON incidents (priority)",
    "CREATE INDEX IF NOT EXISTS incidents_reported_by_idx ON incidents (reported_by)",
    "CREATE INDEX IF NOT EXISTS incidents_assigned_to_idx ON incidents (assigned_to)",

    # --- messages --------------------------------------------------------
    # The conversation on a ticket. Status and assignment changes are also
    # saved here as messages, so the thread shows the ticket's history.
    # ON DELETE CASCADE: deleting a ticket deletes its messages too.
    """
    CREATE TABLE IF NOT EXISTS messages (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        incident_id BIGINT      NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
        user_id     BIGINT      NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
        message     TEXT        NOT NULL CHECK (message <> ''),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS messages_incident_id_idx ON messages (incident_id)",

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
TABLES = ["users", "locations", "incidents", "messages", "ticket_reads"]


def apply_schema():
    """Run every statement in SCHEMA, in order, and save the result."""
    connection = get_connection()
    with connection.cursor() as cursor:
        for statement in SCHEMA:
            cursor.execute(statement)
    connection.commit()


def existing_tables():
    """Return the names from TABLES that exist in the database."""
    connection = get_connection()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        rows = cursor.fetchall()
    connection.rollback()  # end the read-only transaction

    found = [row["table_name"] for row in rows]
    return [name for name in TABLES if name in found]


def handler(event=None, context=None):
    """
    Lambda entry point.

    POST creates the tables, GET only reports them.
    """
    method = http_method(event or {})

    try:
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

    except Exception as error:
        logger.error("Migration failed: %s", error)
        return json_response(500, {"error": "Migration failed", "detail": str(error)})
