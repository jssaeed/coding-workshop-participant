"""
Inbox controller: what the signed-in user has not seen yet.

The inbox is personal. Every function works on the caller's own inbox; there
is no way to look at anyone else's.
"""

import logging

from lib import auth
from lib.database import transaction
from lib.responses import HttpError, ok
from models import inbox as inbox_model
from views import inbox_view

logger = logging.getLogger()


def list_inbox(event):
    """GET /api/inbox - tickets with unread messages, most recent first."""
    caller = auth.current_user(event)
    entries = inbox_model.unread_by_ticket(caller["id"])
    return ok(inbox_view.serialize_inbox(entries))


def count(event):
    """GET /api/inbox/count - just the unread total, for the badge."""
    caller = auth.current_user(event)
    return ok({"unread": inbox_model.unread_count(caller["id"])})


def mark_read(event, incident_id):
    """PUT /api/inbox/{id}/read - the caller has seen this ticket's thread."""
    caller = auth.current_user(event)

    # The access check, the write and the recount are one transaction, so
    # the badge number matches exactly what was just marked read.
    with transaction():
        incident = inbox_model.find_basic_incident(incident_id)
        if incident is None:
            raise HttpError(404, "Incident not found")

        allowed = (
            auth.is_admin(caller)
            or incident["reported_by"] == caller["id"]
            or incident["assigned_to"] == caller["id"]
        )
        if not allowed:
            raise HttpError(404, "Incident not found")

        row = inbox_model.mark_read(caller["id"], incident_id)
        # The remaining total, so the frontend badge can update right away.
        unread = inbox_model.unread_count(caller["id"])

    return ok({
        "incidentId": row["incident_id"],
        "lastReadAt": row["last_read_at"],
        "unread": unread,
    })


def mark_all_read(event):
    """PUT /api/inbox/read-all - the caller has seen everything."""
    caller = auth.current_user(event)
    with transaction():
        inbox_model.mark_all_read(caller["id"])
    logger.info("User %s marked their inbox read", caller["id"])
    return ok({"unread": 0})
