"""
Unit tests for the incidents controllers and views without a database:
input validation, who may call what, and the JSON shapes.
"""

from datetime import datetime, timezone

import pytest

from _testing.events import call
from _testing.fakes import sign_in_as, stub
from function import handler
from models import building as building_model
from models import incident as incident_model
from models import location as location_model
from models import user as user_model
from views import incident_view, stats_view

NOW = datetime(2026, 9, 22, 14, 3, 11, tzinfo=timezone.utc)
BUILDING = {"id": 2, "branch_id": 1, "name": "HQ", "floors": 3, "basement_floors": 1,
            "room_numbers_include_floor": True, "max_rooms": 10}


def ticket_row(**overrides):
    row = {
        "id": 12, "title": "Leaking pipe", "description": "", "status": "open", "priority": 3,
        "created_at": NOW, "updated_at": NOW, "resolved_at": None,
        "location_id": None, "floor": None, "room": None, "building_id": None, "building_name": None,
        "room_numbers_include_floor": None, "max_rooms": None,
        "reported_by": 4, "reporter_name": "Ana", "reporter_email": "ana@acme.inc",
        "assigned_to": None, "assignee_name": None, "assignee_email": None,
        "pending_status": None, "pending_requested_by": None, "pending_requested_at": None,
        "pending_note": None, "pending_requester_name": None,
    }
    row.update(overrides)
    return row


def basic(**overrides):
    row = {"id": 12, "status": "open", "priority": 3, "location_id": None, "reported_by": 4,
           "assigned_to": None, "pending_status": None, "pending_requested_by": None}
    row.update(overrides)
    return row


@pytest.fixture
def models(monkeypatch, no_database):
    return {
        "building": stub(monkeypatch, building_model, "find_by_id", dict(BUILDING)),
        "rooms": stub(monkeypatch, building_model, "rooms_on_floor", 10),
        "location": stub(monkeypatch, location_model, "find_or_create", {"id": 77}),
        "create": stub(monkeypatch, incident_model, "create", ticket_row()),
        "find_basic": stub(monkeypatch, incident_model, "find_basic", basic()),
        "find_by_id": stub(monkeypatch, incident_model, "find_by_id", ticket_row()),
        "search": stub(monkeypatch, incident_model, "search", []),
        "unassigned": stub(monkeypatch, incident_model, "list_unassigned", []),
        "assign": stub(monkeypatch, incident_model, "assign", ticket_row()),
        "update_status": stub(monkeypatch, incident_model, "update_status", ticket_row()),
        "request_status": stub(monkeypatch, incident_model, "request_status", ticket_row()),
        "clear_request": stub(monkeypatch, incident_model, "clear_request", ticket_row()),
        "update_priority": stub(monkeypatch, incident_model, "update_priority", ticket_row()),
        "update_location": stub(monkeypatch, incident_model, "update_location", ticket_row()),
        "user": stub(monkeypatch, user_model, "find_by_id", {"id": 7, "name": "Bob", "email": "bob@acme.inc", "role": "engineer"}),
    }


