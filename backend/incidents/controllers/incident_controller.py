"""
Incident controller: the rules for tickets.

- Anyone signed in can file a ticket and see the tickets they filed.
- Engineers and admins can see the tickets assigned to them.
- Only admins can see all tickets, assign them and change their location.
- The assigned engineer (or an admin) can change a ticket's status and priority.
- Assigning an open ticket moves it to "assigned"; unassigning an "assigned"
  ticket moves it back to "open". "open" always means nobody is on it.

Status, priority, assignment and location changes also add a message to the
ticket, so the thread shows the history and the change appears in other
users' inboxes.
"""

import logging

from lib import auth, validation
from lib.database import transaction
from lib.labels import floor_label, room_label
from lib.request import json_body, query_params
from lib.responses import HttpError, created, ok
from models import building as building_model
from models import incident as incident_model
from models import location as location_model
from models import user as user_model
from views import incident_view

logger = logging.getLogger()


def status_label(status):
    """'in_progress' -> 'in progress', for messages people read."""
    return status.replace("_", " ")


def can_see(caller, incident):
    """The reporter, the assignee and admins may see a ticket."""
    return (
        auth.is_admin(caller)
        or incident["reported_by"] == caller["id"]
        or incident["assigned_to"] == caller["id"]
    )


def get_visible_incident(caller, incident_id):
    """
    Load the basic ticket row, or raise 404.

    People who may not see the ticket also get 404 (not 403), so they cannot
    find out which ticket ids exist.
    """
    incident = incident_model.find_basic(incident_id)
    if incident is None or not can_see(caller, incident):
        raise HttpError(404, "Incident not found")
    return incident


def location_from_body(body, caller):
    """
    Work out the location from a request body.

    Returns (location_id, label). The label is text like "HQ, floor 3, room 12"
    for messages people read. With no location both are (None, "no location").

    The request sends "location": {"buildingId": 2, "floor": 3, "room": 12}
    (room optional), or leaves location out / sends null for no location.
    The building must be at the caller's branch. Floors run 1..floors above
    ground and -1..-basementFloors below (-1 is "B1"); there is no floor 0.
    If the floor has a room count, the room must be within it.
    """
    location = body.get("location")
    if location is None:
        return None, "no location"
    if not isinstance(location, dict):
        raise HttpError(400, "'location' must be an object")

    building_id = validation.required_id(location, "buildingId")
    # Locked (FOR SHARE) so the floors cannot be changed under us between
    # this check and the save. Callers run this in a transaction.
    building = building_model.find_by_id(building_id, lock=True)
    if building is None:
        raise HttpError(400, "'buildingId' does not match a known building")
    if building["branch_id"] != caller["branch_id"]:
        raise HttpError(400, "'buildingId' is not a building at your branch")

    floor = location.get("floor")
    lowest = -building["basement_floors"]
    if not isinstance(floor, int) or isinstance(floor, bool) or floor == 0 or not lowest <= floor <= building["floors"]:
        raise HttpError(400, f"'floor' must be between {floor_label(lowest) if lowest else 1} and {building['floors']} (there is no floor 0)")

    room = validation.optional_id(location, "room")  # a positive whole number, or absent
    rooms = building_model.rooms_on_floor(building_id, floor) or 0
    if room is not None and rooms and room > rooms:
        raise HttpError(400, f"'room' must be between 1 and {rooms} on floor {floor_label(floor)}")

    label = f"{building['name']}, floor {floor_label(floor)}"
    if room is not None:
        label += f", room {room_label(floor, room, building['room_numbers_include_floor'], building['max_rooms'])}"

    return location_model.find_or_create(building_id, floor, room)["id"], label


def get_incident_for_staff_change(caller, incident_id):
    """
    Load and lock the ticket row for a status or priority change, or raise.

    The caller must be staff. An engineer may only change tickets assigned to
    them; admins may change any. Call this inside "with transaction():" so
    the lock lasts until the change is saved.
    """
    auth.require_role(caller, auth.STAFF_ROLES)

    incident = incident_model.find_basic(incident_id, lock=True)
    if incident is None:
        raise HttpError(404, "Incident not found")

    if not auth.is_admin(caller) and incident["assigned_to"] != caller["id"]:
        raise HttpError(403, "Access denied")

    return incident


def create_incident(event):
    """POST /api/incidents - file a ticket. The caller becomes the reporter."""
    caller = auth.current_user(event)
    body = json_body(event)

    title = validation.required_string(body, "title", max_length=255)
    description = validation.optional_string(body, "description", max_length=5000)
    priority = validation.integer_in_range(
        body, "priority", incident_model.MIN_PRIORITY, incident_model.MAX_PRIORITY, default=3
    )
    # The location row (if new) and the ticket are saved together.
    with transaction():
        location_id, _ = location_from_body(body, caller)
        incident = incident_model.create(title, description, priority, location_id, caller["id"])

    logger.info("Incident %s filed by user %s", incident["id"], caller["id"])
    return created(incident_view.serialize(incident))


