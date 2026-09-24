"""Unit tests for function.py: routing and the error safety nets. No database."""

import pytest

from _testing.events import call
from controllers import building_controller
from function import handler

PROTECTED = [("GET", "/api/buildings"), ("POST", "/api/buildings"), ("PUT", "/api/buildings/1"), ("DELETE", "/api/buildings/1")]
WRONG_METHOD = [("PUT", "/api/buildings"), ("DELETE", "/api/buildings"), ("GET", "/api/buildings/1"), ("POST", "/api/buildings/1")]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_route_requires_a_token(no_database, method, path):
    status, data = call(handler, method, path)
    assert (status, data) == (401, {"error": "Authentication required"})


@pytest.mark.parametrize("method, path", WRONG_METHOD)
def test_wrong_method_is_405(no_database, method, path):
    status, data = call(handler, method, path, token="x")
    assert (status, data) == (405, {"error": f"Method {method} not allowed"})


@pytest.mark.parametrize("path", ["/api/buildings/abc", "/api/buildings/0", "/api/buildings/1/floors"])
def test_unknown_paths_are_404(no_database, path):
    status, _ = call(handler, "PUT", path, token="x")
    assert status == 404


def test_unexpected_errors_become_a_generic_500(no_database, monkeypatch):
    monkeypatch.setattr(building_controller, "list_buildings", lambda event: 1 / 0)
    status, data = call(handler, "GET", "/api/buildings", token="x")
    assert (status, data) == (500, {"error": "Internal server error"})
