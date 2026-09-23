"""
Inbox model: finding the messages a user has not seen yet.

A message is UNREAD for a user when all of these are true:
  - it is on a ticket the user reported or is assigned to,
  - someone else wrote it,
  - it is newer than the user's last_read_at for that ticket in ticket_reads
    (or the user has no ticket_reads row for that ticket at all).

That definition is the one SQL query in unread_messages(). The other
functions build on it in plain Python.
"""

from lib.database import execute, fetch_all, fetch_one


def unread_messages(user_id):
    """
    Every unread message for this user, newest first, with the ticket's
    title/status/priority and the author's name.
    """
    return fetch_all(
        """
        SELECT m.id, m.incident_id, m.message, m.created_at,
               m.user_id AS author_id, u.name AS author_name,
               i.title, i.status, i.priority
        FROM messages m
        JOIN incidents i ON i.id = m.incident_id
        LEFT JOIN users u ON u.id = m.user_id
        LEFT JOIN ticket_reads r ON r.incident_id = i.id AND r.user_id = %(user_id)s
        WHERE (i.reported_by = %(user_id)s OR i.assigned_to = %(user_id)s)
          -- not my own messages. IS DISTINCT FROM (not <>) so messages whose
          -- author was deleted (user_id NULL) still count as unread.
          AND m.user_id IS DISTINCT FROM %(user_id)s
          AND (r.last_read_at IS NULL OR m.created_at > r.last_read_at)
        ORDER BY m.created_at DESC, m.id DESC
        """,
        {"user_id": user_id},
    )


def unread_count(user_id):
    """How many unread messages the user has in total."""
    return len(unread_messages(user_id))


def unread_by_ticket(user_id):
    """
    Group the unread messages by ticket.

    Returns a list of dicts, one per ticket, most recent activity first:
        {"incident": {...}, "unread_count": 2, "latest_message": {...}}
    """
    tickets = []
    seen = {}  # incident_id -> the entry in tickets for that ticket

    # Messages arrive newest first, so the first one we see for a ticket is
    # its latest message.
    for message in unread_messages(user_id):
        incident_id = message["incident_id"]

        if incident_id not in seen:
            entry = {
                "incident": {
                    "id": incident_id,
                    "title": message["title"],
                    "status": message["status"],
                    "priority": message["priority"],
                },
                "unread_count": 0,
                "latest_message": {
                    "message": message["message"],
                    "created_at": message["created_at"],
                    "author_id": message["author_id"],
                    "author_name": message["author_name"],
                },
            }
            tickets.append(entry)
            seen[incident_id] = entry

        seen[incident_id]["unread_count"] += 1

    return tickets


def find_basic_incident(incident_id):
    """Just enough of a ticket to check who may mark it read, or None."""
    return fetch_one(
        "SELECT id, reported_by, assigned_to FROM incidents WHERE id = %s",
        (incident_id,),
    )


def mark_read(user_id, incident_id):
    """
    Record that the user has seen this ticket's thread as of now.

    "ON CONFLICT ... DO UPDATE" means: insert the row, or if there already is
    one for this user and ticket, update its time instead.
    """
    return execute(
        """
        INSERT INTO ticket_reads (user_id, incident_id, last_read_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id, incident_id) DO UPDATE SET last_read_at = NOW()
        RETURNING incident_id, last_read_at
        """,
        (user_id, incident_id),
    )


def mark_all_read(user_id):
    """Record that the user has seen every ticket they are involved in."""
    execute(
        """
        INSERT INTO ticket_reads (user_id, incident_id, last_read_at)
        SELECT %(user_id)s, id, NOW()
        FROM incidents
        WHERE reported_by = %(user_id)s OR assigned_to = %(user_id)s
        ON CONFLICT (user_id, incident_id) DO UPDATE SET last_read_at = NOW()
        """,
        {"user_id": user_id},
    )