def list_incidents(event):
    """
    GET /api/incidents - list tickets.

    ?scope=mine        tickets I filed (the default)
    ?scope=assigned    tickets assigned to me (engineer or admin)
    ?scope=unassigned  tickets with no engineer yet (admin)
    ?scope=all         every ticket (admin)
    ?status=open and ?priority=2 narrow the list further.
    """
    caller = auth.current_user(event)
    params = query_params(event)

    scope = params.get("scope", "mine")
    if scope not in ["mine", "assigned", "unassigned", "all"]:
        raise HttpError(400, "'scope' must be one of: mine, assigned, unassigned, all")

    status = params.get("status")
    if status is not None and status not in incident_model.STATUSES:
        raise HttpError(400, f"'status' must be one of: {', '.join(incident_model.STATUSES)}")

    priority = params.get("priority")
    if priority is not None:
        if not priority.isdigit() or not 1 <= int(priority) <= 5:
            raise HttpError(400, "'priority' must be between 1 and 5")
        priority = int(priority)

    if scope == "mine":
        incidents = incident_model.search(reported_by=caller["id"], status=status, priority=priority)
    elif scope == "assigned":
        auth.require_role(caller, auth.STAFF_ROLES)
        incidents = incident_model.search(assigned_to=caller["id"], status=status, priority=priority)
    elif scope == "unassigned":
        auth.require_role(caller, [auth.ROLE_ADMIN])
        incidents = incident_model.list_unassigned()
    else:  # "all"
        auth.require_role(caller, [auth.ROLE_ADMIN])
        incidents = incident_model.search(status=status, priority=priority)

    return ok(incident_view.serialize_many(incidents))


def get_incident(event, incident_id):
    """GET /api/incidents/{id} - one ticket."""
    caller = auth.current_user(event)
    get_visible_incident(caller, incident_id)
    incident = incident_model.find_by_id(incident_id)
    return ok(incident_view.serialize(incident))


def assign_incident(event, incident_id):
    """PUT /api/incidents/{id}/assign - give the ticket to an engineer. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)
    if "assigneeId" not in body:
        raise HttpError(400, "'assigneeId' is required (use null to unassign)")
    assignee_id = validation.optional_id(body, "assigneeId")

    # Lock the ticket while we check and change it, so two admins assigning
    # at the same moment cannot both get through the "already" check.
    with transaction():
        incident = incident_model.find_basic(incident_id, lock=True)
        if incident is None:
            raise HttpError(404, "Incident not found")
        if incident["assigned_to"] == assignee_id:
            raise HttpError(400, "Incident already has that assignment")

        # Keep the status in step with the assignment.
        status = incident["status"]
        if assignee_id is None and status == "assigned":
            status = "open"
        elif assignee_id is not None and status == "open":
            status = "assigned"

        if assignee_id is None:
            note = f"Ticket #{incident_id}: unassigned"
        else:
            assignee = user_model.find_by_id(assignee_id)
            if assignee is None:
                raise HttpError(400, "'assigneeId' does not match a known user")
            if assignee["role"] not in auth.STAFF_ROLES:
                raise HttpError(400, "Tickets can only be assigned to an engineer or admin")
            note = f"Ticket #{incident_id}: assigned to {assignee['name']}"

        incident = incident_model.assign(incident_id, assignee_id, status, caller["id"], note)

    logger.info("Incident %s assigned to %s by %s", incident_id, assignee_id, caller["id"])
    return ok(incident_view.serialize(incident))


def update_status(event, incident_id):
    """PUT /api/incidents/{id}/status - move the ticket along. Assignee or admin."""
    caller = auth.current_user(event)
    body = json_body(event)
    status = validation.one_of(body, "status", incident_model.STATUSES)

    with transaction():
        incident = get_incident_for_staff_change(caller, incident_id)
        if incident["status"] == status:
            raise HttpError(400, f"Incident is already {status_label(status)}")

        # "open" means nobody is on the ticket and "assigned" means someone
        # is, so neither can be set by hand against the actual assignment.
        if status == "open" and incident["assigned_to"] is not None:
            raise HttpError(400, "Unassign the engineer before setting the ticket back to open")
        if status == "assigned" and incident["assigned_to"] is None:
            raise HttpError(400, "Assign an engineer to set the ticket to assigned")

        note = f"Ticket #{incident_id}: status changed to {status_label(status)}"
        incident = incident_model.update_status(incident_id, status, caller["id"], note)

    logger.info("Incident %s status changed to %s by %s", incident_id, status, caller["id"])
    return ok(incident_view.serialize(incident))


def update_priority(event, incident_id):
    """PUT /api/incidents/{id}/priority - re-rank the ticket. Assignee or admin."""
    caller = auth.current_user(event)
    body = json_body(event)
    priority = validation.integer_in_range(
        body, "priority", incident_model.MIN_PRIORITY, incident_model.MAX_PRIORITY
    )

    with transaction():
        incident = get_incident_for_staff_change(caller, incident_id)
        if incident["priority"] == priority:
            raise HttpError(400, f"Incident is already priority {priority}")

        note = f"Ticket #{incident_id}: priority changed to {priority}"
        incident = incident_model.update_priority(incident_id, priority, caller["id"], note)

    logger.info("Incident %s priority changed to %s by %s", incident_id, priority, caller["id"])
    return ok(incident_view.serialize(incident))


def update_location(event, incident_id):
    """PUT /api/incidents/{id}/location - move the ticket to another place. Admin only."""
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)
    if "location" not in body:
        raise HttpError(400, "'location' is required (use null to clear it)")

    with transaction():
        incident = incident_model.find_basic(incident_id, lock=True)
        if incident is None:
            raise HttpError(404, "Incident not found")

        location_id, label = location_from_body(body, caller)
        if incident["location_id"] == location_id:
            raise HttpError(400, "Incident already has that location")

        note = f"Ticket #{incident_id}: location changed to {label}"
        incident = incident_model.update_location(incident_id, location_id, caller["id"], note)

    logger.info("Incident %s location changed to %s by %s", incident_id, location_id, caller["id"])
    return ok(incident_view.serialize(incident))

