"""
Location model: the SQL for the locations table.

Locations are shared between tickets: two tickets in the same room point at
the same location row.
"""

from lib.database import execute, fetch_all, fetch_one


def find_by_id(location_id):
    return fetch_one(
        "SELECT id, building, floor, room FROM locations WHERE id = %s",
        (location_id,),
    )


def find_or_create(building, floor, room):
    """Return the location for this place, adding it if it is new."""
    existing = fetch_one(
        """
        SELECT id, building, floor, room
        FROM locations
        WHERE building = %s AND floor = %s AND room = %s
        """,
        (building, floor, room),
    )
    if existing is not None:
        return existing

    return execute(
        """
        INSERT INTO locations (building, floor, room)
        VALUES (%s, %s, %s)
        RETURNING id, building, floor, room
        """,
        (building, floor, room),
    )


def list_all():
    return fetch_all(
        "SELECT id, building, floor, room FROM locations ORDER BY building, floor, room"
    )
