"""lib/responses.py: the shape of every Lambda response."""

import json
from datetime import date, datetime, timezone

import pytest

from lib.responses import (HttpError, created, json_response, method_not_allowed, no_content,
                           not_found, ok)


def test_json_response_has_status_headers_and_body():
    response = json_response(200, {"a": 1})
    assert response["statusCode"] == 200
    assert response["headers"] == {"Content-Type": "application/json"}
    assert json.loads(response["body"]) == {"a": 1}


def test_json_response_without_payload_has_no_body():
    assert "body" not in json_response(204)


def test_dates_are_written_as_iso_8601():
    when = datetime(2026, 9, 22, 14, 3, 11, tzinfo=timezone.utc)
    body = json.loads(json_response(200, {"at": when, "day": date(2026, 9, 22)})["body"])
    assert body == {"at": "2026-09-22T14:03:11+00:00", "day": "2026-09-22"}


def test_unknown_types_cannot_be_serialized():
    with pytest.raises(TypeError):
        json_response(200, {"x": object()})


def test_http_error_becomes_a_consistent_error_body():
    error = HttpError(404, "Incident not found")
    assert str(error) == "Incident not found"
    response = error.to_response()
    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {"error": "Incident not found"}


@pytest.mark.parametrize("build, status, body", [
    (lambda: ok({"id": 1}), 200, {"id": 1}),
    (lambda: created({"id": 1}), 201, {"id": 1}),
    (lambda: not_found(), 404, {"error": "Resource not found"}),
    (lambda: not_found("Nope"), 404, {"error": "Nope"}),
    (lambda: method_not_allowed("PATCH"), 405, {"error": "Method PATCH not allowed"}),
])
def test_helpers(build, status, body):
    response = build()
    assert response["statusCode"] == status
    assert json.loads(response["body"]) == body


def test_no_content_has_no_body():
    response = no_content()
    assert response["statusCode"] == 204
    assert "body" not in response
