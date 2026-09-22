"""
User model: the SQL for the users table.

Every value goes into the query as a parameter (the %s placeholders), never
pasted into the SQL text. That is what stops SQL injection.

Note that password_hash is only selected in find_by_email_for_login. Every
other query leaves it out, so it can never be sent to a client by accident.
"""

from psycopg.errors import ForeignKeyViolation, RestrictViolation

from lib.database import execute, fetch_all, fetch_one


class UserInUse(Exception):
    """Raised when a user cannot be deleted because tickets still refer to them."""


def create(email, password_hash, name, role):
    """Insert a user and return the new row."""
    return execute(
        """
        INSERT INTO users (email, password_hash, name, role)
        VALUES (%s, %s, %s, %s)
        RETURNING id, email, name, role, created_at, updated_at
        """,
        (email, password_hash, name, role),
    )


def find_by_id(user_id):
    """Return one user, or None."""
    return fetch_one(
        """
        SELECT id, email, name, role, created_at, updated_at
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )


def find_by_email_for_login(email):
    """Return one user including password_hash, or None. Login only."""
    return fetch_one(
        """
        SELECT id, email, name, role, created_at, updated_at, password_hash
        FROM users
        WHERE email = %s
        """,
        (email,),
    )


def email_exists(email):
    """True if an account already uses this email."""
    row = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    return row is not None


def list_all(role=None):
    """Return every user, newest first. Optionally only one role."""
    if role is None:
        return fetch_all(
            """
            SELECT id, email, name, role, created_at, updated_at
            FROM users
            ORDER BY created_at DESC
            """
        )
    return fetch_all(
        """
        SELECT id, email, name, role, created_at, updated_at
        FROM users
        WHERE role = %s
        ORDER BY created_at DESC
        """,
        (role,),
    )


def update_role(user_id, role):
    """Change a user's role. Returns the updated row, or None if no such user."""
    return execute(
        """
        UPDATE users
        SET role = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id, email, name, role, created_at, updated_at
        """,
        (role, user_id),
    )


def delete(user_id):
    """
    Delete a user. Returns how many rows were deleted (0 or 1).

    Raises UserInUse if the database refuses because incidents or messages
    still point at this user (the ON DELETE RESTRICT rules in the schema).
    """
    try:
        return execute("DELETE FROM users WHERE id = %s", (user_id,))
    except (ForeignKeyViolation, RestrictViolation):
        raise UserInUse(user_id)
