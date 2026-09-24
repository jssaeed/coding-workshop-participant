"""
Incidents service: tickets.

    POST /api/incidents               file a ticket
    GET  /api/incidents               one page of tickets (?scope=&status=&priority=&category=&days=&buildingId=&floor=&q=&sort=&order=&page=&limit=)
    GET  /api/incidents/{id}          one ticket
    PUT  /api/incidents/{id}/assign   assign an engineer (admin)
    PUT  /api/incidents/{id}/status   change the status (assignee or admin)
    PUT  /api/incidents/{id}/priority change the priority (assignee or admin)
    PUT  /api/incidents/{id}/category change the category (assignee or admin)
    PUT  /api/incidents/{id}/approval approve/reject a blocked/resolved request (admin)
    PUT  /api/incidents/{id}/location move the ticket to another place (admin)
    GET  /api/incidents/stats/overview   tickets by status, priority and category (admin)
    GET  /api/incidents/stats/locations  tickets per building / floor / room (admin)
    GET  /api/incidents/stats/engineers  per-engineer workload and resolution time (admin)
    GET  /api/incidents/stats/mine       the caller's own tickets by status

This file only decides which controller function handles the request. The
rules live in controllers/, the SQL in models/, the JSON shape in views/.
"""

import logging

from controllers import incident_controller, stats_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "incidents"


def route(event):
    """Pick the controller function for this method and path."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/incidents
    if len(segments) == 0:
        if method == "POST":
            return incident_controller.create_incident(event)
        if method == "GET":
            return incident_controller.list_incidents(event)
        return method_not_allowed(method)

    # /api/incidents/stats/{overview|locations|mine}
    # Checked before path_id(), because "stats" is not a ticket number.
    if segments[0] == "stats":
        if method != "GET":
            return method_not_allowed(method)
        if len(segments) == 2 and segments[1] == "overview":
            return stats_controller.overview(event)
        if len(segments) == 2 and segments[1] == "locations":
            return stats_controller.locations(event)
        if len(segments) == 2 and segments[1] == "engineers":
            return stats_controller.engineers(event)
        if len(segments) == 2 and segments[1] == "mine":
            return stats_controller.mine(event)
        return not_found()

    incident_id = path_id(segments)

    # /api/incidents/{id}
    if len(segments) == 1:
        if method == "GET":
            return incident_controller.get_incident(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/assign
    if len(segments) == 2 and segments[1] == "assign":
        if method == "PUT":
            return incident_controller.assign_incident(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/status
    if len(segments) == 2 and segments[1] == "status":
        if method == "PUT":
            return incident_controller.update_status(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/approval
    if len(segments) == 2 and segments[1] == "approval":
        if method == "PUT":
            return incident_controller.decide_approval(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/priority
    if len(segments) == 2 and segments[1] == "priority":
        if method == "PUT":
            return incident_controller.update_priority(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/category
    if len(segments) == 2 and segments[1] == "category":
        if method == "PUT":
            return incident_controller.update_category(event, incident_id)
        return method_not_allowed(method)

    # /api/incidents/{id}/location
    if len(segments) == 2 and segments[1] == "location":
        if method == "PUT":
            return incident_controller.update_location(event, incident_id)
        return method_not_allowed(method)

    return not_found()


def handler(event=None, context=None):
    """Lambda entry point."""
    try:
        return route(event or {})
    except HttpError as error:
        return error.to_response()
    except Exception as error:
        logger.exception("Unhandled error in incidents service: %s", error)
        return json_response(500, {"error": "Internal server error"})
