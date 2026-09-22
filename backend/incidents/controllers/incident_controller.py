"""
Incident controller: filing tickets, reading them, assigning and moving status.

Holds the access rules for tickets. Anyone may file one and read their own;
engineers and admins work the tickets; only admins decide who a ticket goes to.
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

def _status_label(status):
    """Render a stored status for humans: in_progress -> 'in progress'."""
    return status.replace("_", " ")

def _load_visible_incident(caller, incident_id):
    """
    Load an incident the caller is allowed to see.

    Visible to the person who reported it, the engineer assigned to it, and any
    admin. Everyone else gets 404 rather than 403, so the API does not confirm
    that a ticket exists to someone with no access to it.
    """
    row = incident_model.find_access_row(incident_id)
    if row is None:
        raise HttpError(404, "Incident not found")

    if (
        auth.is_admin(caller)
        or row["reported_by"] == caller["id"]
        or row["assigned_to"] == caller["id"]
    ):
        return row

    raise HttpError(404, "Incident not found")

def _location_id_from(body):
    """
    Resolve the optional location on a new ticket.

    Accepts either an existing locationId or a {building, floor, room} object,
    which is reused if that place is already known.
    """
    location_id = validation.positive_id(body, "locationId", required=False)
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
    """
    File a ticket. Any signed-in account may do this.

    The reporter is taken from the token, never from the request body.
    """
    caller = auth.current_user(event)
    body = json_body(event)

    title = validation.required_string(body, "title", max_length=255)
    description = validation.optional_string(body, "description", max_length=5000)
    priority = validation.integer_in_range(
        body,
        "priority",
        incident_model.MIN_PRIORITY,
        incident_model.MAX_PRIORITY,
        default=3,
    )
    location_id = _location_id_from(body)

    row = incident_model.create(
        title=title,
        description=description,
        priority=priority,
        location_id=location_id,
        reported_by=caller["id"],
    )
    logger.info("Incident %s filed by user %s", row["id"], caller["id"])
    return created(incident_view.serialize(row))

def list_incidents(event):
    """
    List tickets the caller may see.

    ?scope=mine        tickets the caller reported (the default)
    ?scope=assigned    tickets assigned to the caller (engineer or admin)
    ?scope=unassigned  tickets waiting for an engineer (admin)
    ?scope=all         every ticket (admin)

    Also accepts ?status= and ?priority= filters.
    """
    caller = auth.current_user(event)
    params = query_params(event)

    scope = params.get("scope", "mine")
    if scope not in ("mine", "assigned", "unassigned", "all"):
        raise HttpError(400, "'scope' must be one of: all, assigned, mine, unassigned")

    status = params.get("status")
    if status is not None and status not in incident_model.STATUSES:
        raise HttpError(
            400, f"'status' must be one of: {', '.join(incident_model.STATUSES)}"
        )

    priority = params.get("priority")
    if priority is not None:
        try:
            priority = int(priority)
        except (TypeError, ValueError) as exc:
            raise HttpError(400, "'priority' must be an integer") from exc
        if not incident_model.MIN_PRIORITY <= priority <= incident_model.MAX_PRIORITY:
            raise HttpError(400, "'priority' must be between 1 and 5")

    if scope == "assigned":
        auth.require_role(caller, *auth.STAFF_ROLES)
        rows = incident_model.search(
            assigned_to=caller["id"], status=status, priority=priority
        )
    elif scope == "unassigned":
        auth.require_role(caller, auth.ROLE_ADMIN)
        rows = incident_model.list_unassigned()
    elif scope == "all":
        auth.require_role(caller, auth.ROLE_ADMIN)
        rows = incident_model.search(status=status, priority=priority)
    else:
        rows = incident_model.search(
            reported_by=caller["id"], status=status, priority=priority
        )

    return ok(incident_view.serialize_many(rows))

def get_incident(event, incident_id):
    """Return one ticket the caller reported, is assigned, or admins."""
    caller = auth.current_user(event)
    _load_visible_incident(caller, incident_id)
    return ok(incident_view.serialize(incident_model.find_by_id(incident_id)))

def assign_incident(event, incident_id):
    """
    Assign a ticket to an engineer, or clear the assignment. Admin only.

    Body: {"assigneeId": 4} to assign, {"assigneeId": null} to unassign.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, auth.ROLE_ADMIN)

    body = json_body(event)
    if "assigneeId" not in body:
        raise HttpError(400, "'assigneeId' is required (use null to unassign)")

    assignee_id = validation.positive_id(body, "assigneeId", required=False)

    if assignee_id is not None:
        assignee = user_model.find_by_id(assignee_id)
        if assignee is None:
            raise HttpError(400, "'assigneeId' does not match a known user")
        # Employees cannot hold tickets; only engineers and admins work them.
        if assignee["role"] not in auth.STAFF_ROLES:
            raise HttpError(400, "Tickets can only be assigned to an engineer or admin")

    row = incident_model.assign(incident_id, assignee_id)
    if row is None:
        raise HttpError(404, "Incident not found")

    logger.info("Incident %s assigned to %s by %s", incident_id, assignee_id, caller["id"])
    return ok(incident_view.serialize(row))

def update_status(event, incident_id):
    """
    Move a ticket to a new status. Engineers and admins only.

    Records the change as a message on the ticket, in the same transaction, so
    the thread always shows how the ticket got to its current state.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, *auth.STAFF_ROLES)

    body = json_body(event)
    status = validation.one_of(body, "status", incident_model.STATUSES)

    existing = incident_model.find_access_row(incident_id)
    if existing is None:
        raise HttpError(404, "Incident not found")

    # An engineer works the tickets given to them; an admin may act on any.
    if not auth.is_admin(caller) and existing["assigned_to"] != caller["id"]:
        raise HttpError(403, "Access denied")

    if existing["status"] == status:
        raise HttpError(400, f"Incident is already {_status_label(status)}")

    note = f"Ticket #{incident_id}: status changed to {_status_label(status)}"
    row = incident_model.update_status_with_message(
        incident_id, status, caller["id"], note
    )
    if row is None:
        raise HttpError(404, "Incident not found")

    logger.info("Incident %s status -> %s by %s", incident_id, status, caller["id"])
    return ok(incident_view.serialize(row))

def list_locations(event):
    """Return known locations, for the report-a-ticket form."""
    auth.current_user(event)
    return ok([incident_view.serialize_location(row) for row in location_model.list_all()])
