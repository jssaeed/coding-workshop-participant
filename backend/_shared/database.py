"""
Database helpers shared by every service.

Each Lambda container keeps one open connection and reuses it between
requests, because opening a connection is slow. Services never talk to
psycopg directly; they call the small functions at the bottom of this file.

Important psycopg rule: nothing is saved until you call commit(). Every helper
below finishes its own transaction (commit for writes, rollback for reads) so
a request never leaves one half-open.

When several steps must save together, wrap them in "with transaction():".
Inside that block the helpers stop committing on their own; the whole block
is committed at the end, or rolled back if anything in it raises.

Rule for the services: every request that writes runs its checks and its
writes inside ONE "with transaction():" block, in the controller. A single
INSERT is atomic by itself, but the check before it ("does this email
exist?", "is this building at my branch?") is not, and the block is what
makes the check and the write one unit. Reads never need the block.
"""

import os
from contextlib import contextmanager

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

# True while inside a "with transaction():" block. A Lambda container handles
# one request at a time, so a single flag is enough.
_in_transaction = False


def get_connection():
    """Return the open connection, connecting first if needed."""
    global _connection
    if _connection is None or _connection.closed:
        # dict_row makes every row a dict, so code can say row["title"]
        # instead of row[1].
        _connection = connect(CONNECTION_STRING, row_factory=dict_row)
    return _connection


@contextmanager
def transaction():
    """
    Run everything inside the "with" block as one transaction.

        with transaction():
            refresh_token_model.revoke(old_id)
            refresh_token_model.create(...)

    Both saves happen, or neither does. A block inside another block simply
    joins the outer one.
    """
    global _in_transaction
    if _in_transaction:
        yield  # already in a transaction: the outer block will commit
        return

    connection = get_connection()
    _in_transaction = True
    try:
        yield
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        _in_transaction = False


def finish_read(connection):
    """After a SELECT: close the transaction it opened, unless we are inside
    a transaction() block, which will end it later."""
    if not _in_transaction:
        connection.rollback()


def finish_write(connection):
    """After a write: save it, unless we are inside a transaction() block,
    which will save everything at the end."""
    if not _in_transaction:
        connection.commit()


def undo(connection):
    """After an error: throw the transaction away. Inside a transaction()
    block the block does this itself, once, for all the steps."""
    if not _in_transaction:
        connection.rollback()


def fetch_all(sql, params=None):
    """Run a SELECT and return all rows as a list of dicts."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        finish_read(connection)
        return rows
    except Exception:
        undo(connection)
        raise


def fetch_one(sql, params=None):
    """Run a SELECT and return the first row as a dict, or None."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        finish_read(connection)
        return row
    except Exception:
        undo(connection)
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
        finish_write(connection)
        return result
    except Exception:
        undo(connection)
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
        finish_write(connection)
    except Exception:
        undo(connection)
        raise
