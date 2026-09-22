"""
Messages service: the conversation on a ticket.

    POST /api/messages                    add a message to a ticket
    GET  /api/messages?incidentId={id}    read a ticket's thread

Both are limited to the ticket's reporter, its assigned engineer, and admins.
"""

import logging

from controllers import message_controller
from lib.request import http_method, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "messages"


def route(event):
    """Pick the controller function for this method and path."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/messages
    if len(segments) == 0:
        if method == "POST":
            return message_controller.create_message(event)
        if method == "GET":
            return message_controller.list_messages(event)
        return method_not_allowed(method)

    return not_found()


def handler(event=None, context=None):
    """Lambda entry point."""
    try:
        return route(event or {})
    except HttpError as error:
        return error.to_response()
    except Exception as error:
        logger.exception("Unhandled error in messages service: %s", error)
        return json_response(500, {"error": "Internal server error"})
