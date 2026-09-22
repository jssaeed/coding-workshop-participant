"""
Inbox service: changes on your tickets that you have not seen yet.

    GET /api/inbox              tickets with unread messages
    GET /api/inbox/count        the unread total only
    PUT /api/inbox/{id}/read    mark one ticket's thread as read
    PUT /api/inbox/read-all     mark everything as read

Status changes and assignments are saved as messages, so they count as
unread changes too.
"""

import logging

from controllers import inbox_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "inbox"


def route(event):
    """Pick the controller function for this method and path."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/inbox
    if len(segments) == 0:
        if method == "GET":
            return inbox_controller.list_inbox(event)
        return method_not_allowed(method)

    # /api/inbox/count
    if segments == ["count"]:
        if method == "GET":
            return inbox_controller.count(event)
        return method_not_allowed(method)

    # /api/inbox/read-all
    if segments == ["read-all"]:
        if method == "PUT":
            return inbox_controller.mark_all_read(event)
        return method_not_allowed(method)

    # /api/inbox/{id}/read
    incident_id = path_id(segments)
    if len(segments) == 2 and segments[1] == "read":
        if method == "PUT":
            return inbox_controller.mark_read(event, incident_id)
        return method_not_allowed(method)

    return not_found()


def handler(event=None, context=None):
    """Lambda entry point."""
    try:
        return route(event or {})
    except HttpError as error:
        return error.to_response()
    except Exception as error:
        logger.exception("Unhandled error in inbox service: %s", error)
        return json_response(500, {"error": "Internal server error"})
