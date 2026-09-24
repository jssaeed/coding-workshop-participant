"""
Incident controller: the rules for tickets.

- Anyone signed in can file a ticket and see the tickets they filed. A
  ticket belongs to the branch it was filed at (the reporter's branch).
- Engineers and admins can see the tickets assigned to them.
- Only facility admins can see all tickets, assign them and change their
  location, and only at their own branch: a Miami admin never sees a
  Princeton ticket, and tickets are only assigned to staff at the ticket's
  branch.
- The assigned engineer (or an admin at the branch) can change a ticket's
  status, priority and category.
- Assigning an open ticket moves it to "assigned"; unassigning an "assigned"
  ticket moves it back to "open". "open" always means nobody is on it.
- An engineer cannot set "blocked" or "resolved" by themselves. Their
  request is recorded on the ticket and a facility admin approves or
  rejects it. Admins set those statuses directly.

Status, priority, category, assignment and location changes also add a
message to the ticket, so the thread shows the history and the change
appears in other users' inboxes.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from lib import auth, validation
from lib.database import transaction
from lib.labels import floor_label, room_label
from lib.request import choice_param, int_param, json_body, page_params, positive_int_param, query_params, text_param
from lib.responses import HttpError, created, ok, paged
from models import building as building_model
from models import incident as incident_model
from models import location as location_model
from models import user as user_model
from views import incident_view

logger = logging.getLogger()


def status_label(status):
    """'in_progress' -> 'in progress', for messages people read."""
    return status.replace("_", " ")


def category_label(category):
    """'doors_and_locks' -> 'doors and locks', 'hvac' -> 'AC / heating', for messages people read."""
    if category == "hvac":
        return "AC / heating"
    return category.replace("_", " ")


def is_admin_of(caller, incident):
    """A facility admin's powers over a ticket stop at their own branch."""
    return auth.is_admin(caller) and incident["branch_id"] == caller["branch_id"]


