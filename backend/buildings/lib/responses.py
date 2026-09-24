# Copied from backend/_shared/responses.py by bin/sync-shared.sh - do not edit.
"""
Building HTTP responses, shared by every service.

Lambda expects a dict with statusCode, headers and body. These helpers build
that dict so every service answers in the same shape, and errors always look
like {"error": "message"}.
"""

import json
from datetime import date, datetime


class HttpError(Exception):
    """
    An error with an HTTP status code.

    Controllers raise this (for example HttpError(404, "Incident not found"))
    and the service's handler turns it into the matching response.
    """

    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def to_response(self):
        return json_response(self.status_code, {"error": self.message})


def _json_default(value):
    """Tell json.dumps how to write dates: as ISO-8601 strings."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Cannot convert {type(value).__name__} to JSON")


def json_response(status_code, payload=None):
    """Build a Lambda response with a JSON body."""
    response = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
    }
    if payload is not None:
        response["body"] = json.dumps(payload, default=_json_default)
    return response


def ok(payload):
    """200: success, with data."""
    return json_response(200, payload)


def created(payload):
    """201: something new was saved."""
    return json_response(201, payload)


def paged(items, total, page, limit):
    """
    200: one page of a list.

        {"items": [...], "total": 42, "page": 2, "limit": 25, "pages": 2}

    total is how many rows match in all, pages how many pages that makes
    (at least 1, so "page 1 of 1" reads right for an empty list).
    """
    return json_response(200, {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, -(-total // limit)),  # ceiling division
    })


def no_content():
    """204: success, nothing to return (used after a delete)."""
    return json_response(204)


def not_found(message="Resource not found"):
    """404: no such route or record."""
    return json_response(404, {"error": message})


def method_not_allowed(method):
    """405: the route exists but not for this HTTP method."""
    return json_response(405, {"error": f"Method {method} not allowed"})
