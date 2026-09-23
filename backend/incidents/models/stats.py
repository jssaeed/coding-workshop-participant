"""
Stats model: counting tickets for the Statistics page.

Every function takes "since": only tickets created at or after that moment
are counted, so the page can show "the last 30 days".
"""

from lib.database import fetch_all


def count_by_status(since, reported_by=None, assigned_to=None):
    """
    How many tickets are in each status. Optionally only tickets reported
    by, or assigned to, one user. Returns rows of (status, count).
    """
    conditions = ["i.created_at >= %(since)s"]
    params = {"since": since}
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


def count_by_building(since):
    """Tickets per building. Tickets with no location come back with a NULL id."""
    return fetch_all(
        """
        SELECT b.id AS building_id, b.name AS building_name, COUNT(*) AS count
        FROM incidents i
        LEFT JOIN locations l ON l.id = i.location_id
        LEFT JOIN buildings b ON b.id = l.building_id
        WHERE i.created_at >= %s
        GROUP BY b.id, b.name
        ORDER BY count DESC, b.name
        """,
        (since,),
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
