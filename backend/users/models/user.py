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


# How the directory may be ordered (?sort=). Every order ends with the id so
# rows never swap places between pages. "role" puts the most senior first.
ROLE_ORDER = "CASE u.role WHEN 'db_admin' THEN 0 WHEN 'facility_admin' THEN 1 WHEN 'engineer' THEN 2 ELSE 3 END"
SORTS = {
    "created": "u.created_at %(dir)s, u.id %(dir)s",
    "name": "LOWER(u.name) %(dir)s, u.id %(dir)s",
    "role": ROLE_ORDER + " %(dir)s, LOWER(u.name) ASC, u.id ASC",
}
DEFAULT_SORT = "created"  # newest accounts first (with descending=True)


def _conditions(branch_id, roles, q):
    """The WHERE clause for list_all() and count(): (sql, params)."""
    conditions = ["TRUE"]
    params = []
    if branch_id is not None:
        conditions.append("u.branch_id = %s")
        params.append(branch_id)
    if roles:
        conditions.append("u.role = ANY(%s)")
        params.append(list(roles))
    if q:
        # Every word must appear in the name or the email, in any order.
        for word in q.split()[:5]:
            conditions.append("(u.name ILIKE %s OR u.email ILIKE %s)")
            params.extend([f"%{word}%", f"%{word}%"])
    return " WHERE " + " AND ".join(conditions), params


def list_all(branch_id=None, roles=None, q=None, sort=DEFAULT_SORT, descending=True, limit=None, offset=0):
    """
    Return one page of users: those at one branch, or every branch when
    branch_id is None (the db admin's view). roles keeps only those roles,
    q searches name and email, sort names an entry of SORTS.
    """
    where, params = _conditions(branch_id, roles, q)
    order = SORTS[sort] % {"dir": "DESC" if descending else "ASC"}
    sql = SELECT_USER + where + " ORDER BY " + order
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = params + [limit, offset]
    return fetch_all(sql, params)


def count(branch_id=None, roles=None, q=None):
    """How many users match the same filters list_all() takes."""
    where, params = _conditions(branch_id, roles, q)
    return fetch_one("SELECT COUNT(*) AS n FROM users u" + where, params)["n"]


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
