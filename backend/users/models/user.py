"""
User model: every SQL statement that touches the users table.

Values are always passed as query parameters, never formatted into the SQL
string, so input cannot alter the statement.
"""

from psycopg.errors import ForeignKeyViolation, RestrictViolation

from lib.database import execute, fetch_all, fetch_one

class UserInUse(Exception):
    """Raised when a user cannot be deleted because records still point at them."""

# Columns safe to return to clients. password_hash is deliberately excluded so
# it cannot leak through a view by accident.
PUBLIC_COLUMNS = "id, email, name, role, created_at, updated_at"

def create(email, password_hash, name, role):
    """Insert a user and return the created row."""
    return execute(
        f"""
        INSERT INTO users (email, password_hash, name, role)
        VALUES (%s, %s, %s, %s)
        RETURNING {PUBLIC_COLUMNS}
        """,
        (email, password_hash, name, role),
        returning=True,
    )

def find_by_id(user_id):
    """Return one user without the password hash, or None."""
    return fetch_one(
        f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id = %s",
        (user_id,),
    )

def find_by_email_with_hash(email):
    """
    Return one user including the password hash, or None.

    Only the login path may call this.
    """
    return fetch_one(
        f"SELECT {PUBLIC_COLUMNS}, password_hash FROM users WHERE LOWER(email) = LOWER(%s)",
        (email,),
    )

def email_taken(email):
    """True when the email already belongs to an account."""
    return fetch_one(
        "SELECT 1 AS taken FROM users WHERE LOWER(email) = LOWER(%s)",
        (email,),
    ) is not None

def list_all(role=None):
    """Return all users, optionally filtered by role, newest first."""
    if role:
        return fetch_all(
            f"SELECT {PUBLIC_COLUMNS} FROM users WHERE role = %s ORDER BY created_at DESC",
            (role,),
        )
    return fetch_all(
        f"SELECT {PUBLIC_COLUMNS} FROM users ORDER BY created_at DESC"
    )

def update_role(user_id, role):
    """Change a user's role and return the updated row, or None if absent."""
    return execute(
        f"UPDATE users SET role = %s WHERE id = %s RETURNING {PUBLIC_COLUMNS}",
        (role, user_id),
        returning=True,
    )

def delete(user_id):
    """
    Delete a user.

    Returns:
        int: rows deleted (0 when no such user)

    Raises:
        UserInUse: the user has reported incidents or written messages, which
            the schema keeps (ON DELETE RESTRICT) rather than orphaning
    """
    try:
        return execute("DELETE FROM users WHERE id = %s", (user_id,))
    except (ForeignKeyViolation, RestrictViolation) as exc:
        raise UserInUse(user_id) from exc
