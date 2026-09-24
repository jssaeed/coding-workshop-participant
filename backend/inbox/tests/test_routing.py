"""Unit tests for function.py: routing and the error safety nets. No database."""

import pytest

from _testing.events import call
from controllers import inbox_controller
from function import handler

PROTECTED = [("GET", "/api/inbox"), ("GET", "/api/inbox/count"), ("PUT", "/api/inbox/read-all"), ("PUT", "/api/inbox/12/read")]
WRONG_METHOD = [("POST", "/api/inbox"), ("PUT", "/api/inbox/count"), ("GET", "/api/inbox/read-all"), ("GET", "/api/inbox/12/read"), ("DELETE", "/api/inbox/12/read")]


@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_route_requires_a_token(no_database, method, path):
    status, data = call(handler, method, path)
    assert (status, data) == (401, {"error": "Authentication required"})


@pytest.mark.parametrize("method, path", WRONG_METHOD)
def test_wrong_method_is_405(no_database, method, path):
    status, data = call(handler, method, path, token="x")
    assert (status, data) == (405, {"error": f"Method {method} not allowed"})


@pytest.mark.parametrize("path", ["/api/inbox/abc", "/api/inbox/0/read", "/api/inbox/12", "/api/inbox/12/unread", "/api/inbox/12/read/x"])
def test_unknown_paths_are_404(no_database, path):
    status, _ = call(handler, "PUT", path, token="x")
    assert status == 404


def test_unexpected_errors_become_a_generic_500(no_database, monkeypatch):
    monkeypatch.setattr(inbox_controller, "count", lambda event: None.missing)
    status, data = call(handler, "GET", "/api/inbox/count", token="x")
    assert (status, data) == (500, {"error": "Internal server error"})
