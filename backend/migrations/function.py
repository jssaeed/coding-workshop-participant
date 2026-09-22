"""
Schema migration service.

Applies schema.sql to PostgreSQL. The script is idempotent, so invoking this
endpoint repeatedly is safe and is the normal way to bring a fresh local or
cloud database up to date.

    POST /api/migrations   apply schema.sql
    GET  /api/migrations   report which tables currently exist
"""

import logging
from pathlib import Path

from psycopg import connect

from lib.database import PG_CONFIG
from lib.request import http_method
from lib.responses import json_response, method_not_allowed

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Tables schema.sql is expected to create, in dependency order.
EXPECTED_TABLES = ("users", "locations", "incidents", "messages")

# Arbitrary but fixed key identifying the schema lock. Two concurrent Lambda
# invocations would otherwise race to create the same tables.
ADVISORY_LOCK_KEY = 4711_2026

def apply_schema():
    """
    Run schema.sql inside a single transaction.

    A transaction-scoped advisory lock serializes concurrent invocations: the
    second one waits, then re-runs the same idempotent statements as no-ops.

    Returns:
        list[str]: the tables present after the script has run
    """
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    # A dedicated short-lived connection: migrations run rarely, and reusing a
    # pooled connection would keep a DDL transaction open across invocations.
    with connect(PG_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            cur.execute(sql)
        # Commit the DDL; psycopg does not autocommit.
        conn.commit()

    return existing_tables()

def existing_tables():
    """
    List which of the expected tables exist in the public schema.

    Returns:
        list[str]: table names, ordered as in EXPECTED_TABLES
    """
    with connect(PG_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = ANY(%s)
                """,
                (list(EXPECTED_TABLES),),
            )
            found = {row[0] for row in cur.fetchall()}

    return [name for name in EXPECTED_TABLES if name in found]

def handler(event=None, context=None):
    """
    Apply or inspect the database schema.

    Args:
        event (dict, optional): The Lambda event
        context (object, optional): The Lambda context

    Returns:
        dict: A response object with statusCode, headers, and body
    """
    logger.debug("Received event: %s", event)

    method = http_method(event or {})

    try:
        if method == "POST":
            tables = apply_schema()
            missing = [name for name in EXPECTED_TABLES if name not in tables]
            if missing:
                # The script ran without error yet a table is absent, so
                # schema.sql and EXPECTED_TABLES have drifted apart.
                logger.error("Schema applied but tables missing: %s", missing)
                return json_response(500, {"error": "Schema incomplete", "missing": missing})

            logger.info("Schema applied: %s", tables)
            return json_response(200, {"message": "Schema applied", "tables": tables})

        if method == "GET":
            tables = existing_tables()
            return json_response(200, {
                "tables": tables,
                "missing": [name for name in EXPECTED_TABLES if name not in tables],
            })

        return method_not_allowed(method)
    except Exception as e:
        logger.error("Migration error: %s", str(e))
        return json_response(500, {"error": "Migration failed", "detail": str(e)})
