"""
Stats model: counting tickets for the Statistics page.

Every function takes "since": only tickets created at or after that moment
are counted, so the page can show "the last 30 days". The admin views also
take "branch_id": a facility admin only sees the tickets at their branch.
"""

from lib.database import fetch_all, fetch_one


def count_by_status(since, reported_by=None, assigned_to=None, branch_id=None):
    """
    How many tickets are in each status. Optionally only tickets reported
    by, or assigned to, one user, or filed at one branch. Returns rows of
    (status, count).
    """
    conditions = ["i.created_at >= %(since)s"]
    params = {"since": since}
    if branch_id is not None:
        conditions.append("i.branch_id = %(branch_id)s")
        params["branch_id"] = branch_id
    if reported_by is not None:
        conditions.append("i.reported_by = %(reported_by)s")
        params["reported_by"] = reported_by
    if assigned_to is not None:
        conditions.append("i.assigned_to = %(assigned_to)s")
        params["assigned_to"] = assigned_to

    return fetch_all(
        f"""
        SELECT i.status, COUNT(*) AS count
        FROM incidents i
        WHERE {' AND '.join(conditions)}
        GROUP BY i.status
        """,
        params,
    )


def count_by_priority(since, branch_id):
    """How many of one branch's tickets are at each priority. Returns rows of (priority, count)."""
    return fetch_all(
        """
        SELECT i.priority, COUNT(*) AS count
        FROM incidents i
        WHERE i.created_at >= %s AND i.branch_id = %s
        GROUP BY i.priority
        """,
        (since, branch_id),
    )


def count_by_category(since, branch_id):
    """How many of one branch's tickets are in each category. Returns rows of (category, count)."""
    return fetch_all(
        """
        SELECT i.category, COUNT(*) AS count
        FROM incidents i
        WHERE i.created_at >= %s AND i.branch_id = %s
        GROUP BY i.category
        """,
        (since, branch_id),
    )


def count_by_building(since, branch_id):
    """Tickets per building at one branch. Tickets with no location come back with a NULL id."""
    return fetch_all(
        """
        SELECT b.id AS building_id, b.name AS building_name, COUNT(*) AS count
        FROM incidents i
        LEFT JOIN locations l ON l.id = i.location_id
        LEFT JOIN buildings b ON b.id = l.building_id
        WHERE i.created_at >= %s AND i.branch_id = %s
        GROUP BY b.id, b.name
        ORDER BY count DESC, b.name
        """,
        (since, branch_id),
    )


def count_by_floor(building_id, since):
    """Tickets per floor in one building."""
    return fetch_all(
        """
        SELECT l.floor, COUNT(*) AS count
        FROM incidents i
        JOIN locations l ON l.id = i.location_id
        WHERE l.building_id = %s AND i.created_at >= %s
        GROUP BY l.floor
        ORDER BY (l.floor < 0), -l.floor
        """,
        (building_id, since),
    )


def count_by_room(building_id, floor, since):
    """Tickets per room on one floor. Tickets with no room come back with a NULL room."""
    return fetch_all(
        """
        SELECT l.room, COUNT(*) AS count
        FROM incidents i
        JOIN locations l ON l.id = i.location_id
        WHERE l.building_id = %s AND l.floor = %s AND i.created_at >= %s
        GROUP BY l.room
        ORDER BY l.room NULLS LAST
        """,
        (building_id, floor, since),
    )


def resolution_time(since, branch_id):
    """
    How long tickets at one branch took to resolve, over tickets created
    since "since" that have a resolved_at. Returns {"average_seconds":
    float or None, "resolved_count": int}.
    """
    return fetch_one(
        """
        SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))) AS average_seconds,
               COUNT(*) AS resolved_count
        FROM incidents
        WHERE created_at >= %s AND branch_id = %s AND resolved_at IS NOT NULL
        """,
        (since, branch_id),
    )


def engineer_workload(since, branch_id):
    """
    One row per engineer or admin who has tickets at one branch created
    since "since": how many are assigned to them now, how many of those are
    finished, and their average time from ticket creation to resolution.
    """
    return fetch_all(
        """
        SELECT u.id, u.name, u.role,
               COUNT(*) AS assigned_count,
               COUNT(i.resolved_at) AS resolved_count,
               AVG(EXTRACT(EPOCH FROM (i.resolved_at - i.created_at))) AS average_seconds
        FROM incidents i
        JOIN users u ON u.id = i.assigned_to
        WHERE i.created_at >= %s AND i.branch_id = %s
        GROUP BY u.id, u.name, u.role
        ORDER BY assigned_count DESC, u.name
        """,
        (since, branch_id),
    )
