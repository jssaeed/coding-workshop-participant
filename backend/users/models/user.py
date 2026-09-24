"""
User model: the SQL for the users table.

Every value goes into the query as a parameter (the %s placeholders), never
pasted into the SQL text. That is what stops SQL injection.

Note that password_hash is only selected in find_by_email_for_login. Every
other query leaves it out, so it can never be sent to a client by accident.
"""

from lib.database import execute, fetch_all, fetch_one

# The columns every read returns: the user plus their branch's name.
SELECT_USER = """
    SELECT u.id, u.email, u.name, u.role, u.created_at, u.updated_at,
           u.branch_id, b.name AS branch_name
    FROM users u
    JOIN branches b ON b.id = u.branch_id
"""


def create(email, password_hash, name, role, branch_id):
    """Insert a user and return the new row."""
    row = execute(
        """
        INSERT INTO users (email, password_hash, name, role, branch_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (email, password_hash, name, role, branch_id),
    )
    return find_by_id(row["id"])


def find_by_id(user_id):
    """Return one user, or None."""
    return fetch_one(SELECT_USER + " WHERE u.id = %s", (user_id,))


def find_by_email_for_login(email):
    """Return one user including password_hash, or None. Login only."""
    return fetch_one(
        """
        SELECT u.id, u.email, u.name, u.role, u.created_at, u.updated_at,
               u.branch_id, b.name AS branch_name, u.password_hash
        FROM users u
        JOIN branches b ON b.id = u.branch_id
        WHERE u.email = %s
        """,
        (email,),
    )


def email_exists(email):
    """True if an account already uses this email."""
    row = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    return row is not None


def list_all(branch_id=None, role=None):
    """
    Return users newest first: those at one branch, or every branch when
    branch_id is None (the db admin's view). Optionally only one role.
    """
    conditions = ["TRUE"]
    params = []
    if branch_id is not None:
        conditions.append("u.branch_id = %s")
        params.append(branch_id)
    if role is not None:
        conditions.append("u.role = %s")
        params.append(role)
    return fetch_all(
        SELECT_USER + " WHERE " + " AND ".join(conditions) + " ORDER BY u.created_at DESC",
        params,
    )


def update_role(user_id, role):
    """Change a user's role. Returns the updated row, or None if no such user."""
    execute(
        "UPDATE users SET role = %s, updated_at = NOW() WHERE id = %s",
        (role, user_id),
    )
    return find_by_id(user_id)


def delete(user_id):
    """
    Delete a user. Returns how many rows were deleted (0 or 1).

    Their tickets and messages stay; the schema's ON DELETE SET NULL rules
    clear the link, and the API then shows them as a deleted user.
    """
    return execute("DELETE FROM users WHERE id = %s", (user_id,))