def can_see(caller, incident):
    """The reporter, the assignee and the admins at the ticket's branch may see a ticket."""
    return (
        is_admin_of(caller, incident)
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


def check_floor(building, floor):
    """
    Raise 400 unless floor is a whole number the building has. Floors run
    1..floors above ground and -1..-basementFloors below (-1 is "B1"); there
    is no floor 0.
    """
    lowest = -building["basement_floors"]
    if not isinstance(floor, int) or isinstance(floor, bool) or floor == 0 or not lowest <= floor <= building["floors"]:
        raise HttpError(400, f"'floor' must be between {floor_label(lowest) if lowest else 1} and {building['floors']} (there is no floor 0)")


def building_at_branch(building_id, caller, lock=False):
    """Load a building the caller may refer to, or raise 400. It must be at their branch."""
    building = building_model.find_by_id(building_id, lock=lock)
    if building is None:
        raise HttpError(400, "'buildingId' does not match a known building")
    if building["branch_id"] != caller["branch_id"]:
        raise HttpError(400, "'buildingId' is not a building at your branch")
    return building


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
    building = building_at_branch(building_id, caller, lock=True)

    floor = location.get("floor")
    check_floor(building, floor)

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
    them; admins may change any ticket at their branch. Call this inside
    "with transaction():" so the lock lasts until the change is saved.
    """
    auth.require_role(caller, auth.STAFF_ROLES)

    incident = incident_model.find_basic(incident_id, lock=True)
    # An admin at another branch gets 404, like any ticket they cannot see.
    if incident is None or (auth.is_admin(caller) and not can_see(caller, incident)):
        raise HttpError(404, "Incident not found")

    if not is_admin_of(caller, incident) and incident["assigned_to"] != caller["id"]:
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
    category = validation.one_of(body, "category", incident_model.CATEGORIES, default=incident_model.DEFAULT_CATEGORY)
    # The location row (if new) and the ticket are saved together.
    with transaction():
        location_id, _ = location_from_body(body, caller)
        incident = incident_model.create(
            title, description, priority, category, location_id, caller["id"], caller["branch_id"]
        )

    logger.info("Incident %s filed by user %s", incident["id"], caller["id"])
    return created(incident_view.serialize(incident))


def list_incidents(event):
    """
    GET /api/incidents - one page of tickets.

    ?scope=mine        tickets I filed (the default)
    ?scope=assigned    tickets assigned to me (engineer or admin)
    ?scope=unassigned  tickets with no engineer yet (admin, own branch)
    ?scope=pending     tickets waiting for an approval (admin, own branch)
    ?scope=all         every ticket at my branch (admin)
    ?status=open, ?priority=2 and ?category=plumbing narrow the list further.
    ?status=open,in_progress keeps tickets in ANY of the listed statuses.
    ?days=14 keeps only tickets created in the last N days (1-365).
    ?buildingId=2 keeps only tickets in that building; add ?floor=3 (or
    ?floor=-1 for B1) for one floor of it. floor needs buildingId.
    ?q=leak searches the title, description, people and building.
    ?sort=priority|created|updated|id|title|location and ?order=asc|desc order it.
    ?page=2&limit=25 pick the page (limit at most 100).

    The answer is {"items": [...], "total": N, "page": 2, "limit": 25, "pages": M}.
    """
    caller = auth.current_user(event)
    params = query_params(event)

    scope = choice_param(params, "scope", ["mine", "assigned", "unassigned", "pending", "all"], default="mine")
    status = statuses_from_query(params)
    priority = int_param(params, "priority", incident_model.MIN_PRIORITY, incident_model.MAX_PRIORITY)
    category = choice_param(params, "category", incident_model.CATEGORIES)
    days = int_param(params, "days", 1, 365)
    since = None if days is None else datetime.now(timezone.utc) - timedelta(days=days)
    q = text_param(params, "q")
    building_id, floor = place_from_query(params, caller)
    sort = choice_param(params, "sort", list(incident_model.SORTS), default=incident_model.DEFAULT_SORT)
    descending = choice_param(params, "order", ["asc", "desc"], default="asc") == "desc"
    page, limit, offset = page_params(params)

    filters = {"status": status, "priority": priority, "category": category, "since": since, "q": q,
               "building_id": building_id, "floor": floor}
    if scope == "mine":
        filters["reported_by"] = caller["id"]
    elif scope == "assigned":
        auth.require_role(caller, auth.STAFF_ROLES)
        filters["assigned_to"] = caller["id"]
    elif scope == "unassigned":
        auth.require_role(caller, [auth.ROLE_ADMIN])
        filters["unassigned"] = True
        filters["branch_id"] = caller["branch_id"]
    elif scope == "pending":
        auth.require_role(caller, [auth.ROLE_ADMIN])
        filters["pending"] = True
        filters["branch_id"] = caller["branch_id"]
    else:  # "all": every ticket at the admin's own branch
        auth.require_role(caller, [auth.ROLE_ADMIN])
        filters["branch_id"] = caller["branch_id"]

    total = incident_model.count(**filters)
    incidents = incident_model.search(**filters, sort=sort, descending=descending, limit=limit, offset=offset)
    return paged(incident_view.serialize_many(incidents), total, page, limit)


def statuses_from_query(params):
    """
    Read ?status= from a list request: one status, or several separated by
    commas ("open,in_progress"). Returns a list, or None when absent. Each
    one must be a real status, else 400.
    """
    text = params.get("status")
    if text is None or text.strip() == "":
        return None
    statuses = [status.strip() for status in text.split(",")]
    for status in statuses:
        if status not in incident_model.STATUSES:
            raise HttpError(400, f"'status' must be one of: {', '.join(incident_model.STATUSES)}")
    return statuses


def place_from_query(params, caller):
    """
    Read ?buildingId= and ?floor= from a list request.

    Returns (building_id, floor), either or both None when absent. The
    building must exist at the caller's branch, and a floor needs a building
    (a floor number means nothing on its own) and must be one that building
    has - the same rules as a ticket's location.
    """
    building_id = positive_int_param(params, "buildingId")
    floor_text = params.get("floor")
    if floor_text is None or floor_text == "":
        if building_id is not None:
            building_at_branch(building_id, caller)
        return building_id, None

    if building_id is None:
        raise HttpError(400, "'floor' needs a 'buildingId'")
    building = building_at_branch(building_id, caller)
    floor = int(floor_text) if isinstance(floor_text, str) and re.fullmatch(r"-?\d+", floor_text) else None
    check_floor(building, floor)  # raises for a non-number too
    return building_id, floor


def get_incident(event, incident_id):
    """GET /api/incidents/{id} - one ticket."""
    caller = auth.current_user(event)
    get_visible_incident(caller, incident_id)
    incident = incident_model.find_by_id(incident_id)
    return ok(incident_view.serialize(incident))


def assign_incident(event, incident_id):
    """
    PUT /api/incidents/{id}/assign - give the ticket to an engineer. Admin
    only, and the engineer must work at the ticket's branch.
    """
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
        if incident is None or not is_admin_of(caller, incident):
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
            if assignee["branch_id"] != incident["branch_id"]:
                raise HttpError(400, "Tickets can only be assigned to staff at the ticket's branch")
            note = f"Ticket #{incident_id}: assigned to {assignee['name']}"

        incident = incident_model.assign(incident_id, assignee_id, status, caller["id"], note)

    logger.info("Incident %s assigned to %s by %s", incident_id, assignee_id, caller["id"])
    return ok(incident_view.serialize(incident))


def update_status(event, incident_id):
    """
    PUT /api/incidents/{id}/status - move the ticket along. Assignee or admin.

    Body: {"status": "...", "note": "optional text"}. When an engineer asks
    for "blocked" or "resolved" the status does not change yet: the request
    is stored on the ticket for a facility admin to approve (see
    decide_approval). Any other change by anyone drops a pending request.
    """
    caller = auth.current_user(event)
    body = json_body(event)
    status = validation.one_of(body, "status", incident_model.STATUSES)
    note = validation.optional_string(body, "note", max_length=1000)

    with transaction():
        incident = get_incident_for_staff_change(caller, incident_id)
        if incident["status"] == status:
            raise HttpError(400, f"Incident is already {status_label(status)}")

        if status in incident_model.APPROVAL_STATUSES and not auth.is_admin(caller):
            if incident["pending_status"] == status:
                raise HttpError(400, f"A request to mark this ticket {status_label(status)} is already waiting for approval")
            message = f"Ticket #{incident_id}: requested {status_label(status)}, awaiting facility admin approval"
            if note:
                message += f" - {note}"
            incident = incident_model.request_status(incident_id, status, caller["id"], note, caller["id"], message)
            logger.info("Incident %s: %s requested %s", incident_id, caller["id"], status)
            return ok(incident_view.serialize(incident))

        # "open" means nobody is on the ticket and "assigned" means someone
        # is, so neither can be set by hand against the actual assignment.
        if status == "open" and incident["assigned_to"] is not None:
            raise HttpError(400, "Unassign the engineer before setting the ticket back to open")
        if status == "assigned" and incident["assigned_to"] is None:
            raise HttpError(400, "Assign an engineer to set the ticket to assigned")

        message = f"Ticket #{incident_id}: status changed to {status_label(status)}"
        if note:
            message += f" - {note}"
        incident = incident_model.update_status(incident_id, status, caller["id"], message)

    logger.info("Incident %s status changed to %s by %s", incident_id, status, caller["id"])
    return ok(incident_view.serialize(incident))


def decide_approval(event, incident_id):
    """
    PUT /api/incidents/{id}/approval - approve or reject an engineer's
    request to block or resolve. Admin only.

    Body: {"decision": "approve" | "reject", "note": "optional text"}.
    Approving applies the requested status; rejecting just clears the
    request. Either way a message records who decided and why.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    body = json_body(event)
    decision = validation.one_of(body, "decision", ["approve", "reject"])
    note = validation.optional_string(body, "note", max_length=1000)

    with transaction():
        incident = incident_model.find_basic(incident_id, lock=True)
        if incident is None or not is_admin_of(caller, incident):
            raise HttpError(404, "Incident not found")
        if incident["pending_status"] is None:
            raise HttpError(400, "Nothing is waiting for approval on this ticket")

        wanted = incident["pending_status"]
        if decision == "approve":
            message = f"Ticket #{incident_id}: status changed to {status_label(wanted)} (approved)"
            if note:
                message += f" - {note}"
            incident = incident_model.update_status(incident_id, wanted, caller["id"], message)
        else:
            message = f"Ticket #{incident_id}: request to mark {status_label(wanted)} rejected"
            if note:
                message += f" - {note}"
            incident = incident_model.clear_request(incident_id, caller["id"], message)

    logger.info("Incident %s: %s %sd %s", incident_id, caller["id"], decision, wanted)
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


def update_category(event, incident_id):
    """PUT /api/incidents/{id}/category - say what kind of problem it is. Assignee or admin."""
    caller = auth.current_user(event)
    body = json_body(event)
    category = validation.one_of(body, "category", incident_model.CATEGORIES)

    with transaction():
        incident = get_incident_for_staff_change(caller, incident_id)
        if incident["category"] == category:
            raise HttpError(400, f"Incident is already in the {category_label(category)} category")

        note = f"Ticket #{incident_id}: category changed to {category_label(category)}"
        incident = incident_model.update_category(incident_id, category, caller["id"], note)

    logger.info("Incident %s category changed to %s by %s", incident_id, category, caller["id"])
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
        if incident is None or not is_admin_of(caller, incident):
            raise HttpError(404, "Incident not found")

        location_id, label = location_from_body(body, caller)
        if incident["location_id"] == location_id:
            raise HttpError(400, "Incident already has that location")

        note = f"Ticket #{incident_id}: location changed to {label}"
        incident = incident_model.update_location(incident_id, location_id, caller["id"], note)

    logger.info("Incident %s location changed to %s by %s", incident_id, location_id, caller["id"])
    return ok(incident_view.serialize(incident))

