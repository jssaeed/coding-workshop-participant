"""
Building controller: the rules for the list of buildings.

- Anyone signed in can see the list (the ticket form needs it).
- Only a facility admin can add, change or delete buildings.
- A building's floor count cannot drop below a floor that a ticket already
  uses, and a building with tickets in it cannot be deleted.
"""

import logging

from lib import auth, validation
from lib.request import json_body
from lib.responses import HttpError, created, no_content, ok
from models import building as building_model
from views import building_view

logger = logging.getLogger()

MAX_FLOORS = 200


def list_buildings(event):
    """GET /api/buildings - every building, alphabetical."""
    auth.current_user(event)
    return ok(building_view.serialize_many(building_model.list_all()))


def create_building(event):
    """POST /api/buildings - add a building. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)
    name = validation.required_string(body, "name", max_length=100)
    floors = validation.integer_in_range(body, "floors", 1, MAX_FLOORS)

    if building_model.name_taken(name):
        raise HttpError(409, "A building with that name already exists")

    building = building_model.create(name, floors)
    logger.info("Building %s created by %s", building["id"], caller["id"])
    return created(building_view.serialize(building))


def update_building(event, building_id):
    """PUT /api/buildings/{id} - rename or change the floor count. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    existing = building_model.find_by_id(building_id)
    if existing is None:
        raise HttpError(404, "Building not found")

    body = json_body(event)
    # Fields not sent keep their current value.
    name = validation.optional_string(body, "name", max_length=100) or existing["name"]
    floors = validation.integer_in_range(body, "floors", 1, MAX_FLOORS, default=existing["floors"])

    if building_model.name_taken(name, ignore_id=building_id):
        raise HttpError(409, "A building with that name already exists")

    highest = building_model.highest_floor_in_use(building_id)
    if floors < highest:
        raise HttpError(400, f"'floors' cannot be less than {highest}: a ticket is on floor {highest}")

    building = building_model.update(building_id, name, floors)
    logger.info("Building %s updated by %s", building_id, caller["id"])
    return ok(building_view.serialize(building))


def delete_building(event, building_id):
    """DELETE /api/buildings/{id} - remove a building. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    try:
        deleted = building_model.delete(building_id)
    except building_model.BuildingInUse:
        raise HttpError(409, "Building has tickets located in it and cannot be deleted")

    if deleted == 0:
        raise HttpError(404, "Building not found")

    logger.info("Building %s deleted by %s", building_id, caller["id"])
    return no_content()
