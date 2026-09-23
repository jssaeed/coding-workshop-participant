"""
Incident model: the SQL for the incidents table.

Reads join the users and locations tables so each ticket comes back with the
reporter's name, the assignee's name and the location in one query.
"""

from lib.database import execute, execute_many, fetch_all, fetch_one

STATUSES = ["open", "in_progress", "blocked", "resolved", "closed"]
# Statuses that mean the work is finished; resolved_at is set when a ticket
# enters one of these and cleared when it leaves.
FINISHED_STATUSES = ["resolved", "closed"]

MIN_PRIORITY = 1
MAX_PRIORITY = 5

# The columns every read returns. Kept in one place so every ticket the API
# sends out has the same fields.
SELECT_INCIDENT = """
    SELECT i.id, i.title, i.description, i.status, i.priority,
           i.created_at, i.updated_at, i.resolved_at,
           i.location_id, l.floor, l.room, b.id AS building_id, b.name AS building_name,
           i.reported_by, reporter.name AS reporter_name, reporter.email AS reporter_email,
           i.assigned_to, assignee.name AS assignee_name, assignee.email AS assignee_email
    FROM incidents i
    LEFT JOIN locations l ON l.id = i.location_id
    LEFT JOIN buildings b ON b.id = l.building_id
    JOIN users reporter ON reporter.id = i.reported_by
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


def find_basic(incident_id):
    """
    Return just id, status, reported_by and assigned_to, or None.

    Enough to decide who may see or change the ticket, without the joins.
    """
    return fetch_one(
        "SELECT id, status, reported_by, assigned_to FROM incidents WHERE id = %s",
        (incident_id,),
    )


def search(reported_by=None, assigned_to=None, status=None, priority=None):
    """
    Return tickets matching every filter that is given.

    Each filter adds one "AND column = %s" to the WHERE clause, with its value
    added to params in the same order.
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

    sql = SELECT_INCIDENT
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    # Most urgent first, then newest.
    sql += " ORDER BY i.priority ASC, i.created_at DESC"

    return fetch_all(sql, params)


def list_unassigned():
    """Tickets that still need an engineer and are not finished."""
    return fetch_all(
        SELECT_INCIDENT
        + " WHERE i.assigned_to IS NULL AND i.status NOT IN ('resolved', 'closed')"
        + " ORDER BY i.priority ASC, i.created_at DESC"
    )


def assign(incident_id, assignee_id, author_id, note):
    """
    Set (or clear, with None) the assigned engineer, and add a message
    saying so. Both are saved together or not at all.
    """
    execute_many([
        (
            "UPDATE incidents SET assigned_to = %s, updated_at = NOW() WHERE id = %s",
            (assignee_id, incident_id),
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
    if status in FINISHED_STATUSES:
        update_sql = """
            UPDATE incidents
            SET status = %s, resolved_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """
    else:
        update_sql = """
            UPDATE incidents
            SET status = %s, resolved_at = NULL, updated_at = NOW()
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
