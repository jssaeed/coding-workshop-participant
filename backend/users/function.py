"""
Users service: accounts, login and roles.

    POST   /api/users            sign up (always creates an employee)
    POST   /api/users/login      log in, returns access + refresh tokens
    POST   /api/users/refresh    swap a refresh token for new tokens
    POST   /api/users/logout     revoke a refresh token
    GET    /api/users/me         the signed-in user
    GET    /api/users            list accounts (admin)
    PUT    /api/users/{id}/role  change a role (admin)
    DELETE /api/users/{id}       delete an account (admin)

This file only decides which controller function handles the request. The
rules live in controllers/, the SQL in models/, the JSON shape in views/.
"""

import logging

from controllers import user_controller
from lib.request import http_method, path_id, path_segments
from lib.responses import HttpError, json_response, method_not_allowed, not_found

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "users"


def route(event):
    """Pick the controller function for this method and path."""
    method = http_method(event)
    segments = path_segments(event, SERVICE_NAME)

    # /api/users
    if len(segments) == 0:
        if method == "POST":
            return user_controller.create_account(event)
        if method == "GET":
            return user_controller.list_users(event)
        return method_not_allowed(method)

    # /api/users/branches (public: the signup form needs it before login)
    if segments == ["branches"]:
        if method == "GET":
            return user_controller.list_branches(event)
        return method_not_allowed(method)

    # /api/users/login
    if segments == ["login"]:
        if method == "POST":
            return user_controller.login(event)
        return method_not_allowed(method)

    # /api/users/refresh
    if segments == ["refresh"]:
        if method == "POST":
            return user_controller.refresh(event)
        return method_not_allowed(method)

    # /api/users/logout
    if segments == ["logout"]:
        if method == "POST":
            return user_controller.logout(event)
        return method_not_allowed(method)

    # /api/users/me
    if segments == ["me"]:
        if method == "GET":
            return user_controller.me(event)
        return method_not_allowed(method)

    user_id = path_id(segments)

    # /api/users/{id}
    if len(segments) == 1:
        if method == "DELETE":
            return user_controller.delete_user(event, user_id)
        return method_not_allowed(method)

    # /api/users/{id}/role
    if len(segments) == 2 and segments[1] == "role":
        if method == "PUT":
            return user_controller.update_role(event, user_id)
        return method_not_allowed(method)

    return not_found()


def handler(event=None, context=None):
    """Lambda entry point."""
    try:
        return route(event or {})
    except HttpError as error:
        # Expected problems: bad input, not logged in, no such record.
        return error.to_response()
    except Exception as error:
        # Anything else is a bug or an outage. Log the details, but do not
        # send them to the client.
        logger.exception("Unhandled error in users service: %s", error)
        return json_response(500, {"error": "Internal server error"})