class TestCreateValidation:
    @pytest.mark.parametrize("body, message", [
        ({}, "'title' is required"),
        ({"title": "   "}, "'title' is required"),
        ({"title": "x" * 256}, "'title' must be 255 characters or fewer"),
        ({"title": "Leak", "description": "x" * 5001}, "'description' must be 5000 characters or fewer"),
        ({"title": "Leak", "priority": 0}, "'priority' must be between 1 and 5"),
        ({"title": "Leak", "priority": 6}, "'priority' must be between 1 and 5"),
        ({"title": "Leak", "priority": "2"}, "'priority' must be a whole number"),
        ({"title": "Leak", "location": "HQ"}, "'location' must be an object"),
        ({"title": "Leak", "location": {}}, "'buildingId' is required"),
        ({"title": "Leak", "location": {"buildingId": 2}}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"title": "Leak", "location": {"buildingId": 2, "floor": 0}}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"title": "Leak", "location": {"buildingId": 2, "floor": 4}}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"title": "Leak", "location": {"buildingId": 2, "floor": -2}}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"title": "Leak", "location": {"buildingId": 2, "floor": "3"}}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"title": "Leak", "location": {"buildingId": 2, "floor": 3, "room": "12"}}, "'room' must be a positive whole number"),
        ({"title": "Leak", "location": {"buildingId": 2, "floor": 3, "room": 11}}, "'room' must be between 1 and 10 on floor 3"),
    ])
    def test_bad_input_is_400_and_saves_nothing(self, models, monkeypatch, body, message):
        sign_in_as(monkeypatch, "employee")
        status, data = call(handler, "POST", "/api/incidents", body=body)
        assert (status, data) == (400, {"error": message})
        assert models["create"].calls == []
        assert models["location"].calls == []

    def test_unknown_building(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee")
        stub(monkeypatch, building_model, "find_by_id", None)
        status, data = call(handler, "POST", "/api/incidents", body={"title": "Leak", "location": {"buildingId": 9, "floor": 1}})
        assert (status, data) == (400, {"error": "'buildingId' does not match a known building"})

    def test_building_at_another_branch(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", branch_id=2)
        status, data = call(handler, "POST", "/api/incidents", body={"title": "Leak", "location": {"buildingId": 2, "floor": 1}})
        assert (status, data) == (400, {"error": "'buildingId' is not a building at your branch"})

    def test_no_floor_zero_message_without_basements(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee")
        stub(monkeypatch, building_model, "find_by_id", {**BUILDING, "basement_floors": 0})
        status, data = call(handler, "POST", "/api/incidents", body={"title": "Leak", "location": {"buildingId": 2, "floor": 0}})
        assert data == {"error": "'floor' must be between 1 and 3 (there is no floor 0)"}

    def test_defaults_and_reporter(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=4)
        status, data = call(handler, "POST", "/api/incidents", body={"title": " Leak "})
        assert status == 201
        assert models["create"].calls[0][0] == ("Leak", "", 3, None, 4)
        assert data["status"] == "open"

    def test_room_on_a_floor_without_a_count_is_accepted(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=4)
        stub(monkeypatch, building_model, "rooms_on_floor", 0)
        status, _ = call(handler, "POST", "/api/incidents", body={"title": "Leak", "location": {"buildingId": 2, "floor": -1, "room": 900}})
        assert status == 201
        assert models["location"].calls[0][0] == (2, -1, 900)
        assert models["create"].calls[0][0][3] == 77

    def test_create_is_one_transaction(self, models, monkeypatch, no_database):
        sign_in_as(monkeypatch, "employee")
        call(handler, "POST", "/api/incidents", body={"title": "Leak", "location": {"buildingId": 2, "floor": 1}})
        assert no_database.commits == 1
        # the building was locked while the ticket was checked against it
        assert models["building"].calls[0][1] == {"lock": True}


class TestListValidation:
    @pytest.mark.parametrize("query, message", [
        ({"scope": "everything"}, "'scope' must be one of: mine, assigned, unassigned, pending, all"),
        ({"status": "done"}, "'status' must be one of: open, assigned, in_progress, blocked, resolved, closed"),
        ({"priority": "0"}, "'priority' must be between 1 and 5"),
        ({"priority": "high"}, "'priority' must be between 1 and 5"),
    ])
    def test_bad_query(self, models, monkeypatch, query, message):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "GET", "/api/incidents", query=query)
        assert (status, data) == (400, {"error": message})

    @pytest.mark.parametrize("role, scope", [
        ("employee", "assigned"), ("employee", "unassigned"), ("employee", "pending"), ("employee", "all"),
        ("engineer", "unassigned"), ("engineer", "pending"), ("engineer", "all"),
        ("db_admin", "assigned"), ("db_admin", "all"),
    ])
    def test_scopes_a_role_may_not_use(self, models, monkeypatch, role, scope):
        sign_in_as(monkeypatch, role)
        status, data = call(handler, "GET", "/api/incidents", query={"scope": scope})
        assert (status, data) == (403, {"error": "Access denied"})

    def test_default_scope_is_mine_with_filters(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=4)
        status, data = call(handler, "GET", "/api/incidents", query={"status": "open", "priority": "2"})
        assert (status, data) == (200, [])
        assert models["search"].calls[0][1] == {"reported_by": 4, "status": "open", "priority": 2}

    def test_pending_scope(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        call(handler, "GET", "/api/incidents", query={"scope": "pending"})
        assert models["search"].calls[0][1] == {"status": None, "priority": None, "pending": True}


class TestVisibility:
    @pytest.mark.parametrize("role, user_id, expected", [
        ("employee", 4, 200),        # the reporter
        ("engineer", 7, 200),        # the assignee
        ("facility_admin", 1, 200),  # any admin
        ("employee", 5, 404),        # someone else: 404, not 403
        ("engineer", 8, 404),
        ("db_admin", 9, 404),        # the db admin is not facilities staff
    ])
    def test_get_incident(self, models, monkeypatch, role, user_id, expected):
        sign_in_as(monkeypatch, role, user_id=user_id)
        stub(monkeypatch, incident_model, "find_basic", basic(assigned_to=7))
        status, _ = call(handler, "GET", "/api/incidents/12")
        assert status == expected

    def test_unknown_ticket(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, incident_model, "find_basic", None)
        status, data = call(handler, "GET", "/api/incidents/12")
        assert (status, data) == (404, {"error": "Incident not found"})


class TestAssignRules:
    @pytest.mark.parametrize("role", ["employee", "engineer", "db_admin"])
    def test_admin_only(self, models, monkeypatch, role):
        sign_in_as(monkeypatch, role)
        status, _ = call(handler, "PUT", "/api/incidents/12/assign", body={"assigneeId": 7})
        assert status == 403

    @pytest.mark.parametrize("body, message", [
        ({}, "'assigneeId' is required (use null to unassign)"),
        ({"assigneeId": "7"}, "'assigneeId' must be a positive whole number"),
        ({"assigneeId": None}, "Incident already has that assignment"),  # already unassigned
    ])
    def test_bad_input(self, models, monkeypatch, body, message):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "PUT", "/api/incidents/12/assign", body=body)
        assert (status, data) == (400, {"error": message})
        assert models["assign"].calls == []

    def test_unknown_or_employee_assignee(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, user_model, "find_by_id", None)
        status, data = call(handler, "PUT", "/api/incidents/12/assign", body={"assigneeId": 99})
        assert (status, data) == (400, {"error": "'assigneeId' does not match a known user"})
        stub(monkeypatch, user_model, "find_by_id", {"id": 5, "name": "Cy", "email": "c@acme.inc", "role": "employee"})
        status, data = call(handler, "PUT", "/api/incidents/12/assign", body={"assigneeId": 5})
        assert (status, data) == (400, {"error": "Tickets can only be assigned to an engineer or admin"})

    @pytest.mark.parametrize("before, assignee, expected_status", [
        (basic(status="open"), 7, "assigned"),
        (basic(status="assigned", assigned_to=8), 7, "assigned"),
        (basic(status="in_progress", assigned_to=8), 7, "in_progress"),
        (basic(status="assigned", assigned_to=8), None, "open"),
        (basic(status="blocked", assigned_to=8), None, "blocked"),
    ])
    def test_status_follows_the_assignment(self, models, monkeypatch, before, assignee, expected_status):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, incident_model, "find_basic", before)
        status, _ = call(handler, "PUT", "/api/incidents/12/assign", body={"assigneeId": assignee})
        assert status == 200
        incident_id, assignee_id, new_status, author, note = models["assign"].calls[0][0]
        assert (incident_id, assignee_id, new_status, author) == (12, assignee, expected_status, 1)
        assert note == ("Ticket #12: unassigned" if assignee is None else "Ticket #12: assigned to Bob")

    def test_unknown_ticket(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, incident_model, "find_basic", None)
        status, _ = call(handler, "PUT", "/api/incidents/12/assign", body={"assigneeId": 7})
        assert status == 404


class TestStatusRules:
    def test_employee_may_not(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=4)
        status, _ = call(handler, "PUT", "/api/incidents/12/status", body={"status": "in_progress"})
        assert status == 403

    def test_engineer_must_be_the_assignee(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=8)
        stub(monkeypatch, incident_model, "find_basic", basic(status="assigned", assigned_to=7))
        status, data = call(handler, "PUT", "/api/incidents/12/status", body={"status": "in_progress"})
        assert (status, data) == (403, {"error": "Access denied"})

    @pytest.mark.parametrize("before, body, message", [
        (basic(), {}, "'status' is required"),
        (basic(), {"status": "done"}, "'status' must be one of: open, assigned, in_progress, blocked, resolved, closed"),
        (basic(), {"status": "in_progress", "note": "x" * 1001}, "'note' must be 1000 characters or fewer"),
        (basic(status="open"), {"status": "open"}, "Incident is already open"),
        (basic(status="in_progress", assigned_to=7), {"status": "in_progress"}, "Incident is already in progress"),
        (basic(status="in_progress", assigned_to=7), {"status": "open"}, "Unassign the engineer before setting the ticket back to open"),
        (basic(status="open"), {"status": "assigned"}, "Assign an engineer to set the ticket to assigned"),
    ])
    def test_bad_input_for_an_admin(self, models, monkeypatch, before, body, message):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, incident_model, "find_basic", before)
        status, data = call(handler, "PUT", "/api/incidents/12/status", body=body)
        assert (status, data) == (400, {"error": message})
        assert models["update_status"].calls == []

    def test_admin_change_posts_a_message_with_the_note(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, incident_model, "find_basic", basic(status="assigned", assigned_to=7))
        status, _ = call(handler, "PUT", "/api/incidents/12/status", body={"status": "in_progress", "note": "Started"})
        assert status == 200
        assert models["update_status"].calls[0][0] == (12, "in_progress", 1, "Ticket #12: status changed to in progress - Started")

    @pytest.mark.parametrize("wanted", ["blocked", "resolved"])
    def test_engineer_only_requests_blocked_or_resolved(self, models, monkeypatch, wanted):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        stub(monkeypatch, incident_model, "find_basic", basic(status="in_progress", assigned_to=7))
        status, _ = call(handler, "PUT", "/api/incidents/12/status", body={"status": wanted, "note": "Parts ordered"})
        assert status == 200
        assert models["update_status"].calls == []
        assert models["request_status"].calls[0][0] == (
            12, wanted, 7, "Parts ordered", 7,
            f"Ticket #12: requested {wanted}, awaiting facility admin approval - Parts ordered",
        )

    def test_same_request_twice_is_400(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        stub(monkeypatch, incident_model, "find_basic", basic(status="in_progress", assigned_to=7, pending_status="resolved"))
        status, data = call(handler, "PUT", "/api/incidents/12/status", body={"status": "resolved"})
        assert (status, data) == (400, {"error": "A request to mark this ticket resolved is already waiting for approval"})

    def test_admin_applies_resolved_directly(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, incident_model, "find_basic", basic(status="in_progress", assigned_to=7))
        status, _ = call(handler, "PUT", "/api/incidents/12/status", body={"status": "resolved"})
        assert status == 200
        assert models["request_status"].calls == []
        assert models["update_status"].calls[0][0][:2] == (12, "resolved")


class TestApprovalRules:
    @pytest.mark.parametrize("role", ["employee", "engineer", "db_admin"])
    def test_admin_only(self, models, monkeypatch, role):
        sign_in_as(monkeypatch, role)
        status, _ = call(handler, "PUT", "/api/incidents/12/approval", body={"decision": "approve"})
        assert status == 403

    def test_bad_decision(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "PUT", "/api/incidents/12/approval", body={"decision": "maybe"})
        assert (status, data) == (400, {"error": "'decision' must be one of: approve, reject"})

    def test_nothing_pending(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "PUT", "/api/incidents/12/approval", body={"decision": "approve"})
        assert (status, data) == (400, {"error": "Nothing is waiting for approval on this ticket"})

    def test_approve_applies_the_requested_status(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, incident_model, "find_basic", basic(status="in_progress", assigned_to=7, pending_status="resolved"))
        status, _ = call(handler, "PUT", "/api/incidents/12/approval", body={"decision": "approve", "note": "Good"})
        assert status == 200
        assert models["update_status"].calls[0][0] == (12, "resolved", 1, "Ticket #12: status changed to resolved (approved) - Good")

    def test_reject_only_clears_the_request(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, incident_model, "find_basic", basic(status="in_progress", assigned_to=7, pending_status="blocked"))
        status, _ = call(handler, "PUT", "/api/incidents/12/approval", body={"decision": "reject"})
        assert status == 200
        assert models["update_status"].calls == []
        assert models["clear_request"].calls[0][0] == (12, 1, "Ticket #12: request to mark blocked rejected")


class TestPriorityRules:
    @pytest.mark.parametrize("body, message", [
        ({}, "'priority' is required"),
        ({"priority": 9}, "'priority' must be between 1 and 5"),
        ({"priority": 3}, "Incident is already priority 3"),
    ])
    def test_bad_input(self, models, monkeypatch, body, message):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "PUT", "/api/incidents/12/priority", body=body)
        assert (status, data) == (400, {"error": message})

    def test_assignee_changes_it_and_a_message_is_posted(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        stub(monkeypatch, incident_model, "find_basic", basic(status="assigned", assigned_to=7))
        status, _ = call(handler, "PUT", "/api/incidents/12/priority", body={"priority": 1})
        assert status == 200
        assert models["update_priority"].calls[0][0] == (12, 1, 7, "Ticket #12: priority changed to 1")

    def test_other_engineer_and_employee_may_not(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=8)
        stub(monkeypatch, incident_model, "find_basic", basic(status="assigned", assigned_to=7))
        assert call(handler, "PUT", "/api/incidents/12/priority", body={"priority": 1})[0] == 403
        sign_in_as(monkeypatch, "employee", user_id=4)
        assert call(handler, "PUT", "/api/incidents/12/priority", body={"priority": 1})[0] == 403


class TestLocationRules:
    def test_admin_only(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=7)
        status, _ = call(handler, "PUT", "/api/incidents/12/location", body={"location": None})
        assert status == 403

    def test_key_is_required(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "PUT", "/api/incidents/12/location", body={})
        assert (status, data) == (400, {"error": "'location' is required (use null to clear it)"})

    def test_same_location_is_400(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, incident_model, "find_basic", basic(location_id=77))
        status, data = call(handler, "PUT", "/api/incidents/12/location", body={"location": {"buildingId": 2, "floor": 3, "room": 1}})
        assert (status, data) == (400, {"error": "Incident already has that location"})

    def test_move_posts_a_message_with_the_written_room(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        status, _ = call(handler, "PUT", "/api/incidents/12/location", body={"location": {"buildingId": 2, "floor": 3, "room": 1}})
        assert status == 200
        assert models["update_location"].calls[0][0] == (12, 77, 1, "Ticket #12: location changed to HQ, floor 3, room 301")

    def test_clear(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, incident_model, "find_basic", basic(location_id=77))
        status, _ = call(handler, "PUT", "/api/incidents/12/location", body={"location": None})
        assert status == 200
        assert models["update_location"].calls[0][0] == (12, None, 1, "Ticket #12: location changed to no location")


class TestStatsRules:
    @pytest.mark.parametrize("path", ["/api/incidents/stats/overview", "/api/incidents/stats/locations"])
    @pytest.mark.parametrize("role", ["employee", "engineer", "db_admin"])
    def test_admin_only(self, models, monkeypatch, path, role):
        sign_in_as(monkeypatch, role)
        assert call(handler, "GET", path)[0] == 403

    @pytest.mark.parametrize("days", ["0", "366", "abc", "-5", "1.5"])
    def test_days_must_be_1_to_365(self, models, monkeypatch, days):
        sign_in_as(monkeypatch, "employee")
        status, data = call(handler, "GET", "/api/incidents/stats/mine", query={"days": days})
        assert (status, data) == (400, {"error": "'days' must be between 1 and 365"})

    @pytest.mark.parametrize("query, message", [
        ({"buildingId": "x"}, "'buildingId' must be a positive whole number"),
        ({"buildingId": "0"}, "'buildingId' must be a positive whole number"),
        ({"buildingId": "2", "floor": "-1"}, "'floor' must be a positive whole number"),
    ])
    def test_location_parameters(self, models, monkeypatch, query, message):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "GET", "/api/incidents/stats/locations", query=query)
        assert (status, data) == (400, {"error": message})

    def test_unknown_building_is_404(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, building_model, "find_by_id", None)
        status, data = call(handler, "GET", "/api/incidents/stats/locations", query={"buildingId": "9"})
        assert (status, data) == (404, {"error": "Building not found"})


class TestIncidentView:
    def test_nulls_when_nothing_is_set(self):
        data = incident_view.serialize(ticket_row(reported_by=None, reporter_name=None, reporter_email=None))
        assert data["location"] is None
        assert data["reportedBy"] is None  # deleted account
        assert data["assignedTo"] is None
        assert data["pendingApproval"] is None
        assert data["resolvedAt"] is None
        assert set(data) == {"id", "title", "pendingApproval", "description", "status", "priority", "location",
                             "reportedBy", "assignedTo", "createdAt", "updatedAt", "resolvedAt"}

    def test_nested_objects(self):
        row = ticket_row(
            location_id=1, floor=3, room=12, building_id=2, building_name="HQ", room_numbers_include_floor=True, max_rooms=50,
            assigned_to=7, assignee_name="Bob", assignee_email="bob@acme.inc",
            pending_status="resolved", pending_requested_by=7, pending_requested_at=NOW, pending_note="Done", pending_requester_name="Bob",
        )
        data = incident_view.serialize(row)
        assert data["location"] == {"id": 1, "building": {"id": 2, "name": "HQ"}, "floor": 3, "room": 12, "roomLabel": "312"}
        assert data["reportedBy"] == {"id": 4, "name": "Ana", "email": "ana@acme.inc"}
        assert data["assignedTo"] == {"id": 7, "name": "Bob", "email": "bob@acme.inc"}
        assert data["pendingApproval"] == {"status": "resolved", "note": "Done", "requestedAt": NOW, "requestedBy": {"id": 7, "name": "Bob"}}

    def test_room_label_without_floor_numbering_and_without_room(self):
        row = ticket_row(location_id=1, floor=-1, room=4, building_id=2, building_name="HQ", room_numbers_include_floor=False, max_rooms=5)
        assert incident_view.serialize(row)["location"]["roomLabel"] == "4"
        row["room"] = None
        assert incident_view.serialize(row)["location"]["roomLabel"] is None


class TestStatsView:
    def test_status_counts_always_lists_every_status(self):
        data = stats_view.status_counts([{"status": "open", "count": 2}, {"status": "closed", "count": 1}])
        assert data == {"total": 3, "byStatus": {"open": 2, "assigned": 0, "in_progress": 0, "blocked": 0, "resolved": 0, "closed": 1}}
        assert list(data["byStatus"]) == incident_model.STATUSES

    def test_building_counts_name_the_missing_location(self):
        rows = [{"building_id": 1, "building_name": "HQ", "count": 7}, {"building_id": None, "building_name": None, "count": 2}]
        assert stats_view.building_counts(rows) == [{"id": 1, "name": "HQ", "count": 7}, {"id": None, "name": "No location", "count": 2}]

    def test_floor_and_room_counts(self):
        assert stats_view.floor_counts([{"floor": -1, "count": 3}]) == [{"floor": -1, "count": 3}]
        rows = [{"room": 12, "count": 2}, {"room": None, "count": 1}]
        assert stats_view.room_counts(rows, lambda room: None if room is None else f"3{room:02d}") == [
            {"room": 12, "label": "312", "count": 2}, {"room": None, "label": None, "count": 1}]
