"""
Location model: the SQL for the locations table.

A location is one exact place (building, floor, optional room). Locations
are shared: every ticket reported in the same place points at the same row.
"""

from lib.database import execute, fetch_one

COLUMNS = "id, building_id, floor, room"


def find_or_create(building_id, floor, room):
    """
    Return the location for this place, adding it if it is new.

    The INSERT comes first, with ON CONFLICT DO NOTHING: if two tickets for
    a brand-new place arrive at the same moment, one insert wins and the
    other quietly does nothing, instead of failing on the UNIQUE rule. The
    SELECT after it then finds the row either way.
    """
    execute(
        """
        INSERT INTO locations (building_id, floor, room)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (building_id, floor, room),
    )
    return fetch_one(
        f"""
        SELECT {COLUMNS}
        FROM locations
        WHERE building_id = %s AND floor = %s AND room IS NOT DISTINCT FROM %s
        """,
        (building_id, floor, room),
    )
