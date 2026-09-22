"""
HTTP response shaping shared by every service.

Keeps status codes and the error body in one place so all services answer in
the same shape.
"""

import json
from datetime import date, datetime
from decimal import Decimal

class HttpError(Exception):
    """
    An error that maps to a specific HTTP status code.

    Controllers raise it; the service handler turns it into a response.
    """

    def __init__(self, status_code, message, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details

    def to_response(self):
        """Render the error as an HTTP response."""
        payload = {"error": self.message}
        if self.details:
            payload["details"] = self.details
        return json_response(self.status_code, payload)

def _encode(value):
    """Serialize types psycopg returns that json does not handle."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")

def json_response(status_code, payload=None):
    """Build a Lambda HTTP response with a JSON body."""
    response = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
    }
    if payload is not None:
        response["body"] = json.dumps(payload, default=_encode)
    return response

def ok(payload):
    """200 - successful retrieval or update."""
    return json_response(200, payload)

def created(payload):
    """201 - successful creation."""
    return json_response(201, payload)

def no_content():
    """204 - successful deletion, no body."""
    return {"statusCode": 204, "headers": {"Content-Type": "application/json"}}

def method_not_allowed(method):
    """405 - the route exists but not for this verb."""
    return HttpError(405, f"Method {method} not allowed").to_response()

def not_found(message="Resource not found"):
    """404 - no such route or record."""
    return HttpError(404, message).to_response()
