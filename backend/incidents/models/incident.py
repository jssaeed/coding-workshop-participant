"""
Incident model: every SQL statement that touches the incidents table.

Reads join users and locations so a ticket list renders without the frontend
making follow-up requests per row.
"""

from lib.database import execute, fetch_all, fetch_one

STATUS_OPEN = "open"
STATUS_IN_PROGRESS = "in_progress"
STATUS_BLOCKED = "blocked"
STATUS_RESOLVED = "resolved"
STATUS_CLOSED = "closed"

# Must match the CHECK constraint in backend/migrations/schema.sql.
STATUSES = (
    STATUS_OPEN,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_RESOLVED,
    STATUS_CLOSED,
)

MIN_PRIORITY = 1
MAX_PRIORITY = 5

# One projection for every read, so each response carries the same fields.
_SELECT = """
    SELECT i.id, i.title, i.description, i.status, i.priority,
           i.created_at, i.updated_at, i.resolved_at,
           i.location_id, l.building, l.floor, l.room,
           i.reported_by, reporter.name AS reporter_name, reporter.email AS reporter_email,
           i.assigned_to, assignee.name AS assignee_name, assignee.email AS assignee_email
      FROM incidents i
      LEFT JOIN locations l ON l.id = i.location_id
      JOIN users reporter ON reporter.id = i.reported_by
      LEFT JOIN users assignee ON assignee.id = i.assigned_to
"""

def create(title, description, priority, location_id, reported_by):
    """Insert an incident and return it with its joined rows."""
    row = execute(
        """
        INSERT INTO incidents (title, description, priority, location_id, reported_by)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (title, description, priority, location_id, reported_by),
        returning=True,
    )
    return find_by_id(row["id"])

def find_by_id(incident_id):
    """Return one incident, or None."""
    return fetch_one(f"{_SELECT} WHERE i.id = %s", (incident_id,))

def find_access_row(incident_id):
    """
    Return just the columns needed to decide who may see an incident.

    Kept separate from find_by_id so permission checks do not pay for the
    joins.
    """
    return fetch_one(
        "SELECT id, reported_by, assigned_to, status FROM incidents WHERE id = %s",
        (incident_id,),
    )

def search(reported_by=None, assigned_to=None, status=None, priority=None):
    """
    List incidents, filtered by any combination of the arguments.

    Filters are appended as parameters rather than formatted into the SQL, so
    query strings cannot alter the statement.
    """
    clauses = []
    params = []

    if reported_by is not None:
        clauses.append("i.reported_by = %s")
        params.append(reported_by)
    if assigned_to is not None:
        clauses.append("i.assigned_to = %s")
        params.append(assigned_to)
    if status is not None:
        clauses.append("i.status = %s")
        params.append(status)
    if priority is not None:
        clauses.append("i.priority = %s")
        params.append(priority)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    # Most urgent first, then newest, which is the order the ticket list shows.
    order = " ORDER BY i.priority ASC, i.created_at DESC"
    return fetch_all(f"{_SELECT}{where}{order}", tuple(params))

def list_unassigned():
    """Return incidents waiting for an engineer, for the admin queue."""
    return fetch_all(
        f"{_SELECT} WHERE i.assigned_to IS NULL AND i.status NOT IN ('resolved', 'closed')"
        " ORDER BY i.priority ASC, i.created_at DESC"
    )

def assign(incident_id, assignee_id):
    """Set or clear the assigned engineer. Returns the row, or None."""
    row = execute(
        "UPDATE incidents SET assigned_to = %s WHERE id = %s RETURNING id",
        (assignee_id, incident_id),
        returning=True,
    )
    return find_by_id(row["id"]) if row else None

def update_status_with_message(incident_id, status, author_id, message):
    """
    Change an incident's status and post the note recording it.

    Both statements share one transaction: a status change must never be left
    without its message, and a message must never describe a change that did
    not commit.

    Returns:
        dict | None: the updated incident, or None when it does not exist
    """
    from lib.database import transaction

    with transaction() as cur:
        cur.execute(
            "UPDATE incidents SET status = %s WHERE id = %s RETURNING id",
            (status, incident_id),
        )
        if cur.fetchone() is None:
            return None

        cur.execute(
            "INSERT INTO messages (incident_id, user_id, message) VALUES (%s, %s, %s)",
            (incident_id, author_id, message),
        )

    return find_by_id(incident_id)
