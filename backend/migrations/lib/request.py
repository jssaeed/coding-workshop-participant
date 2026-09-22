# Copied from backend/_shared/request.py by bin/sync-shared.sh - do not edit.
"""
Reading the incoming request, shared by every service.

Lambda gives the request as a dict called "event". These helpers pull out the
parts a service needs: the HTTP method, the path, the query string, the
headers and the JSON body.
"""

import base64
import json

from .responses import HttpError


def http_method(event):
    """Return the HTTP method in upper case, e.g. "GET" or "POST"."""
    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})
    return http.get("method", "GET").upper()


def path_segments(event, service_name):
    """
    Split the path into parts, without the "/api/<service>" prefix.

    For the incidents service:
        /api/incidents/12/status  ->  ["12", "status"]
        /api/incidents            ->  []
    """
    path = event.get("rawPath") or "/"
    parts = [part for part in path.split("/") if part != ""]

    if parts and parts[0] == "api":
        parts = parts[1:]
    if parts and parts[0] == service_name:
        parts = parts[1:]
    return parts


def path_id(segments, index=0):
    """
    Read a record id from the path, e.g. the "12" in /api/incidents/12.

    Anything that is not a positive whole number gets a 404, because it can
    never match a record.
    """
    try:
        value = int(segments[index])
    except (IndexError, ValueError):
        raise HttpError(404, "Resource not found")

    if value < 1:
        raise HttpError(404, "Resource not found")
    return value


def query_params(event):
    """Return the query string as a dict, e.g. {"status": "open"}."""
    return event.get("queryStringParameters") or {}


def headers(event):
    """Return the request headers with lower-case names."""
    result = {}
    for name, value in (event.get("headers") or {}).items():
        result[name.lower()] = value
    return result


def json_body(event):
    """
    Parse the request body as JSON and return it as a dict.

    An empty body gives {}. A body that is not a JSON object gives a 400.
    """
    body = event.get("body")
    if not body:
        return {}

    # Lambda sometimes delivers the body base64-encoded.
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        data = json.loads(body)
    except ValueError:
        raise HttpError(400, "Request body must be valid JSON")

    if not isinstance(data, dict):
        raise HttpError(400, "Request body must be a JSON object")
    return data
