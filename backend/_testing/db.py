"""
The PostgreSQL test database for integration tests.

Integration tests run the real handlers against a real database, so every
SQL statement, constraint and transaction is exercised. They use a SEPARATE
database (incident_tracker_test by default) so the local development data
in the "postgres" database is never touched.

How it is set up:
  1. configure_environment() points lib.database at the test database. It
     must run before lib.database is imported, because the connection string
     is built at import time.
  2. ensure_test_database() creates the database if it is missing.
  3. apply_schema() runs the migrations service's schema on it.
  4. reset() empties every table between tests (branches are kept: the
     migration seeds them and users point at them).

Connection settings come from the same POSTGRES_* variables the services
use, with TEST_POSTGRES_NAME choosing the database name.
"""

import importlib.util
import itertools
import os
import sys

# Each service vendors its own psycopg, while the venv may carry a different
# release of the C accelerator (psycopg_c). Mixing the two breaks, so tests
# run psycopg's pure Python implementation. Must be set before psycopg loads.
os.environ.setdefault("PSYCOPG_IMPL", "python")

import bcrypt  # noqa: E402
import psycopg  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_FUNCTION = os.path.join(BACKEND_DIR, "migrations", "function.py")

TEST_DB_NAME = os.environ.get("TEST_POSTGRES_NAME", "incident_tracker_test")
# The local development database. Refuse to ever run the suite against it.
DEV_DB_NAME = "postgres"

# Every table the schema creates except branches, in no particular order
# (TRUNCATE ... CASCADE handles the foreign keys).
DATA_TABLES = ["users", "buildings", "building_floors", "locations", "incidents",
               "messages", "refresh_tokens", "ticket_reads"]

# Hashing a password properly takes a quarter of a second; test users use the
# cheapest bcrypt cost so hundreds of them cost nothing. check_password()
# still verifies them, because the cost is stored inside the hash.
_hash_cache = {}


def configure_environment():
    """Point the services at the test database. Call before importing lib.database."""
    if TEST_DB_NAME == DEV_DB_NAME:
        raise RuntimeError("TEST_POSTGRES_NAME must not be the development database")
    os.environ["IS_LOCAL"] = "true"  # no TLS, local dev secret allowed
    os.environ.setdefault("JWT_SECRET", "test-signing-secret-long-enough-for-hmac-sha256")
    os.environ["POSTGRES_NAME"] = TEST_DB_NAME
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_USER", "postgres")
    os.environ.setdefault("POSTGRES_PASS", "postgres123")


def maintenance_connection_string(dbname=DEV_DB_NAME):
    return (
        f"host={os.environ['POSTGRES_HOST']} port={os.environ['POSTGRES_PORT']} "
        f"user={os.environ['POSTGRES_USER']} password={os.environ['POSTGRES_PASS']} "
        f"dbname={dbname} sslmode=disable connect_timeout=3"
    )


_availability = None


def unavailable_reason():
    """None when PostgreSQL answers, otherwise why the integration tests skip."""
    global _availability
    if _availability is None:
        try:
            with psycopg.connect(maintenance_connection_string()):
                pass
            _availability = ""
        except Exception as error:  # noqa: BLE001 - any failure means "skip"
            _availability = f"PostgreSQL is not reachable ({error.__class__.__name__}: {error})"
    return _availability or None


def ensure_test_database():
    """Create the test database if it does not exist yet."""
    with psycopg.connect(maintenance_connection_string(), autocommit=True) as connection:
        row = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if row is None:
            connection.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')


def assert_using_test_database():
    """A last line of defence: the services must be connected to the test database."""
    import lib.database as database

    assert f"dbname={TEST_DB_NAME} " in database.CONNECTION_STRING, (
        "lib.database was imported before configure_environment() ran; "
        "the tests would use the wrong database"
    )


def migrations_module():
    """
    Load backend/migrations/function.py as a module, whichever service is
    under test. It only needs lib.*, which every service has a copy of.
    """
    name = "_testing_migrations_function"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, MIGRATIONS_FUNCTION)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def apply_schema():
    assert_using_test_database()
    migrations_module().apply_schema()


def drop_everything():
    """Empty the test database completely (for testing the migration itself)."""
    assert_using_test_database()
    import lib.database as database

    connection = database.get_connection()
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE")
        cursor.execute("CREATE SCHEMA public")
    connection.commit()


