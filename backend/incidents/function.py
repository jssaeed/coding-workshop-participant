"""
Incidents service: filing, reading, assigning and progressing tickets.

    POST /api/incidents               file a ticket (any account)
    GET  /api/incidents               list tickets, see ?scope= below
    GET  /api/incidents/locations     known buildings and floors
    GET  /api/incidents/{id}          one ticket (reporter, assignee or admin)
    PUT  /api/incidents/{id}/assign   assign to an engineer (admin)
    PUT  /api/incidents/{id}/status   change status (assigned engineer or admin)

Scopes for the list route: mine (default), assigned, unassigned, all.
"""

import logging

from controllers import incident_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "incidents"

def route(event):
    """Dispatch a request to the controller that handles it."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/incidents
    if not segments:
        if method == "POST":
            return incident_controller.create_incident(event)
        if method == "GET":
            return incident_controller.list_incidents(event)
        return method_not_allowed(method)

    # /api/incidents/locations
    if segments[0] == "locations":
        if method == "GET":
            return incident_controller.list_locations(event)
        return method_not_allowed(method)

    incident_id = path_id(segments)

    # /api/incidents/{id}
    if len(segments) == 1:
        if method == "GET":
            return incident_controller.get_incident(event, incident_id)
        return method_not_allowed(method)

    action = segments[1]

    # /api/incidents/{id}/assign
    if action == "assign":
        if method == "PUT":
            return incident_controller.assign_incident(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/status
    if action == "status":
        if method == "PUT":
            return incident_controller.update_status(event, incident_id)
        return method_not_allowed(method)

    return not_found()

def handler(event=None, context=None):
    """
    Lambda entry point for the incidents service.

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
        logger.exception("Unhandled error in incidents service: %s", e)
        return json_response(500, {"error": "Internal server error"})
