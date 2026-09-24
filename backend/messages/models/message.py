"""
Message model: the SQL for the messages table.

Reads join the users table so each message comes back with its author's name
(a LEFT JOIN, because the author's account may have been deleted since).
"""

from lib.database import execute, fetch_all, fetch_one

SELECT_MESSAGE = """
    SELECT m.id, m.incident_id, m.message, m.created_at, m.updated_at,
           m.user_id, u.name AS author_name, u.email AS author_email, u.role AS author_role
    FROM messages m
    LEFT JOIN users u ON u.id = m.user_id
"""


def create(incident_id, user_id, message):
    """Add a message and return it with the author's details."""
    row = execute(
        """
        INSERT INTO messages (incident_id, user_id, message)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (incident_id, user_id, message),
    )
    return find_by_id(row["id"])


def find_by_id(message_id):
    return fetch_one(SELECT_MESSAGE + " WHERE m.id = %s", (message_id,))


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def list_for_incident(incident_id, limit=DEFAULT_PAGE_SIZE, before_id=None):
    """
    One page of a ticket's thread: the `limit` newest messages, or the
    `limit` messages older than message `before_id`, returned oldest first
    so they read top to bottom.

    This is keyset pagination: instead of "skip N rows", the page is
    defined by where the previous one ended, so it costs the same however
    long the thread is and never shows a message twice when new ones
    arrive while the user is reading.

    Returns (messages, has_more): has_more says whether older messages
    exist beyond this page.
    """
    conditions = ["m.incident_id = %s"]
    params = [incident_id]
    if before_id is not None:
        # Older than the cursor message in thread order (created_at, then id).
        conditions.append("(m.created_at, m.id) < (SELECT c.created_at, c.id FROM messages c WHERE c.id = %s)")
        params.append(before_id)

    # One extra row tells us whether there is another page, without a count.
    newest_first = fetch_all(
        SELECT_MESSAGE + " WHERE " + " AND ".join(conditions)
        + " ORDER BY m.created_at DESC, m.id DESC LIMIT %s",
        params + [limit + 1],
    )
    has_more = len(newest_first) > limit
    page = newest_first[:limit]
    page.reverse()  # oldest first, as the thread is read
    return page, has_more


def count_for_incident(incident_id):
    """How many messages a ticket has in all."""
    return fetch_one("SELECT COUNT(*) AS n FROM messages WHERE incident_id = %s", (incident_id,))["n"]
