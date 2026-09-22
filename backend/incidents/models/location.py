"""
Location model: the buildings, floors and rooms incidents are reported in.

Locations are reused rather than duplicated, so filtering by building stays
reliable.
"""

from lib.database import execute, fetch_all, fetch_one

def find_or_create(building, floor, room=""):
    """
    Return the matching location, creating it only if it is new.

    ON CONFLICT makes this safe when two tickets are filed for the same place
    at once: the loser of the race reads the winner's row instead of failing.
    """
    existing = fetch_one(
        "SELECT id, building, floor, room FROM locations"
        " WHERE building = %s AND floor = %s AND room = %s",
        (building, floor, room),
    )
    if existing:
        return existing

    return execute(
        """
        INSERT INTO locations (building, floor, room)
        VALUES (%s, %s, %s)
        ON CONFLICT ON CONSTRAINT locations_unique_place DO UPDATE
            SET building = EXCLUDED.building
        RETURNING id, building, floor, room
        """,
        (building, floor, room),
        returning=True,
    )

def find_by_id(location_id):
    """Return one location, or None."""
    return fetch_one(
        "SELECT id, building, floor, room FROM locations WHERE id = %s",
        (location_id,),
    )

def list_all():
    """Return every known location, for the report-a-ticket dropdown."""
    return fetch_all(
        "SELECT id, building, floor, room FROM locations ORDER BY building, floor, room"
    )
