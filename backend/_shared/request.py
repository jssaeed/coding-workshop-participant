"""
Reading the incoming request, shared by every service.

Lambda gives the request as a dict called "event". These helpers pull out the
parts a service needs: the HTTP method, the path, the query string, the
headers and the JSON body.
"""

import base64
import json
import re

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


# --- pagination -------------------------------------------------------------
#
# Lists are never sent whole. Every list endpoint takes ?page=N&limit=M and
# answers with one page plus the total, so a table can show page numbers
# (see responses.paged). The database does the limiting (LIMIT/OFFSET), so
# a page costs the same however large the table grows.

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def int_param(params, name, minimum, maximum, default=None):
    """
    A whole-number query parameter between minimum and maximum, or default
    when it is absent. Anything else is a 400 that names the parameter.
    """
    value = params.get(name)
    if value is None or value == "":
        return default
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+", value) or not minimum <= int(value) <= maximum:
        raise HttpError(400, f"'{name}' must be between {minimum} and {maximum}")
    return int(value)


def positive_int_param(params, name):
    """
    An optional ?name=N query parameter that must be a positive whole number
    (an id, say), or None when it is absent or empty. Anything else is a 400
    that names the parameter.
    """
    value = params.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.isdigit() or int(value) < 1:
        raise HttpError(400, f"'{name}' must be a positive whole number")
    return int(value)


def page_params(params, default_limit=DEFAULT_PAGE_SIZE, max_limit=MAX_PAGE_SIZE):
    """
    Read ?page= and ?limit= from the query string.

    Returns (page, limit, offset): the 1-based page number, how many rows it
    holds, and how many rows to skip to reach it. Missing values mean the
    first page of default_limit rows.
    """
    page = int_param(params, "page", 1, 1_000_000, default=1)
    limit = int_param(params, "limit", 1, max_limit, default=default_limit)
    return page, limit, (page - 1) * limit


def choice_param(params, name, allowed, default=None):
    """A query parameter that must be one of the allowed values."""
    value = params.get(name)
    if value is None or value == "":
        return default
    if value not in allowed:
        raise HttpError(400, f"'{name}' must be one of: {', '.join(allowed)}")
    return value


def text_param(params, name, max_length=100):
    """A free-text query parameter, trimmed; '' and absent both give None."""
    value = params.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HttpError(400, f"'{name}' must be text")
    value = value.strip()
    if value == "":
        return None
    if len(value) > max_length:
        raise HttpError(400, f"'{name}' must be {max_length} characters or fewer")
    return value


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
