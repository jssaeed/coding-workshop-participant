"""Unit tests for controllers/message_controller.py without a database."""

import pytest

from _testing.events import call
from _testing.fakes import sign_in_as, stub
from function import handler
from models import incident as incident_model
from models import message as message_model
from views import message_view

INCIDENT = {"id": 12, "status": "open", "branch_id": 1, "reported_by": 4, "assigned_to": 7}


@pytest.fixture
def models(monkeypatch, no_database):
    return {
        "incident": stub(monkeypatch, incident_model, "find_basic", dict(INCIDENT)),
        "create": stub(monkeypatch, message_model, "create", {"id": 31, "incident_id": 12, "message": "Hi", "created_at": None, "updated_at": None,
                                                              "user_id": 4, "author_name": "Ana", "author_email": "ana@acme.inc", "author_role": "employee"}),
        "list": stub(monkeypatch, message_model, "list_for_incident", ([], False)),
        "count": stub(monkeypatch, message_model, "count_for_incident", 0),
    }


class TestCreate:
    @pytest.mark.parametrize("body, message", [
        ({"message": "Hi"}, "'incidentId' is required"),
        ({"incidentId": "12", "message": "Hi"}, "'incidentId' must be a positive whole number"),
        ({"incidentId": 12}, "'message' is required"),
        ({"incidentId": 12, "message": "   "}, "'message' is required"),
        ({"incidentId": 12, "message": "x" * 5001}, "'message' must be 5000 characters or fewer"),
    ])
    def test_validation(self, models, monkeypatch, body, message):
        sign_in_as(monkeypatch, "employee", user_id=4)
        status, data = call(handler, "POST", "/api/messages", body=body)
        assert (status, data) == (400, {"error": message})
        assert models["create"].calls == []

    @pytest.mark.parametrize("role, user_id, expected", [
        ("employee", 4, 201), ("engineer", 7, 201), ("facility_admin", 1, 201),
        ("employee", 5, 404), ("engineer", 8, 404), ("db_admin", 9, 404),
    ])
    def test_only_participants_may_post(self, models, monkeypatch, role, user_id, expected):
        sign_in_as(monkeypatch, role, user_id=user_id)
        status, _ = call(handler, "POST", "/api/messages", body={"incidentId": 12, "message": " Hi "})
        assert status == expected
        if expected == 201:
            assert models["create"].calls[0][0] == (12, user_id, "Hi")
            assert models["incident"].calls[0][1] == {"lock": True}

    def test_admin_at_another_branch_is_an_outsider(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1, branch_id=2)  # the ticket is at branch 1
        assert call(handler, "POST", "/api/messages", body={"incidentId": 12, "message": "Hi"})[0] == 404
        assert call(handler, "GET", "/api/messages", query={"incidentId": "12"})[0] == 404
        assert models["create"].calls == []

    def test_closed_ticket_is_409(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=4)
        stub(monkeypatch, incident_model, "find_basic", {**INCIDENT, "status": "closed"})
        status, data = call(handler, "POST", "/api/messages", body={"incidentId": 12, "message": "Hi"})
        assert (status, data) == (409, {"error": "Incident is closed and cannot receive new messages"})

    def test_unknown_ticket_is_404(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, incident_model, "find_basic", None)
        status, data = call(handler, "POST", "/api/messages", body={"incidentId": 12, "message": "Hi"})
        assert (status, data) == (404, {"error": "Incident not found"})


class TestList:
    @pytest.mark.parametrize("query, message", [
        ({}, "'incidentId' query parameter is required"),
        ({"incidentId": "abc"}, "'incidentId' must be a positive whole number"),
        ({"incidentId": "0"}, "'incidentId' must be a positive whole number"),
    ])
    def test_validation(self, models, monkeypatch, query, message):
        sign_in_as(monkeypatch, "employee", user_id=4)
        status, data = call(handler, "GET", "/api/messages", query=query)
        assert (status, data) == (400, {"error": message})

    def test_outsider_gets_404(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=5)
        status, _ = call(handler, "GET", "/api/messages", query={"incidentId": "12"})
        assert status == 404

    def test_participant_gets_the_thread(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        status, data = call(handler, "GET", "/api/messages", query={"incidentId": "12"})
        assert (status, data) == (200, {"items": [], "total": 0, "hasMore": False})
        assert models["list"].calls[0] == ((12,), {"limit": 50, "before_id": None})
        assert models["count"].calls[0][0] == (12,)

    def test_limit_and_before_reach_the_model(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        stub(monkeypatch, message_model, "count_for_incident", 9)
        stub(monkeypatch, message_model, "list_for_incident", ([], True))
        status, data = call(handler, "GET", "/api/messages", query={"incidentId": "12", "limit": "2", "before": "31"})
        assert (status, data) == (200, {"items": [], "total": 9, "hasMore": True})
        assert message_model.list_for_incident.calls[0] == ((12,), {"limit": 2, "before_id": 31})

    @pytest.mark.parametrize("query, message", [
        ({"incidentId": "12", "limit": "0"}, "'limit' must be between 1 and 200"),
        ({"incidentId": "12", "limit": "201"}, "'limit' must be between 1 and 200"),
        ({"incidentId": "12", "before": "0"}, f"'before' must be between 1 and {10**18}"),
        ({"incidentId": "12", "before": "abc"}, f"'before' must be between 1 and {10**18}"),
    ])
    def test_bad_paging(self, models, monkeypatch, query, message):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        status, data = call(handler, "GET", "/api/messages", query=query)
        assert (status, data) == (400, {"error": message})


class TestView:
    def test_author_and_deleted_author(self):
        row = {"id": 1, "incident_id": 12, "message": "Hi", "created_at": None, "updated_at": None,
               "user_id": 7, "author_name": "Bob", "author_email": "bob@acme.inc", "author_role": "engineer"}
        assert message_view.serialize(row) == {"id": 1, "incidentId": 12, "message": "Hi", "createdAt": None, "updatedAt": None,
                                               "author": {"id": 7, "name": "Bob", "email": "bob@acme.inc", "role": "engineer"}}
        assert message_view.serialize({**row, "user_id": None})["author"] is None
