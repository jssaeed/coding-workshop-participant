"""
Database helpers shared by every service.

Each Lambda container keeps one open connection and reuses it between
requests, because opening a connection is slow. Services never talk to
psycopg directly; they call the small functions at the bottom of this file.

Important psycopg rule: nothing is saved until you call commit(). Every helper
below finishes its own transaction (commit for writes, rollback for reads) so
a request never leaves one half-open.
"""

import os

from psycopg import connect
from psycopg.rows import dict_row

IS_LOCAL = os.getenv("IS_LOCAL", "false") == "true"

# Connection settings come from environment variables that Terraform sets on
# every Lambda. The defaults match the local development database.
# Aurora (cloud) requires TLS ("sslmode=require"); local PostgreSQL has none.
CONNECTION_STRING = (
    f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
    f"port={os.getenv('POSTGRES_PORT', '5432')} "
    f"user={os.getenv('POSTGRES_USER', 'postgres')} "
    f"password={os.getenv('POSTGRES_PASS', 'postgres123')} "
    f"dbname={os.getenv('POSTGRES_NAME', 'postgres')} "
    f"sslmode={'disable' if IS_LOCAL else 'require'} "
    f"connect_timeout=15"
)

# The one connection this container reuses. None until first needed.
_connection = None


def get_connection():
    """Return the open connection, connecting first if needed."""
    global _connection
    if _connection is None or _connection.closed:
        # dict_row makes every row a dict, so code can say row["title"]
        # instead of row[1].
        _connection = connect(CONNECTION_STRING, row_factory=dict_row)
    return _connection


def fetch_all(sql, params=None):
    """Run a SELECT and return all rows as a list of dicts."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        connection.rollback()  # reads still open a transaction; close it
        return rows
    except Exception:
        connection.rollback()
        raise


def fetch_one(sql, params=None):
    """Run a SELECT and return the first row as a dict, or None."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        connection.rollback()
        return row
    except Exception:
        connection.rollback()
        raise


def execute(sql, params=None):
    """
    Run an INSERT, UPDATE or DELETE and commit it.

    If the SQL ends with RETURNING, the returned row is given back as a dict.
    Otherwise the number of rows changed is returned.
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.description:  # the statement had a RETURNING clause
                result = cursor.fetchone()
            else:
                result = cursor.rowcount
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def execute_many(statements):
    """
    Run several writes so that they all save or none do.

    statements is a list of (sql, params) pairs. Used when two changes belong
    together, like changing a ticket's status and adding the message that
    records it.
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for sql, params in statements:
                cursor.execute(sql, params)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
