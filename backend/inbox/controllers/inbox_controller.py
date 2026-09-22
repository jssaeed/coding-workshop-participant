"""
Inbox controller: what a user has not seen yet, and marking it seen.

Everything here is scoped to the caller. There is no way to read or change
another user's inbox, and admins get no special view: an inbox is personal.
"""

import logging

from lib import auth
from lib.responses import HttpError, ok
from models import inbox as inbox_model
from views import inbox_view

logger = logging.getLogger()

def list_inbox(event):
    """Tickets with unread activity for the caller, most recent first."""
    caller = auth.current_user(event)
    rows = inbox_model.unread_by_ticket(caller["id"])
    # Summing the rows avoids a second query for the total.
    total = sum(row["unread_count"] for row in rows)
    return ok(inbox_view.serialize_inbox(rows, total))

def count(event):
    """Just the unread total, for the nav badge to poll."""
    caller = auth.current_user(event)
    return ok(inbox_view.serialize_count(inbox_model.unread_count(caller["id"])))

def mark_read(event, incident_id):
    """
    Mark one ticket's thread as read up to now.

    Allowed for anyone who can see the ticket (reporter, assignee, admin).
    Others get 404 so the endpoint does not reveal which ticket ids exist.
    """
    caller = auth.current_user(event)

    incident = inbox_model.find_access_row(incident_id)
    if incident is None:
        raise HttpError(404, "Incident not found")
    if not (
        auth.is_admin(caller)
        or incident["reported_by"] == caller["id"]
        or incident["assigned_to"] == caller["id"]
    ):
        raise HttpError(404, "Incident not found")

    row = inbox_model.mark_read(caller["id"], incident_id)
    return ok(inbox_view.serialize_read(row, inbox_model.unread_count(caller["id"])))

def mark_all_read(event):
    """Mark every ticket the caller is involved in as read up to now."""
    caller = auth.current_user(event)
    inbox_model.mark_all_read(caller["id"])
    logger.info("User %s marked inbox read", caller["id"])
    return ok(inbox_view.serialize_count(0))
