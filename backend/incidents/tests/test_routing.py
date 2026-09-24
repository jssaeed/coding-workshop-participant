"""Unit tests for function.py: routing and the error safety nets. No database."""

import pytest

from _testing.events import call
from controllers import incident_controller
from function import handler

PROTECTED = [
    ("POST", "/api/incidents"), ("GET", "/api/incidents"), ("GET", "/api/incidents/1"),
    ("PUT", "/api/incidents/1/assign"), ("PUT", "/api/incidents/1/status"), ("PUT", "/api/incidents/1/approval"),
    ("PUT", "/api/incidents/1/priority"), ("PUT", "/api/incidents/1/location"),
    ("GET", "/api/incidents/stats/overview"), ("GET", "/api/incidents/stats/locations"), ("GET", "/api/incidents/stats/mine"),
]
WRONG_METHOD = [
    ("PUT", "/api/incidents"), ("DELETE", "/api/incidents"), ("POST", "/api/incidents/1"), ("DELETE", "/api/incidents/1"),
    ("GET", "/api/incidents/1/assign"), ("POST", "/api/incidents/1/status"), ("GET", "/api/incidents/1/approval"),
    ("DELETE", "/api/incidents/1/priority"), ("POST", "/api/incidents/1/location"),
    ("POST", "/api/incidents/stats/overview"), ("PUT", "/api/incidents/stats/mine"),
]
NOT_FOUND = ["/api/incidents/abc", "/api/incidents/0", "/api/incidents/1/unknown", "/api/incidents/1/status/x",
             "/api/incidents/stats", "/api/incidents/stats/unknown", "/api/incidents/stats/overview/extra"]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_route_requires_a_token(no_database, method, path):
    status, data = call(handler, method, path)
    assert (status, data) == (401, {"error": "Authentication required"})


@pytest.mark.parametrize("method, path", WRONG_METHOD)
def test_wrong_method_is_405(no_database, method, path):
    status, data = call(handler, method, path, token="x")
    assert (status, data) == (405, {"error": f"Method {method} not allowed"})


@pytest.mark.parametrize("path", NOT_FOUND)
def test_unknown_paths_are_404(no_database, path):
    status, data = call(handler, "GET", path, token="x")
    assert status == 404
    assert "error" in data


def test_unexpected_errors_become_a_generic_500(no_database, monkeypatch):
    monkeypatch.setattr(incident_controller, "list_incidents", lambda event: {}["missing"])
    status, data = call(handler, "GET", "/api/incidents", token="x")
    assert (status, data) == (500, {"error": "Internal server error"})
