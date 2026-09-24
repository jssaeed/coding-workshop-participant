"""
Unit tests for function.py: routing, method checks, and the two safety nets
(HttpError -> its status, anything else -> a plain 500). No database.
"""

import pytest

from _testing.events import call
from controllers import user_controller
from function import handler

PROTECTED = [
    ("GET", "/api/users"),
    ("GET", "/api/users/me"),
    ("PUT", "/api/users/5/role"),
    ("DELETE", "/api/users/5"),
]

WRONG_METHOD = [
    ("PUT", "/api/users"),
    ("DELETE", "/api/users"),
    ("GET", "/api/users/login"),
    ("GET", "/api/users/refresh"),
    ("GET", "/api/users/logout"),
    ("POST", "/api/users/me"),
    ("POST", "/api/users/branches"),
    ("GET", "/api/users/5"),
    ("PUT", "/api/users/5"),
    ("POST", "/api/users/5/role"),
    ("GET", "/api/users/5/role"),
]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_protected_routes_require_a_token(no_database, method, path):
    status, data = call(handler, method, path)
    assert status == 401
    assert data == {"error": "Authentication required"}


@pytest.mark.parametrize("method, path", WRONG_METHOD)
def test_wrong_method_is_405(no_database, method, path):
    status, data = call(handler, method, path, token="x")
    assert status == 405
    assert data == {"error": f"Method {method} not allowed"}


@pytest.mark.parametrize("path", ["/api/users/abc", "/api/users/0", "/api/users/-1", "/api/users/5/unknown", "/api/users/5/role/x"])
def test_unknown_paths_are_404(no_database, path):
    status, data = call(handler, "GET", path, token="x")
    assert status == 404
    assert "error" in data


def test_unexpected_errors_become_a_generic_500(no_database, monkeypatch):
    def explode(event):
        raise RuntimeError("database on fire")

    monkeypatch.setattr(user_controller, "list_branches", explode)
    status, data = call(handler, "GET", "/api/users/branches")
    assert status == 500
    assert data == {"error": "Internal server error"}  # no details leak to the client


def test_handler_tolerates_a_missing_event(no_database):
    response = handler()
    assert response["statusCode"] == 401  # routed as GET /api/users, no token
