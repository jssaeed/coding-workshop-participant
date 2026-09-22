"""
Inbox service: unread activity on the caller's tickets.

    GET /api/inbox              tickets with unread messages, newest first
    GET /api/inbox/count        unread total only (cheap to poll)
    PUT /api/inbox/{id}/read    mark one ticket's thread read
    PUT /api/inbox/read-all     mark everything read

A message is unread when it is on a ticket you reported or are assigned to,
someone else wrote it, and you have not opened the ticket since. Status and
assignment changes are recorded as messages, so they surface here too.
"""

import logging

from controllers import inbox_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "inbox"

def route(event):
    """Dispatch a request to the controller that handles it."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/inbox
    if not segments:
        if method == "GET":
            return inbox_controller.list_inbox(event)
        return method_not_allowed(method)

    # /api/inbox/count
    if segments[0] == "count":
        if method == "GET":
            return inbox_controller.count(event)
        return method_not_allowed(method)

    # /api/inbox/read-all
    if segments[0] == "read-all":
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
    """
    Lambda entry point for the inbox service.

    Args:
        event (dict, optional): The Lambda event
        context (object, optional): The Lambda context

    Returns:
        dict: A response object with statusCode, headers, and body
    """
    logger.debug("Received event: %s", event)

    try:
        return route(event or {})
    except HttpError as error:
        logger.info("Request rejected (%s): %s", error.status_code, error.message)
        return error.to_response()
    except Exception as e:
        logger.exception("Unhandled error in inbox service: %s", e)
        return json_response(500, {"error": "Internal server error"})
