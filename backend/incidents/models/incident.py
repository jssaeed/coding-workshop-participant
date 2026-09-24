"""
Incident model: the SQL for the incidents table.

Reads join the users and locations tables so each ticket comes back with the
reporter's name, the assignee's name and the location in one query. The user
joins are LEFT JOINs because a reporter or assignee may have been deleted.
"""

from lib.database import execute, execute_many, fetch_all, fetch_one

# In the order a ticket normally moves through them. "assigned" is set
# automatically when an engineer is put on an open ticket.
STATUSES = ["open", "assigned", "in_progress", "blocked", "resolved", "closed"]
# Statuses that mean the work is finished; resolved_at is set when a ticket
# enters one of these and cleared when it leaves.
FINISHED_STATUSES = ["resolved", "closed"]

# Statuses an engineer may only ask for; a facility admin has to approve.
APPROVAL_STATUSES = ["blocked", "resolved"]

MIN_PRIORITY = 1
MAX_PRIORITY = 5

# The columns every read returns. Kept in one place so every ticket the API
# sends out has the same fields.
SELECT_INCIDENT = """
    SELECT i.id, i.title, i.description, i.status, i.priority,
           i.created_at, i.updated_at, i.resolved_at,
           i.location_id, l.floor, l.room, b.id AS building_id, b.name AS building_name,
           b.room_numbers_include_floor,
           (SELECT MAX(rooms) FROM building_floors f WHERE f.building_id = b.id) AS max_rooms,
           i.reported_by, reporter.name AS reporter_name, reporter.email AS reporter_email,
           i.assigned_to, assignee.name AS assignee_name, assignee.email AS assignee_email,
           i.pending_status, i.pending_requested_by, i.pending_requested_at, i.pending_note,
           requester.name AS pending_requester_name
    FROM incidents i
    LEFT JOIN users requester ON requester.id = i.pending_requested_by
    LEFT JOIN locations l ON l.id = i.location_id
    LEFT JOIN buildings b ON b.id = l.building_id
    LEFT JOIN users reporter ON reporter.id = i.reported_by
    LEFT JOIN users assignee ON assignee.id = i.assigned_to
"""


