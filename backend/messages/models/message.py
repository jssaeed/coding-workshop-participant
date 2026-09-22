"""
Message model: the SQL for the messages table.

Reads join the users table so each message comes back with its author's name.
"""

from lib.database import execute, fetch_all, fetch_one

SELECT_MESSAGE = """
    SELECT m.id, m.incident_id, m.message, m.created_at, m.updated_at,
           m.user_id, u.name AS author_name, u.email AS author_email, u.role AS author_role
    FROM messages m
    JOIN users u ON u.id = m.user_id
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


def list_for_incident(incident_id):
    """A ticket's whole thread, oldest first."""
    return fetch_all(
        SELECT_MESSAGE + " WHERE m.incident_id = %s ORDER BY m.created_at ASC, m.id ASC",
        (incident_id,),
    )
