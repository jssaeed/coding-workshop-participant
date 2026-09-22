"""
Message controller: the conversation on a ticket.

One access rule governs both reading and posting: you may take part in a
ticket's thread if you reported it, are assigned to it, or are an admin.
"""

import logging

from lib import auth, validation
from lib.request import json_body, query_params
from lib.responses import HttpError, created, ok
from models import incident as incident_model
from models import message as message_model
from views import message_view

logger = logging.getLogger()

MAX_MESSAGE_LENGTH = 5000

def _require_thread_access(caller, incident_id):
    """
    Confirm the caller may take part in this ticket's thread.

    Raises 404 rather than 403 for outsiders, so the API does not reveal which
    ticket ids exist to people with no access to them.
    """
    incident = incident_model.find_access_row(incident_id)
    if incident is None:
        raise HttpError(404, "Incident not found")

    if (
        auth.is_admin(caller)
        or incident["reported_by"] == caller["id"]
        or incident["assigned_to"] == caller["id"]
    ):
        return incident

    raise HttpError(404, "Incident not found")

def create_message(event):
    """
    Post a message on a ticket.

    The author is taken from the token, never from the request body.
    """
    caller = auth.current_user(event)
    body = json_body(event)

    incident_id = validation.positive_id(body, "incidentId")
    text = validation.required_string(body, "message", max_length=MAX_MESSAGE_LENGTH)

    incident = _require_thread_access(caller, incident_id)

    # A closed ticket is a finished record; reopen it to continue the thread.
    if incident["status"] == "closed":
        raise HttpError(409, "Incident is closed and cannot receive new messages")

    row = message_model.create(incident_id, caller["id"], text)
    logger.info("Message %s posted on incident %s by %s", row["id"], incident_id, caller["id"])
    return created(message_view.serialize(row))

def list_messages(event):
    """
    Return a ticket's thread, oldest first.

    Requires ?incidentId=, since messages are only ever read per ticket.
    """
    caller = auth.current_user(event)

    raw_id = query_params(event).get("incidentId")
    if raw_id is None:
        raise HttpError(400, "'incidentId' query parameter is required")
    try:
        incident_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, "'incidentId' must be an integer") from exc
    if incident_id < 1:
        raise HttpError(400, "'incidentId' must be a positive integer")

    _require_thread_access(caller, incident_id)

    rows = message_model.list_for_incident(incident_id)
    return ok(message_view.serialize_many(rows))
