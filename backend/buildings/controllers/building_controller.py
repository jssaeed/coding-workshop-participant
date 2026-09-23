"""
Building controller: the rules for a branch's list of buildings.

- Anyone signed in can see their own branch's buildings (the ticket form
  needs them).
- Only a facility admin can add, change or delete buildings, and only at
  their own branch.
- Floors are 1..floors above ground and B1..Bm below. Each floor can say
  how many rooms it has: one number for every floor, or a per-floor list.
- Rooms can be numbered by floor ("501" = floor 5, room 1); that is only
  how they are shown, the database keeps the plain room index.
- A building cannot lose a floor, or rooms on a floor, that a ticket
  already uses; a building with tickets in it cannot be deleted.
"""

import logging

from lib import auth, validation
from lib.database import transaction
from lib.labels import floor_label, room_digits, room_label
from lib.request import json_body
from lib.responses import HttpError, created, no_content, ok
from models import building as building_model
from views import building_view

logger = logging.getLogger()

MAX_FLOORS = 200
MAX_BASEMENT_FLOORS = 20
MAX_ROOMS = 500


def optional_bool(body, field, default):
    """A true/false field, or default when it is left out."""
    value = body.get(field)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise HttpError(400, f"'{field}' must be true or false")
    return value


def floor_numbers(floors, basement_floors):
    """Every floor of a building: [floors..1, -1..-basement_floors]."""
    return list(range(floors, 0, -1)) + list(range(-1, -basement_floors - 1, -1))


def rooms_from_body(body, all_floors, existing):
    """
    Work out how many rooms each floor has, as {floor: rooms}.

    The request may send "roomsPerFloor": 10 (the same for every floor), or
    "rooms": [{"floor": 3, "rooms": 12}, ...] for some or all floors, or
    both, or neither. Priority for each floor: its "rooms" entry, then
    roomsPerFloor, then what it had before (existing), then 0.
    """
    per_floor = None
    if body.get("roomsPerFloor") is not None:
        per_floor = validation.integer_in_range(body, "roomsPerFloor", 0, MAX_ROOMS)

    listed = {}
    if body.get("rooms") is not None:
        if not isinstance(body["rooms"], list):
            raise HttpError(400, "'rooms' must be a list of {floor, rooms}")
        for entry in body["rooms"]:
            if not isinstance(entry, dict):
                raise HttpError(400, "'rooms' must be a list of {floor, rooms}")
            floor = entry.get("floor")
            if not isinstance(floor, int) or isinstance(floor, bool) or floor not in all_floors:
                raise HttpError(400, "'rooms' names a floor this building does not have")
            listed[floor] = validation.integer_in_range(entry, "rooms", 0, MAX_ROOMS)

    result = {}
    for floor in all_floors:
        if floor in listed:
            result[floor] = listed[floor]
        elif per_floor is not None:
            result[floor] = per_floor
        else:
            result[floor] = existing.get(floor, 0)
    return result


def get_building_in_my_branch(caller, building_id, lock=False):
    """Load a building, or 404. 403 if it belongs to another branch."""
    building = building_model.find_by_id(building_id, lock=lock)
    if building is None:
        raise HttpError(404, "Building not found")
    if building["branch_id"] != caller["branch_id"]:
        raise HttpError(403, "That building belongs to another branch")
    return building


def list_buildings(event):
    """GET /api/buildings - the caller's branch's buildings, alphabetical."""
    caller = auth.current_user(event)
    buildings = building_model.list_all(caller["branch_id"])
    floors = building_model.list_floors_for([b["id"] for b in buildings])
    return ok(building_view.serialize_many(buildings, floors))


