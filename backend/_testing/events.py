"""
Building Lambda events and reading Lambda responses in tests.

A service handler takes the event dict that API Gateway (HTTP API, payload
v2) sends to a Lambda and returns {"statusCode", "headers", "body"}. These
helpers build the former and unpack the latter, so a test reads like:

    status, data = call(handler, "POST", "/api/users", body={...})
    assert status == 201
"""

import base64
import json


def event(method="GET", path="/", body=None, query=None, token=None, headers=None,
          raw_body=None, base64_body=False):
    """
    Build an API Gateway v2 event.

    body      a dict, sent as JSON
    raw_body  a string sent exactly as given (for malformed-JSON tests)
    query     a dict for the query string
    token     an access token, sent as "Authorization: Bearer <token>"
    """
    result = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": {},
    }
    if query:
        result["queryStringParameters"] = query
    if token:
        result["headers"]["Authorization"] = f"Bearer {token}"
    if headers:
        result["headers"].update(headers)

    text = raw_body if raw_body is not None else (json.dumps(body) if body is not None else None)
    if text is not None:
        if base64_body:
            result["body"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
            result["isBase64Encoded"] = True
        else:
            result["body"] = text
    return result


def parse(response):
    """(status code, decoded JSON body or None) from a Lambda response."""
    assert isinstance(response, dict), f"handler returned {type(response).__name__}, not a dict"
    assert "statusCode" in response
    body = response.get("body")
    return response["statusCode"], (json.loads(body) if body is not None else None)


def call(handler, method="GET", path="/", **kwargs):
    """Send one request to a handler and return (status, payload)."""
    return parse(handler(event(method, path, **kwargs), None))
