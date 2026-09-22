"""
Message model: every SQL statement that touches the messages table.

Reads join the author so a thread renders names without a lookup per message.
"""

from lib.database import execute, fetch_all, fetch_one

_SELECT = """
    SELECT m.id, m.incident_id, m.message, m.created_at, m.updated_at,
           m.user_id, u.name AS author_name, u.email AS author_email, u.role AS author_role
      FROM messages m
      JOIN users u ON u.id = m.user_id
"""

def create(incident_id, user_id, message):
    """Post a message and return it with its author joined."""
    row = execute(
        """
        INSERT INTO messages (incident_id, user_id, message)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (incident_id, user_id, message),
        returning=True,
    )
    return find_by_id(row["id"])

def find_by_id(message_id):
    """Return one message, or None."""
    return fetch_one(f"{_SELECT} WHERE m.id = %s", (message_id,))

def list_for_incident(incident_id):
    """Return a ticket's thread, oldest first."""
    return fetch_all(
        f"{_SELECT} WHERE m.incident_id = %s ORDER BY m.created_at ASC, m.id ASC",
        (incident_id,),
    )
