"""Unit tests for function.py: routing and the error safety nets. No database."""

import pytest

from _testing.events import call
from controllers import message_controller
from function import handler


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_routes_require_a_token(no_database, method):
    status, data = call(handler, method, "/api/messages")
    assert (status, data) == (401, {"error": "Authentication required"})


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_wrong_method_is_405(no_database, method):
    status, data = call(handler, method, "/api/messages", token="x")
    assert (status, data) == (405, {"error": f"Method {method} not allowed"})


@pytest.mark.parametrize("path", ["/api/messages/1", "/api/messages/thread", "/api/messages/1/x"])
def test_sub_paths_are_404(no_database, path):
    status, _ = call(handler, "GET", path, token="x")
    assert status == 404


def test_unexpected_errors_become_a_generic_500(no_database, monkeypatch):
    monkeypatch.setattr(message_controller, "list_messages", lambda event: [][0])
    status, data = call(handler, "GET", "/api/messages", token="x")
    assert (status, data) == (500, {"error": "Internal server error"})
