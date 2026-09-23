"""
Message controller: the rules for a ticket's thread.

One rule covers both reading and writing: you can take part in a thread if
you reported the ticket, you are assigned to it, or you are an admin.
"""

import logging

from lib import auth, validation
from lib.database import transaction
from lib.request import json_body, query_params
from lib.responses import HttpError, created, ok
from models import incident as incident_model
from models import message as message_model
from views import message_view

logger = logging.getLogger()

MAX_MESSAGE_LENGTH = 5000


def get_incident_for_thread(caller, incident_id, lock=False):
    """
    Load the ticket if the caller may use its thread, else raise 404.

    404 rather than 403 for outsiders, so they cannot learn which ticket ids
    exist. lock=True holds the ticket steady until the caller's transaction
    ends (used when posting, so the ticket cannot close mid-request).
    """
    incident = incident_model.find_basic(incident_id, lock=lock)
    if incident is None:
        raise HttpError(404, "Incident not found")

    allowed = (
        auth.is_admin(caller)
        or incident["reported_by"] == caller["id"]
        or incident["assigned_to"] == caller["id"]
    )
    if not allowed:
        raise HttpError(404, "Incident not found")
    return incident


def create_message(event):
    """POST /api/messages - add a message. The caller is the author."""
    caller = auth.current_user(event)
    body = json_body(event)

    incident_id = validation.required_id(body, "incidentId")
    text = validation.required_string(body, "message", max_length=MAX_MESSAGE_LENGTH)

    with transaction():
        incident = get_incident_for_thread(caller, incident_id, lock=True)
        if incident["status"] == "closed":
            raise HttpError(409, "Incident is closed and cannot receive new messages")

        message = message_model.create(incident_id, caller["id"], text)

    logger.info("Message %s posted on incident %s by %s", message["id"], incident_id, caller["id"])
    return created(message_view.serialize(message))


def list_messages(event):
    """GET /api/messages?incidentId=12 - a ticket's thread, oldest first."""
    caller = auth.current_user(event)

    incident_id = query_params(event).get("incidentId")
    if incident_id is None:
        raise HttpError(400, "'incidentId' query parameter is required")
    if not incident_id.isdigit() or int(incident_id) < 1:
        raise HttpError(400, "'incidentId' must be a positive whole number")
    incident_id = int(incident_id)

    get_incident_for_thread(caller, incident_id)

    messages = message_model.list_for_incident(incident_id)
    return ok(message_view.serialize_many(messages))