def create(title, description, priority, location_id, reported_by):
    """Insert a ticket and return it with its joined data."""
    row = execute(
        """
        INSERT INTO incidents (title, description, priority, location_id, reported_by)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (title, description, priority, location_id, reported_by),
    )
    return find_by_id(row["id"])


def find_by_id(incident_id):
    """Return one ticket with its joined data, or None."""
    return fetch_one(SELECT_INCIDENT + " WHERE i.id = %s", (incident_id,))


def find_basic(incident_id, lock=False):
    """
    Return just the plain columns (id, status, priority, location_id,
    reported_by, assigned_to), or None.

    Enough to decide who may see or change the ticket, without the joins.

    lock=True adds FOR UPDATE: the row stays locked until the current
    transaction ends, so two people changing the same ticket at once are
    handled one after the other, and the second sees the first's change.
    """
    sql = """
        SELECT id, status, priority, location_id, reported_by, assigned_to,
               pending_status, pending_requested_by
        FROM incidents
        WHERE id = %s
    """
    if lock:
        sql += " FOR UPDATE"
    return fetch_one(sql, (incident_id,))


# How a list may be ordered (?sort=). Each entry is the ORDER BY for that
# choice; %(dir)s becomes ASC or DESC. Every order ends with the id, so two
# rows can never swap places between pages when they tie on the sort key.
SORTS = {
    "priority": "i.priority %(dir)s, i.created_at DESC, i.id DESC",
    "created": "i.created_at %(dir)s, i.id %(dir)s",
    "updated": "i.updated_at %(dir)s, i.id %(dir)s",
    "id": "i.id %(dir)s",
    "title": "LOWER(i.title) %(dir)s, i.id %(dir)s",
}
DEFAULT_SORT = "priority"  # most urgent first, then newest

# The columns a text search (?q=) looks in. A ticket number ("#12" or "12")
# matches on the id as well.
SEARCH_COLUMNS = ["i.title", "i.description", "reporter.name", "assignee.name", "b.name"]
MAX_SEARCH_WORDS = 5


def _conditions(reported_by, assigned_to, status, priority, pending, unassigned, since, q):
    """
    Build the WHERE clause for search() and count() from the filters given.

    Returns (sql, params): "" when there are no filters, otherwise
    " WHERE a AND b ..." with one %s per value in params.
    """
    conditions = []
    params = []

    if reported_by is not None:
        conditions.append("i.reported_by = %s")
        params.append(reported_by)
    if assigned_to is not None:
        conditions.append("i.assigned_to = %s")
        params.append(assigned_to)
    if status is not None:
        conditions.append("i.status = %s")
        params.append(status)
    if priority is not None:
        conditions.append("i.priority = %s")
        params.append(priority)
    if pending:
        conditions.append("i.pending_status IS NOT NULL")
    if unassigned:
        # Nobody on it, and still worth assigning.
        conditions.append("i.assigned_to IS NULL AND i.status NOT IN ('resolved', 'closed')")
    if since is not None:
        conditions.append("i.created_at >= %s")
        params.append(since)
    if q:
        # Every word must appear somewhere (in any column), in any order,
        # ignoring case. ILIKE on a LEFT JOINed column is NULL for a
        # deleted reporter, which simply does not match.
        for word in q.split()[:MAX_SEARCH_WORDS]:
            matches = [f"{column} ILIKE %s" for column in SEARCH_COLUMNS]
            params.extend([f"%{word}%"] * len(SEARCH_COLUMNS))
            number = word.lstrip("#")
            if number.isdigit():
                matches.append("i.id = %s")
                params.append(int(number))
            conditions.append("(" + " OR ".join(matches) + ")")

    if not conditions:
        return "", params
    return " WHERE " + " AND ".join(conditions), params


def search(reported_by=None, assigned_to=None, status=None, priority=None, pending=False,
           unassigned=False, since=None, q=None, sort=DEFAULT_SORT, descending=False,
           limit=None, offset=0):
    """
    Return one page of the tickets matching every filter that is given.

    sort names an entry of SORTS; descending flips it. limit/offset pick the
    page (limit=None means every row, for callers that need them all).
    """
    where, params = _conditions(reported_by, assigned_to, status, priority, pending, unassigned, since, q)
    order = SORTS[sort] % {"dir": "DESC" if descending else "ASC"}
    sql = SELECT_INCIDENT + where + " ORDER BY " + order
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = params + [limit, offset]
    return fetch_all(sql, params)


def count(reported_by=None, assigned_to=None, status=None, priority=None, pending=False,
          unassigned=False, since=None, q=None):
    """How many tickets match the same filters search() takes."""
    where, params = _conditions(reported_by, assigned_to, status, priority, pending, unassigned, since, q)
    # The joins are only needed when the text search looks at joined columns.
    if q:
        sql = "SELECT COUNT(*) AS n FROM (" + SELECT_INCIDENT + where + ") AS matching"
    else:
        sql = "SELECT COUNT(*) AS n FROM incidents i" + where
    return fetch_one(sql, params)["n"]


def assign(incident_id, assignee_id, status, author_id, note):
    """
    Set (or clear, with None) the assigned engineer, set the status the
    controller worked out ("assigned" / back to "open" / unchanged), and add
    a message saying so. All saved together or not at all.
    """
    execute_many([
        (
            "UPDATE incidents SET assigned_to = %s, status = %s, updated_at = NOW() WHERE id = %s",
            (assignee_id, status, incident_id),
        ),
        (
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, note),
        ),
    ])
    return find_by_id(incident_id)


def update_status(incident_id, status, author_id, note):
    """
    Change the status, keep resolved_at in step with it, and add a message
    saying so. Both are saved together or not at all.
    """
    # Any real status change also drops a pending approval request: the
    # ticket has moved on, so the request no longer applies.
    if status in FINISHED_STATUSES:
        update_sql = """
            UPDATE incidents
            SET status = %s, resolved_at = NOW(), updated_at = NOW(),
                pending_status = NULL, pending_requested_by = NULL,
                pending_requested_at = NULL, pending_note = NULL
            WHERE id = %s
        """
    else:
        update_sql = """
            UPDATE incidents
            SET status = %s, resolved_at = NULL, updated_at = NOW(),
                pending_status = NULL, pending_requested_by = NULL,
                pending_requested_at = NULL, pending_note = NULL
            WHERE id = %s
        """

    execute_many([
        (update_sql, (status, incident_id)),
        (
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, note),
        ),
    ])
    return find_by_id(incident_id)


def update_priority(incident_id, priority, author_id, note):
    """Change the priority and add a message saying so, in one transaction."""
    execute_many([
        (
            "UPDATE incidents SET priority = %s, updated_at = NOW() WHERE id = %s",
            (priority, incident_id),
        ),
        (
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, note),
        ),
    ])
    return find_by_id(incident_id)


def update_location(incident_id, location_id, author_id, note):
    """
    Change (or clear, with None) the location and add a message saying so,
    in one transaction.
    """
    execute_many([
        (
            "UPDATE incidents SET location_id = %s, updated_at = NOW() WHERE id = %s",
            (location_id, incident_id),
        ),
        (
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, note),
        ),
    ])
    return find_by_id(incident_id)


def request_status(incident_id, status, requested_by, note, author_id, message):
    """
    Record that an engineer wants the ticket blocked or resolved, without
    changing the status, and add a message saying so. One transaction.
    """
    execute_many([
        (
            """
            UPDATE incidents
            SET pending_status = %s, pending_requested_by = %s, pending_requested_at = NOW(),
                pending_note = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (status, requested_by, note, incident_id),
        ),
        (
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, message),
        ),
    ])
    return find_by_id(incident_id)


def clear_request(incident_id, author_id, message):
    """Drop the pending request (a rejection or withdrawal) and add a message. One transaction."""
    execute_many([
        (
            """
            UPDATE incidents
            SET pending_status = NULL, pending_requested_by = NULL,
                pending_requested_at = NULL, pending_note = NULL, updated_at = NOW()
            WHERE id = %s
            """,
            (incident_id,),
        ),
        (
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, message),
        ),
    ])
    return find_by_id(incident_id)
