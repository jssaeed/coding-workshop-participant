"""
A read-only look at the buildings tables, for checking a ticket's location.

Buildings are managed by the buildings service.
"""

from lib.database import fetch_one


def find_by_id(building_id, lock=False):
    """
    One building, or None.

    lock=True adds FOR SHARE: until the current transaction ends, nobody can
    change this building (for example remove a floor) while we are checking
    a ticket's location against it.
    """
    sql = """
        SELECT id, branch_id, name, floors, basement_floors, room_numbers_include_floor,
               (SELECT MAX(rooms) FROM building_floors f WHERE f.building_id = buildings.id) AS max_rooms
        FROM buildings
        WHERE id = %s
    """
    if lock:
        sql += " FOR SHARE"
    return fetch_one(sql, (building_id,))


def rooms_on_floor(building_id, floor):
    """How many rooms a floor has (0 = not specified), or None for an unknown floor."""
    row = fetch_one(
        "SELECT rooms FROM building_floors WHERE building_id = %s AND floor = %s",
        (building_id, floor),
    )
    return None if row is None else row["rooms"]