def reset():
    """Remove every row except the branches, and restart the id counters."""
    assert_using_test_database()
    import lib.database as database

    connection = database.get_connection()
    connection.rollback()  # throw away anything a failed test left open
    database._in_transaction = False
    database.execute(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE")


# --- factories ---------------------------------------------------------------
#
# These insert rows directly, so a test can set up "an engineer with two
# tickets" in three lines and then exercise one endpoint. They go through
# lib.database so they share the handler's connection.

_counter = itertools.count(1)


def fast_hash(password):
    if password not in _hash_cache:
        _hash_cache[password] = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")
    return _hash_cache[password]


def create_user(role="employee", branch_id=1, email=None, name=None, password="password123"):
    """Insert a user and return a dict with id, email, name, role, branch_id, password."""
    import lib.database as database

    number = next(_counter)
    email = email or f"{role}{number}@acme.inc"
    name = name or f"{role.replace('_', ' ').title()} {number}"
    row = database.execute(
        """
        INSERT INTO users (email, password_hash, name, role, branch_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, email, name, role, branch_id
        """,
        (email.lower(), fast_hash(password), name, role, branch_id),
    )
    return {**row, "password": password}


def token_for(user):
    """A real access token for a user dict (needs id, email, role)."""
    import lib.auth as auth

    return auth.create_access_token(user)


def create_building(branch_id=1, name=None, floors=3, basement_floors=0, rooms=None,
                    include_floor=False):
    """
    Insert a building with one building_floors row per floor.

    rooms: {floor: rooms} for floors that have a room count; others get 0.
    Returns the buildings row as a dict.
    """
    import lib.database as database

    name = name or f"Building {next(_counter)}"
    row = database.execute(
        """
        INSERT INTO buildings (branch_id, name, floors, basement_floors, room_numbers_include_floor)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, branch_id, name, floors, basement_floors, room_numbers_include_floor
        """,
        (branch_id, name, floors, basement_floors, include_floor),
    )
    rooms = rooms or {}
    all_floors = list(range(1, floors + 1)) + list(range(-1, -basement_floors - 1, -1))
    database.execute_many([
        ("INSERT INTO building_floors (building_id, floor, rooms) VALUES (%s, %s, %s)",
         (row["id"], floor, rooms.get(floor, 0)))
        for floor in all_floors
    ])
    return row


def create_location(building_id, floor, room=None):
    import lib.database as database

    return database.execute(
        """
        INSERT INTO locations (building_id, floor, room) VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (building_id, floor, room),
    ) or database.fetch_one(
        "SELECT id FROM locations WHERE building_id = %s AND floor = %s AND room IS NOT DISTINCT FROM %s",
        (building_id, floor, room),
    )


def create_incident(reported_by, title=None, description="", priority=3, status="open",
                    assigned_to=None, location_id=None, created_days_ago=0,
                    pending_status=None, pending_requested_by=None, branch_id=None, category="other"):
    """Insert a ticket and return its id. branch_id defaults to the reporter's branch (else 1)."""
    import lib.database as database

    title = title or f"Ticket {next(_counter)}"
    row = database.execute(
        """
        INSERT INTO incidents (title, description, priority, status, reported_by, assigned_to,
                               location_id, created_at, pending_status, pending_requested_by,
                               pending_requested_at, branch_id, category)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW() - make_interval(days => %s), %s, %s,
                CASE WHEN %s::text IS NULL THEN NULL ELSE NOW() END,
                COALESCE(%s, (SELECT branch_id FROM users WHERE id = %s), 1), %s)
        RETURNING id
        """,
        (title, description, priority, status, reported_by, assigned_to, location_id,
         created_days_ago, pending_status, pending_requested_by, pending_status,
         branch_id, reported_by, category),
    )
    return row["id"]


def create_message(incident_id, user_id, text=None, created_seconds_ago=0):
    """Insert a message and return its id. user_id may be None (deleted author)."""
    import lib.database as database

    text = text or f"Message {next(_counter)}"
    row = database.execute(
        """
        INSERT INTO messages (incident_id, user_id, message, created_at)
        VALUES (%s, %s, %s, NOW() - make_interval(secs => %s))
        RETURNING id
        """,
        (incident_id, user_id, text, created_seconds_ago),
    )
    return row["id"]


def create_refresh_token(user_id, expires_in_days=14, revoked=False):
    """Insert a refresh token row and return the raw token the client would hold."""
    import lib.auth as auth
    import lib.database as database

    token, token_hash, _ = auth.create_refresh_token()
    database.execute(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at, revoked_at)
        VALUES (%s, %s, NOW() + make_interval(days => %s), CASE WHEN %s THEN NOW() ELSE NULL END)
        """,
        (user_id, token_hash, expires_in_days, revoked),
    )
    return token


def execute(sql, params=None):
    """Run a write (INSERT/UPDATE/DELETE) and commit it. Reads must use fetch_*."""
    import lib.database as database

    return database.execute(sql, params)


def fetch_one(sql, params=None):
    import lib.database as database

    return database.fetch_one(sql, params)


def fetch_all(sql, params=None):
    import lib.database as database

    return database.fetch_all(sql, params)


def count(table, where="TRUE", params=None):
    return fetch_one(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params)["n"]
