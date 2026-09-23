"""
Building model: the SQL for the buildings table.
"""

from psycopg.errors import ForeignKeyViolation, RestrictViolation

from lib.database import execute, fetch_all, fetch_one

COLUMNS = "id, name, floors, created_at, updated_at"


class BuildingInUse(Exception):
    """Raised when a building cannot be deleted because tickets are located in it."""


def create(name, floors):
    return execute(
        f"INSERT INTO buildings (name, floors) VALUES (%s, %s) RETURNING {COLUMNS}",
        (name, floors),
    )


def find_by_id(building_id):
    return fetch_one(f"SELECT {COLUMNS} FROM buildings WHERE id = %s", (building_id,))


def name_taken(name, ignore_id=None):
    """True if another building already has this name (ignoring case)."""
    row = fetch_one(
        "SELECT id FROM buildings WHERE LOWER(name) = LOWER(%s) AND id <> %s",
        (name, ignore_id or 0),
    )
    return row is not None


def list_all():
    return fetch_all(f"SELECT {COLUMNS} FROM buildings ORDER BY name")


def highest_floor_in_use(building_id):
    """The highest floor any ticket location uses in this building (0 if none)."""
    row = fetch_one(
        "SELECT COALESCE(MAX(floor), 0) AS highest FROM locations WHERE building_id = %s",
        (building_id,),
    )
    return row["highest"]


def update(building_id, name, floors):
    return execute(
        f"""
        UPDATE buildings
        SET name = %s, floors = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING {COLUMNS}
        """,
        (name, floors, building_id),
    )


def delete(building_id):
    """
    Delete a building. Returns rows deleted (0 or 1).

    Raises BuildingInUse if locations (and so tickets) still point at it.
    """
    try:
        return execute("DELETE FROM buildings WHERE id = %s", (building_id,))
    except (ForeignKeyViolation, RestrictViolation):
        raise BuildingInUse(building_id)
