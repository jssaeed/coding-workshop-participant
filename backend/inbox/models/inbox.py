"""
Inbox model: which of a user's tickets have activity they have not seen.

"Unread" is derived, not stored: a message counts as unread for a user when it
is on a ticket they reported or are assigned to, someone else wrote it, and it
is newer than the user's read watermark on that ticket (ticket_reads).
"""

from lib.database import execute, fetch_all, fetch_one

# The set of messages a user has not seen yet. Every query below builds on it,
# so the definition of "unread" lives in exactly one place.
_UNREAD = """
    SELECT m.id, m.incident_id, m.user_id, m.message, m.created_at
      FROM messages m
      JOIN incidents i ON i.id = m.incident_id
      LEFT JOIN ticket_reads r
             ON r.incident_id = i.id AND r.user_id = %(user_id)s
     WHERE (i.reported_by = %(user_id)s OR i.assigned_to = %(user_id)s)
       AND m.user_id <> %(user_id)s
       AND (r.last_read_at IS NULL OR m.created_at > r.last_read_at)
"""

def unread_count(user_id):
    """Total unread messages across all of the user's tickets."""
    row = fetch_one(
        f"SELECT COUNT(*) AS unread FROM ({_UNREAD}) AS unread",
        {"user_id": user_id},
    )
    return row["unread"]

def unread_by_ticket(user_id):
    """
    One row per ticket with unread activity, most recent activity first.

    Each row carries the unread count and the latest unread message with its
    author, which is all the inbox list needs to render.
    """
    return fetch_all(
        f"""
        WITH unread AS ({_UNREAD}),
        latest AS (
            SELECT DISTINCT ON (incident_id)
                   incident_id, message, created_at, user_id
              FROM unread
             ORDER BY incident_id, created_at DESC, id DESC
        ),
        counts AS (
            SELECT incident_id, COUNT(*) AS unread_count
              FROM unread
             GROUP BY incident_id
        )
        SELECT i.id, i.title, i.status, i.priority,
               c.unread_count,
               l.message AS latest_message,
               l.created_at AS latest_at,
               u.id AS latest_author_id,
               u.name AS latest_author_name
          FROM counts c
          JOIN latest l ON l.incident_id = c.incident_id
          JOIN incidents i ON i.id = c.incident_id
          JOIN users u ON u.id = l.user_id
         ORDER BY l.created_at DESC
        """,
        {"user_id": user_id},
    )

def find_access_row(incident_id):
    """Return the columns needed to decide who may act on a ticket, or None."""
    return fetch_one(
        "SELECT id, reported_by, assigned_to FROM incidents WHERE id = %s",
        (incident_id,),
    )

def mark_read(user_id, incident_id):
    """Move the user's watermark on one ticket to now. Returns the row."""
    return execute(
        """
        INSERT INTO ticket_reads (user_id, incident_id, last_read_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id, incident_id) DO UPDATE SET last_read_at = NOW()
        RETURNING incident_id, last_read_at
        """,
        (user_id, incident_id),
        returning=True,
    )

def mark_all_read(user_id):
    """Move the user's watermark to now on every ticket they are involved in."""
    return execute(
        """
        INSERT INTO ticket_reads (user_id, incident_id, last_read_at)
        SELECT %(user_id)s, id, NOW()
          FROM incidents
         WHERE reported_by = %(user_id)s OR assigned_to = %(user_id)s
        ON CONFLICT (user_id, incident_id) DO UPDATE SET last_read_at = NOW()
        """,
        {"user_id": user_id},
    )
