"""
Building model: the SQL for the buildings and building_floors tables.

Floors are numbered 1..floors above ground and -1..-basement_floors below
ground (-1 is shown as "B1"). building_floors has one row per floor with
how many rooms it has (0 = not specified).
"""

from psycopg.errors import ForeignKeyViolation, RestrictViolation

from lib.database import execute, execute_many, fetch_all, fetch_one

COLUMNS = "id, branch_id, name, floors, basement_floors, room_numbers_include_floor, created_at, updated_at"

# Floors in display order: top floor first down to 1, then B1, B2, ...
# "(floor < 0)" is false (sorts first) for above-ground floors; "-floor"
# then puts 3 before 2 before 1, and B1 (-1) before B2 (-2).
FLOOR_ORDER = "ORDER BY (floor < 0), -floor"


class BuildingInUse(Exception):
    """Raised when a building cannot be deleted because tickets are located in it."""


def create(branch_id, name, floors, basement_floors, room_numbers_include_floor):
    return execute(
        f"""
        INSERT INTO buildings (branch_id, name, floors, basement_floors, room_numbers_include_floor)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING {COLUMNS}
        """,
        (branch_id, name, floors, basement_floors, room_numbers_include_floor),
    )


def find_by_id(building_id, lock=False):
    """
    One building, or None. lock=True adds FOR UPDATE, so nobody else can
    change the row (or file a ticket against it, which takes a share lock)
    until the current transaction ends.
    """
    sql = f"SELECT {COLUMNS} FROM buildings WHERE id = %s"
    if lock:
        sql += " FOR UPDATE"
    return fetch_one(sql, (building_id,))


def name_taken(branch_id, name, ignore_id=None):
    """True if another building at this branch already has this name (ignoring case)."""
    row = fetch_one(
        "SELECT id FROM buildings WHERE branch_id = %s AND LOWER(name) = LOWER(%s) AND id <> %s",
        (branch_id, name, ignore_id or 0),
    )
    return row is not None


def list_all(branch_id):
    """Every building at one branch, alphabetical."""
    return fetch_all(f"SELECT {COLUMNS} FROM buildings WHERE branch_id = %s ORDER BY name", (branch_id,))


def list_floors(building_id):
    """[{floor, rooms}, ...] for one building, top floor first."""
    return fetch_all(
        f"SELECT floor, rooms FROM building_floors WHERE building_id = %s {FLOOR_ORDER}",
        (building_id,),
    )


def list_floors_for(building_ids):
    """The floors of several buildings at once: {building_id: [{floor, rooms}, ...]}."""
    floors = {building_id: [] for building_id in building_ids}
    if not building_ids:
        return floors
    rows = fetch_all(
        f"SELECT building_id, floor, rooms FROM building_floors WHERE building_id = ANY(%s) {FLOOR_ORDER}",
        (list(building_ids),),
    )
    for row in rows:
        floors[row["building_id"]].append({"floor": row["floor"], "rooms": row["rooms"]})
    return floors


def replace_floors(building_id, rooms_by_floor):
    """
    Make building_floors match rooms_by_floor ({floor: rooms}) exactly:
    floors not in it are removed, the rest are added or updated.
    """
    statements = [
        (
            "DELETE FROM building_floors WHERE building_id = %s AND NOT (floor = ANY(%s))",
            (building_id, list(rooms_by_floor)),
        )
    ]
    for floor, rooms in rooms_by_floor.items():
        statements.append((
            """
            INSERT INTO building_floors (building_id, floor, rooms)
            VALUES (%s, %s, %s)
            ON CONFLICT (building_id, floor) DO UPDATE SET rooms = EXCLUDED.rooms
            """,
            (building_id, floor, rooms),
        ))
    execute_many(statements)


def floors_in_use(building_id):
    """
    The highest above-ground floor and the deepest basement floor that any
    ticket location uses in this building. 0 for either means none.
    """
    row = fetch_one(
        """
        SELECT COALESCE(MAX(floor) FILTER (WHERE floor > 0), 0) AS highest,
               COALESCE(MIN(floor) FILTER (WHERE floor < 0), 0) AS lowest
        FROM locations
        WHERE building_id = %s
        """,
        (building_id,),
    )
    return row


def convert_numbered_rooms(building_id, digits):
    """
    Turn rooms that were typed in the "floor in front" style into plain
    indexes, so a building can switch to numbering rooms by floor.

    With digits=2, room 502 on floor 5 becomes room 2 (502 - 5*100); with
    digits=3, room 5002 becomes 2. Only rooms whose leading digits equal
    their own floor are touched, and only above ground (a basement room
    cannot carry a "B" in a number). Returns how many locations changed.

    If the converted place already exists as a row, tickets are pointed at
    that row and the old one is dropped (the place is unique per building).
    """
    base = 10 ** digits
    rows = fetch_all(
        """
        SELECT id, floor, room
        FROM locations
        WHERE building_id = %s AND floor > 0 AND room >= %s AND room / %s = floor AND room %% %s >= 1
        """,
        (building_id, base, base, base),
    )
    for row in rows:
        new_room = row["room"] % base
        existing = fetch_one(
            "SELECT id FROM locations WHERE building_id = %s AND floor = %s AND room = %s",
            (building_id, row["floor"], new_room),
        )
        if existing is None:
            execute("UPDATE locations SET room = %s WHERE id = %s", (new_room, row["id"]))
        else:
            execute("UPDATE incidents SET location_id = %s WHERE location_id = %s", (existing["id"], row["id"]))
            execute("DELETE FROM locations WHERE id = %s", (row["id"],))
    return len(rows)


def rooms_in_use(building_id):
    """{floor: highest room number a ticket uses on that floor}."""
    rows = fetch_all(
        """
        SELECT floor, MAX(room) AS highest_room
        FROM locations
        WHERE building_id = %s AND room IS NOT NULL
        GROUP BY floor
        """,
        (building_id,),
    )
    return {row["floor"]: row["highest_room"] for row in rows}


def update(building_id, name, floors, basement_floors, room_numbers_include_floor):
    return execute(
        f"""
        UPDATE buildings
        SET name = %s, floors = %s, basement_floors = %s, room_numbers_include_floor = %s,
            updated_at = NOW()
        WHERE id = %s
        RETURNING {COLUMNS}
        """,
        (name, floors, basement_floors, room_numbers_include_floor, building_id),
    )


def delete(building_id):
    """
    Delete a building (its floor rows go with it). Returns rows deleted.

    Raises BuildingInUse if locations (and so tickets) still point at it.
    """
    try:
        return execute("DELETE FROM buildings WHERE id = %s", (building_id,))
    except (ForeignKeyViolation, RestrictViolation):
        raise BuildingInUse(building_id)