def create_building(event):
    """POST /api/buildings - add a building at the caller's branch. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)
    name = validation.required_string(body, "name", max_length=100)
    floors = validation.integer_in_range(body, "floors", 1, MAX_FLOORS)
    basement_floors = validation.integer_in_range(body, "basementFloors", 0, MAX_BASEMENT_FLOORS, default=0)
    include_floor = optional_bool(body, "roomNumbersIncludeFloor", default=False)
    rooms_by_floor = rooms_from_body(body, floor_numbers(floors, basement_floors), existing={})

    if building_model.name_taken(caller["branch_id"], name):
        raise HttpError(409, "A building with that name already exists at your branch")

    with transaction():
        building = building_model.create(caller["branch_id"], name, floors, basement_floors, include_floor)
        building_model.replace_floors(building["id"], rooms_by_floor)

    logger.info("Building %s created by %s", building["id"], caller["id"])
    return created(building_view.serialize(building, building_model.list_floors(building["id"])))


def update_building(event, building_id):
    """PUT /api/buildings/{id} - rename, change floors or rooms. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)

    # Lock the building while we check what is in use and save, so a ticket
    # cannot be filed on floor 5 while we are cutting the building down to 3
    # (ticket creation takes a share lock on the same row).
    with transaction():
        existing = get_building_in_my_branch(caller, building_id, lock=True)

        # Fields not sent keep their current value.
        name = validation.optional_string(body, "name", max_length=100) or existing["name"]
        floors = validation.integer_in_range(body, "floors", 1, MAX_FLOORS, default=existing["floors"])
        basement_floors = validation.integer_in_range(
            body, "basementFloors", 0, MAX_BASEMENT_FLOORS, default=existing["basement_floors"]
        )
        include_floor = optional_bool(body, "roomNumbersIncludeFloor", default=existing["room_numbers_include_floor"])
        current_rooms = {f["floor"]: f["rooms"] for f in building_model.list_floors(building_id)}
        rooms_by_floor = rooms_from_body(body, floor_numbers(floors, basement_floors), current_rooms)

        if building_model.name_taken(caller["branch_id"], name, ignore_id=building_id):
            raise HttpError(409, "A building with that name already exists at your branch")

        # Switching to "rooms start with the floor number": tickets whose room
        # was typed that way before (502 on floor 5) become plain indexes (2),
        # so the room counts below compare like with like.
        digits = room_digits(max(rooms_by_floor.values(), default=0))
        if include_floor and not existing["room_numbers_include_floor"]:
            converted = building_model.convert_numbered_rooms(building_id, digits)
            if converted:
                logger.info("Converted %s numbered rooms in building %s", converted, building_id)

        # Nothing a ticket points at may disappear.
        in_use = building_model.floors_in_use(building_id)
        if floors < in_use["highest"]:
            raise HttpError(400, f"'floors' cannot be less than {in_use['highest']}: a ticket is on floor {in_use['highest']}")
        if basement_floors < -in_use["lowest"]:
            raise HttpError(400, f"'basementFloors' cannot be less than {-in_use['lowest']}: a ticket is on floor {floor_label(in_use['lowest'])}")
        max_rooms = max(rooms_by_floor.values(), default=0)
        for floor, highest_room in building_model.rooms_in_use(building_id).items():
            if 0 < rooms_by_floor.get(floor, 0) < highest_room:
                written = room_label(floor, highest_room, include_floor, max_rooms)
                raise HttpError(400, f"Floor {floor_label(floor)} cannot have fewer than {highest_room} rooms: a ticket is in room {written}")

        building = building_model.update(building_id, name, floors, basement_floors, include_floor)
        building_model.replace_floors(building_id, rooms_by_floor)

    logger.info("Building %s updated by %s", building_id, caller["id"])
    return ok(building_view.serialize(building, building_model.list_floors(building_id)))


def delete_building(event, building_id):
    """DELETE /api/buildings/{id} - remove a building. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])
    get_building_in_my_branch(caller, building_id)

    try:
        building_model.delete(building_id)
    except building_model.BuildingInUse:
        raise HttpError(409, "Building has tickets located in it and cannot be deleted")

    logger.info("Building %s deleted by %s", building_id, caller["id"])
    return no_content()
