"""
Location model: the SQL for the locations table.

A location is one exact place (building, floor, optional room). Locations
are shared: every ticket reported in the same place points at the same row.
"""

from lib.database import execute, fetch_one

COLUMNS = "id, building_id, floor, room"


def find_or_create(building_id, floor, room):
    """Return the location for this place, adding it if it is new."""
    existing = fetch_one(
        f"""
        SELECT {COLUMNS}
        FROM locations
        WHERE building_id = %s AND floor = %s AND room IS NOT DISTINCT FROM %s
        """,
        (building_id, floor, room),
    )
    if existing is not None:
        return existing

    return execute(
        f"""
        INSERT INTO locations (building_id, floor, room)
        VALUES (%s, %s, %s)
        RETURNING {COLUMNS}
        """,
        (building_id, floor, room),
    )
