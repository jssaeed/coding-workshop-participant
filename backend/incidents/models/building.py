"""
A read-only look at the buildings table, for checking a ticket's location.

Buildings are managed by the buildings service.
"""

from lib.database import fetch_one


def find_by_id(building_id):
    return fetch_one(
        "SELECT id, name, floors FROM buildings WHERE id = %s",
        (building_id,),
    )
