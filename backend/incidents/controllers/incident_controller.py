"""
Incident controller: the rules for tickets.

- Anyone signed in can file a ticket and see the tickets they filed.
- Engineers and admins can see the tickets assigned to them.
- Only admins can see all tickets and assign them.
- The assigned engineer (or an admin) can change a ticket's status.

Status and assignment changes also add a message to the ticket, so the
thread shows the history and the change appears in other users' inboxes.
"""

import logging

from lib import auth, validation
from lib.request import json_body, query_params
from lib.responses import HttpError, created, ok
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


def location_id_from_body(body):
    """
    Work out the location for a new ticket. Returns a location id or None.

    The request can send either "locationId": 5 (an existing location) or
    "location": {"building": ..., "floor": ..., "room": ...}, or neither.
    """
    location_id = validation.optional_id(body, "locationId")
    if location_id is not None:
        if location_model.find_by_id(location_id) is None:
            raise HttpError(400, "'locationId' does not match a known location")
        return location_id

    location = body.get("location")
    if location is None:
        return None
    if not isinstance(location, dict):
        raise HttpError(400, "'location' must be an object")

    building = validation.required_string(location, "building", max_length=255)
    floor = validation.required_string(location, "floor", max_length=64)
    room = validation.optional_string(location, "room", max_length=64)
    return location_model.find_or_create(building, floor, room)["id"]


def create_incident(event):
    """POST /api/incidents - file a ticket. The caller becomes the reporter."""
    caller = auth.current_user(event)
    body = json_body(event)

    title = validation.required_string(body, "title", max_length=255)
    description = validation.optional_string(body, "description", max_length=5000)
    priority = validation.integer_in_range(
        body, "priority", incident_model.MIN_PRIORITY, incident_model.MAX_PRIORITY, default=3
    )
    location_id = location_id_from_body(body)

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

    incident = incident_model.find_basic(incident_id)
    if incident is None:
        raise HttpError(404, "Incident not found")
    if incident["assigned_to"] == assignee_id:
        raise HttpError(400, "Incident already has that assignment")

    if assignee_id is None:
        note = f"Ticket #{incident_id}: unassigned"
    else:
        assignee = user_model.find_by_id(assignee_id)
        if assignee is None:
            raise HttpError(400, "'assigneeId' does not match a known user")
        if assignee["role"] not in auth.STAFF_ROLES:
            raise HttpError(400, "Tickets can only be assigned to an engineer or admin")
        note = f"Ticket #{incident_id}: assigned to {assignee['name']}"

    incident = incident_model.assign(incident_id, assignee_id, caller["id"], note)
    logger.info("Incident %s assigned to %s by %s", incident_id, assignee_id, caller["id"])
    return ok(incident_view.serialize(incident))


def update_status(event, incident_id):
    """PUT /api/incidents/{id}/status - move the ticket along. Assignee or admin."""
    caller = auth.current_user(event)
    auth.require_role(caller, auth.STAFF_ROLES)

    body = json_body(event)
    status = validation.one_of(body, "status", incident_model.STATUSES)

    incident = incident_model.find_basic(incident_id)
    if incident is None:
        raise HttpError(404, "Incident not found")

    # An engineer may only change tickets assigned to them. Admins may change any.
    if not auth.is_admin(caller) and incident["assigned_to"] != caller["id"]:
        raise HttpError(403, "Access denied")

    if incident["status"] == status:
        raise HttpError(400, f"Incident is already {status_label(status)}")

    note = f"Ticket #{incident_id}: status changed to {status_label(status)}"
    incident = incident_model.update_status(incident_id, status, caller["id"], note)
    logger.info("Incident %s status changed to %s by %s", incident_id, status, caller["id"])
    return ok(incident_view.serialize(incident))


def list_locations(event):
    """GET /api/incidents/locations - every known location."""
    auth.current_user(event)
    locations = location_model.list_all()
    return ok([incident_view.serialize_location(row) for row in locations])
