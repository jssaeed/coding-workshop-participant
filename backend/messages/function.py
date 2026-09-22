"""
Messages service: the conversation on a ticket.

    POST /api/messages                    post a message on a ticket
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
    """Dispatch a request to the controller that handles it."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/messages
    if not segments:
        if method == "POST":
            return message_controller.create_message(event)
        if method == "GET":
            return message_controller.list_messages(event)
        return method_not_allowed(method)

    return not_found()

def handler(event=None, context=None):
    """
    Lambda entry point for the messages service.

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
        logger.exception("Unhandled error in messages service: %s", e)
        return json_response(500, {"error": "Internal server error"})
