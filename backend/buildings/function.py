"""
Buildings service: the buildings, and how many floors each has.

    GET    /api/buildings        list buildings (any signed-in user)
    POST   /api/buildings        add a building (admin)
    PUT    /api/buildings/{id}   rename or change floor count (admin)
    DELETE /api/buildings/{id}   remove a building (admin)

The ticket form uses the list to offer buildings and floors as dropdowns.
"""

import logging

from controllers import building_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "buildings"


def route(event):
    """Pick the controller function for this method and path."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/buildings
    if len(segments) == 0:
        if method == "GET":
            return building_controller.list_buildings(event)
        if method == "POST":
            return building_controller.create_building(event)
        return method_not_allowed(method)

    building_id = path_id(segments)

    # /api/buildings/{id}
    if len(segments) == 1:
        if method == "PUT":
            return building_controller.update_building(event, building_id)
        if method == "DELETE":
            return building_controller.delete_building(event, building_id)
        return method_not_allowed(method)

    return not_found()


def handler(event=None, context=None):
    """Lambda entry point."""
    try:
        return route(event or {})
    except HttpError as error:
        return error.to_response()
    except Exception as error:
        logger.exception("Unhandled error in buildings service: %s", error)
        return json_response(500, {"error": "Internal server error"})
