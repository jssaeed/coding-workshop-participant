"""
Users service: accounts, login and role management.

    POST   /api/users            create an employee account (public)
    POST   /api/users/login      log in, returns an access token
    GET    /api/users/me         the signed-in user
    GET    /api/users            list accounts (admin)
    GET    /api/users/{id}       one account (admin)
    PUT    /api/users/{id}/role  promote or demote (admin)
    DELETE /api/users/{id}       delete an account (admin)
"""

import logging

from controllers import user_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "users"

def route(event):
    """Dispatch a request to the controller that handles it."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/users
    if not segments:
        if method == "POST":
            return user_controller.create_account(event)
        if method == "GET":
            return user_controller.list_users(event)
        return method_not_allowed(method)

    # /api/users/login
    if segments[0] == "login":
        if method == "POST":
            return user_controller.login(event)
        return method_not_allowed(method)

    # /api/users/me
    if segments[0] == "me":
        if method == "GET":
            return user_controller.me(event)
        return method_not_allowed(method)

    user_id = path_id(segments)

    # /api/users/{id}/role
    if len(segments) > 1 and segments[1] == "role":
        if method == "PUT":
            return user_controller.update_role(event, user_id)
        return method_not_allowed(method)

    # /api/users/{id}
    if len(segments) == 1:
        if method == "DELETE":
            return user_controller.delete_user(event, user_id)
        return method_not_allowed(method)

    return not_found()

def handler(event=None, context=None):
    """
    Lambda entry point for the users service.

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
        # Expected failures: validation, auth, missing records.
        logger.info("Request rejected (%s): %s", error.status_code, error.message)
        return error.to_response()
    except Exception as e:
        # Unexpected failures: log the detail, return a generic message so
        # internals are not exposed to clients.
        logger.exception("Unhandled error in users service: %s", e)
        return json_response(500, {"error": "Internal server error"})
