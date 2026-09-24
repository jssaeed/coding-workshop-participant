"""Integration tests for the incidents service: real handler, real PostgreSQL."""

import pytest

from function import handler


@pytest.fixture
def people(db):
    """The cast: everyone at branch 1 unless said otherwise."""
    return {
        "admin": db.create_user("facility_admin"),
        "engineer": db.create_user("engineer"),
        "other_engineer": db.create_user("engineer"),
        "employee": db.create_user("employee"),
        "other_employee": db.create_user("employee"),
        "db_admin": db.create_user("db_admin"),
        # Miami (branch 2): a facility admin there has no say over branch 1
        "miami_admin": db.create_user("facility_admin", branch_id=2),
        "miami_engineer": db.create_user("engineer", branch_id=2),
        "miami_employee": db.create_user("employee", branch_id=2),
    }


@pytest.fixture
def hq(db):
    """A building with 3 floors and one basement; floor 3 has 10 rooms, numbered by floor."""
    return db.create_building(branch_id=1, name="HQ", floors=3, basement_floors=1, rooms={3: 10}, include_floor=True)


def messages_on(db, incident_id):
    return db.fetch_all("SELECT user_id, message FROM messages WHERE incident_id = %s ORDER BY id", (incident_id,))


def ticket_state(db, incident_id):
    return db.fetch_one(
        "SELECT status, priority, assigned_to, location_id, resolved_at, pending_status, pending_note FROM incidents WHERE id = %s",
        (incident_id,),
    )


class TestCreate:
    def test_minimal_ticket(self, api, db, people):
        status, data = api(handler, "POST", "/api/incidents", user=people["employee"], body={"title": "Leaking pipe"})
        assert status == 201
        assert data["title"] == "Leaking pipe"
        assert data["status"] == "open"
        assert data["priority"] == 3
        assert data["category"] == "other"
        assert data["description"] == ""
        assert data["location"] is None
        assert data["assignedTo"] is None
        assert data["resolvedAt"] is None
        assert data["pendingApproval"] is None
        assert data["reportedBy"] == {"id": people["employee"]["id"], "name": people["employee"]["name"], "email": people["employee"]["email"]}
        assert db.fetch_one("SELECT title, reported_by FROM incidents WHERE id = %s", (data["id"],)) == {"title": "Leaking pipe", "reported_by": people["employee"]["id"]}

    def test_with_location_and_room_label(self, api, db, people, hq):
        body = {"title": "Leak", "description": "Under the sink", "priority": 2, "location": {"buildingId": hq["id"], "floor": 3, "room": 7}}
        status, data = api(handler, "POST", "/api/incidents", user=people["employee"], body=body)
        assert status == 201
        assert data["priority"] == 2
        assert data["location"]["building"] == {"id": hq["id"], "name": "HQ"}
        assert data["location"]["floor"] == 3
        assert data["location"]["room"] == 7
        assert data["location"]["roomLabel"] == "307"

    def test_with_a_category(self, api, db, people):
        status, data = api(handler, "POST", "/api/incidents", user=people["employee"], body={"title": "No power", "category": "electrical"})
        assert (status, data["category"]) == (201, "electrical")
        assert db.fetch_one("SELECT category FROM incidents WHERE id = %s", (data["id"],)) == {"category": "electrical"}

    def test_unknown_category_saves_nothing(self, api, db, people):
        status, data = api(handler, "POST", "/api/incidents", user=people["employee"], body={"title": "Odd", "category": "magic"})
        assert status == 400
        assert data["error"].startswith("'category' must be one of: plumbing, electrical")
        assert db.count("incidents") == 0

    def test_the_same_place_is_stored_once(self, api, db, people, hq):
        body = {"title": "A", "location": {"buildingId": hq["id"], "floor": -1}}
        _, first = api(handler, "POST", "/api/incidents", user=people["employee"], body=body)
        _, second = api(handler, "POST", "/api/incidents", user=people["engineer"], body={**body, "title": "B"})
        assert first["location"]["id"] == second["location"]["id"]
        assert first["location"]["roomLabel"] is None
        assert db.count("locations") == 1

    @pytest.mark.parametrize("location, message", [
        ({"buildingId": 999, "floor": 1}, "'buildingId' does not match a known building"),
        ({"buildingId": None, "floor": 1}, "'buildingId' is required"),
        ({"floor": 0}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"floor": 4}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"floor": -2}, "'floor' must be between B1 and 3 (there is no floor 0)"),
        ({"floor": 3, "room": 11}, "'room' must be between 1 and 10 on floor 3"),
        ({"floor": 3, "room": 0}, "'room' must be a positive whole number"),
    ])
    def test_bad_location_saves_nothing(self, api, db, people, hq, location, message):
        location = {"buildingId": hq["id"], **location} if "buildingId" not in location else location
        status, data = api(handler, "POST", "/api/incidents", user=people["employee"], body={"title": "Leak", "location": location})
        assert (status, data) == (400, {"error": message})
        assert db.count("incidents") == 0
        assert db.count("locations") == 0

    def test_building_at_another_branch(self, api, db, people, hq):
        away = db.create_user("employee", branch_id=2)
        status, data = api(handler, "POST", "/api/incidents", user=away, body={"title": "Leak", "location": {"buildingId": hq["id"], "floor": 1}})
        assert (status, data) == (400, {"error": "'buildingId' is not a building at your branch"})

    def test_room_on_a_floor_without_a_count(self, api, db, people, hq):
        status, data = api(handler, "POST", "/api/incidents", user=people["employee"], body={"title": "Leak", "location": {"buildingId": hq["id"], "floor": 1, "room": 250}})
        assert status == 201
        assert data["location"]["roomLabel"] == "1250"  # floor 1 + room 250, two-digit padding (no floor has 100+ rooms)


class TestGet:
    def test_who_can_see_a_ticket(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")
        for who, expected in [("employee", 200), ("engineer", 200), ("admin", 200),
                              ("other_employee", 404), ("other_engineer", 404), ("db_admin", 404)]:
            status, _ = api(handler, "GET", f"/api/incidents/{ticket}", user=people[who])
            assert status == expected, who

    def test_unknown_ticket(self, api, db, people):
        status, data = api(handler, "GET", "/api/incidents/999", user=people["admin"])
        assert (status, data) == (404, {"error": "Incident not found"})


class TestList:
    @pytest.fixture
    def tickets(self, db, people):
        e, en, oe = people["employee"]["id"], people["engineer"]["id"], people["other_engineer"]["id"]
        return {
            "mine_p3": db.create_incident(e, priority=3, created_days_ago=2),
            "mine_p1": db.create_incident(e, priority=1, created_days_ago=3, category="plumbing"),
            "mine_p3_newer": db.create_incident(e, priority=3, created_days_ago=1, status="closed"),
            "assigned_to_engineer": db.create_incident(oe, assigned_to=en, status="in_progress", pending_status="resolved", pending_requested_by=en),
            "assigned_to_other": db.create_incident(oe, assigned_to=oe, status="assigned"),
            "unassigned_resolved": db.create_incident(oe, status="resolved"),
        }

    def ids(self, data):
        return [t["id"] for t in data["items"]]

    def test_default_scope_is_mine_most_urgent_then_newest(self, api, db, people, tickets):
        status, data = api(handler, "GET", "/api/incidents", user=people["employee"])
        assert status == 200
        assert self.ids(data) == [tickets["mine_p1"], tickets["mine_p3_newer"], tickets["mine_p3"]]

    def test_filters(self, api, db, people, tickets):
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"status": "closed"})
        assert self.ids(data) == [tickets["mine_p3_newer"]]
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"priority": "3", "status": "open"})
        assert self.ids(data) == [tickets["mine_p3"]]
        # several statuses: a ticket in any of them matches
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"priority": "3", "status": "open,closed"})
        assert self.ids(data) == [tickets["mine_p3_newer"], tickets["mine_p3"]]
        assert api(handler, "GET", "/api/incidents", user=people["employee"], query={"status": "open,done"})[0] == 400
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"category": "plumbing"})
        assert self.ids(data) == [tickets["mine_p1"]]
        assert data["items"][0]["category"] == "plumbing"
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"category": "other"})
        assert (data["total"], len(data["items"])) == (2, 2)

    def test_days_keeps_only_recent_tickets(self, api, db, people, tickets):
        # created 1, 2 and 3 days ago: "days=2" keeps the one from yesterday
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"days": "2"})
        assert self.ids(data) == [tickets["mine_p3_newer"]]
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"days": "3"})
        assert self.ids(data) == [tickets["mine_p3_newer"], tickets["mine_p3"]]

    def test_model_with_no_filters_returns_every_ticket(self, db, people, tickets):
        # The model's own defaults: no WHERE clause, no LIMIT (callers that need every row)
        from models import incident as incident_model
        assert incident_model.count() == 6
        assert len(incident_model.search()) == 6

    def test_building_and_floor_filters_and_location_sort(self, api, db, people, hq):
        e = people["employee"]["id"]
        annex = db.create_building(branch_id=1, name="Annex", floors=2, basement_floors=0)
        room = db.create_location(hq["id"], 3, room=7)
        basement = db.create_location(hq["id"], -1)
        annex_floor = db.create_location(annex["id"], 2)
        in_room = db.create_incident(e, location_id=room["id"], priority=1)
        in_basement = db.create_incident(e, location_id=basement["id"], priority=2)
        in_annex = db.create_incident(e, location_id=annex_floor["id"], priority=3)
        nowhere = db.create_incident(e, priority=4)

        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": str(hq["id"])})
        assert (self.ids(data), data["total"]) == ([in_room, in_basement], 2)
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": str(hq["id"]), "floor": "-1"})
        assert (self.ids(data), data["total"]) == ([in_basement], 1)
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": str(hq["id"]), "floor": "2"})
        assert (self.ids(data), data["total"]) == ([], 0)
        # Other filters still apply on top
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": str(hq["id"]), "priority": "2"})
        assert self.ids(data) == [in_basement]

        # Sorted by place: building name, then floor, then room; no location last either way
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"sort": "location"})
        assert self.ids(data) == [in_annex, in_basement, in_room, nowhere]
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"sort": "location", "order": "desc"})
        assert self.ids(data) == [in_room, in_basement, in_annex, nowhere]

    def test_building_filter_errors(self, api, db, people, hq):
        away = db.create_building(branch_id=2, name="Miami office", floors=1, basement_floors=0)
        status, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": "999"})
        assert (status, data) == (400, {"error": "'buildingId' does not match a known building"})
        status, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": str(away["id"])})
        assert (status, data) == (400, {"error": "'buildingId' is not a building at your branch"})
        status, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"floor": "1"})
        assert (status, data) == (400, {"error": "'floor' needs a 'buildingId'"})
        status, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"buildingId": str(hq["id"]), "floor": "5"})
        assert (status, data) == (400, {"error": "'floor' must be between B1 and 3 (there is no floor 0)"})

    def test_assigned_scope(self, api, db, people, tickets):
        _, data = api(handler, "GET", "/api/incidents", user=people["engineer"], query={"scope": "assigned"})
        assert self.ids(data) == [tickets["assigned_to_engineer"]]
        status, _ = api(handler, "GET", "/api/incidents", user=people["employee"], query={"scope": "assigned"})
        assert status == 403

    def test_unassigned_scope_excludes_finished_tickets(self, api, db, people, tickets):
        _, data = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "unassigned"})
        assert set(self.ids(data)) == {tickets["mine_p3"], tickets["mine_p1"]}

    def test_pending_scope(self, api, db, people, tickets):
        _, data = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "pending"})
        assert self.ids(data) == [tickets["assigned_to_engineer"]]
        assert data["items"][0]["pendingApproval"]["status"] == "resolved"
        assert data["items"][0]["pendingApproval"]["requestedBy"]["id"] == people["engineer"]["id"]

    def test_all_scope_is_admin_only(self, api, db, people, tickets):
        status, data = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "all"})
        assert status == 200
        assert (len(data["items"]), data["total"], data["page"], data["limit"], data["pages"]) == (6, 6, 1, 25, 1)
        for who in ("engineer", "employee", "db_admin"):
            assert api(handler, "GET", "/api/incidents", user=people[who], query={"scope": "all"})[0] == 403

    def test_pages_are_stable_and_do_not_overlap(self, api, db, people, tickets):
        """Two pages of two cover the first four tickets in the same order as one page of four."""
        _, whole = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "all", "limit": "4"})
        _, first = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "all", "limit": "2", "page": "1"})
        _, second = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "all", "limit": "2", "page": "2"})
        assert self.ids(first) + self.ids(second) == self.ids(whole)
        assert (first["total"], first["pages"], second["page"]) == (6, 3, 2)
        _, beyond = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": "all", "limit": "2", "page": "9"})
        assert (beyond["items"], beyond["total"], beyond["pages"]) == ([], 6, 3)

    def test_sort_options(self, api, db, people, tickets):
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"sort": "created", "order": "asc"})
        assert self.ids(data) == [tickets["mine_p1"], tickets["mine_p3"], tickets["mine_p3_newer"]]
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"sort": "id", "order": "desc"})
        assert self.ids(data) == sorted(self.ids(data), reverse=True)
        _, data = api(handler, "GET", "/api/incidents", user=people["employee"], query={"sort": "priority", "order": "desc"})
        assert self.ids(data)[-1] == tickets["mine_p1"]

    def test_text_search(self, api, db, hq):
        # Names without digits, so a search for a ticket number cannot match a person
        reporter = db.create_user("employee", name="Ana Lopez", email="ana@acme.inc")
        engineer = db.create_user("engineer", name="Bob Stone", email="bob@acme.inc")
        place = db.create_location(hq["id"], 3, 7)
        leak = db.create_incident(reporter["id"], title="Leaking pipe", description="under the KITCHEN sink", location_id=place["id"])
        db.create_incident(reporter["id"], title="No power", description="third floor")
        assigned = db.create_incident(reporter["id"], title="Cold office", assigned_to=engineer["id"], status="assigned")

        def search(q):
            _, data = api(handler, "GET", "/api/incidents", user=reporter, query={"q": q})
            return self.ids(data), data["total"]

        assert search("kitchen leak") == ([leak], 1)          # every word, any order, any case
        assert search("kitchen power") == ([], 0)             # words must all match
        assert search(f"#{assigned}") == ([assigned], 1)      # by ticket number
        assert search(str(leak)) == ([leak], 1)
        assert search("HQ") == ([leak], 1)                    # the building
        assert search("bob") == ([assigned], 1)               # the assignee
        assert search("lopez")[1] == 3                        # the reporter
        _, data = api(handler, "GET", "/api/incidents", user=reporter, query={"q": "  "})
        assert data["total"] == 3                             # blank search means no search


class TestBranches:
    """Tickets belong to the branch they were filed at; admins only reach their own."""

    def test_a_ticket_is_filed_at_the_reporters_branch(self, api, db, people):
        status, data = api(handler, "POST", "/api/incidents", user=people["miami_employee"], body={"title": "AC broken"})
        assert (status, data["branchId"]) == (201, 2)
        assert db.fetch_one("SELECT branch_id FROM incidents WHERE id = %s", (data["id"],)) == {"branch_id": 2}

    def test_admin_at_another_branch_cannot_see_or_change_a_ticket(self, api, db, people, hq):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"],
                                    status="in_progress", pending_status="resolved", pending_requested_by=people["engineer"]["id"])
        miami = people["miami_admin"]
        requests = [
            ("GET", f"/api/incidents/{ticket}", None),
            ("PUT", f"/api/incidents/{ticket}/assign", {"assigneeId": None}),
            ("PUT", f"/api/incidents/{ticket}/status", {"status": "blocked"}),
            ("PUT", f"/api/incidents/{ticket}/priority", {"priority": 1}),
            ("PUT", f"/api/incidents/{ticket}/approval", {"decision": "approve"}),
            ("PUT", f"/api/incidents/{ticket}/location", {"location": None}),
        ]
        for method, path, body in requests:
            status, data = api(handler, method, path, user=miami, body=body)
            assert (status, data) == (404, {"error": "Incident not found"}), path
        before = ticket_state(db, ticket)
        assert (before["status"], before["priority"], before["pending_status"]) == ("in_progress", 3, "resolved")
        assert messages_on(db, ticket) == []

    def test_admin_scopes_only_list_their_own_branch(self, api, db, people):
        princeton = db.create_incident(people["employee"]["id"])
        miami = db.create_incident(people["miami_employee"]["id"], pending_status="blocked", pending_requested_by=people["miami_engineer"]["id"])
        for scope in ("all", "unassigned", "pending"):
            _, data = api(handler, "GET", "/api/incidents", user=people["admin"], query={"scope": scope})
            assert [t["id"] for t in data["items"]] == ([princeton] if scope != "pending" else []), scope
            _, data = api(handler, "GET", "/api/incidents", user=people["miami_admin"], query={"scope": scope})
            assert [t["id"] for t in data["items"]] == [miami], scope
            assert data["items"][0]["branchId"] == 2

    def test_assignee_must_work_at_the_tickets_branch(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/assign", user=people["admin"], body={"assigneeId": people["miami_engineer"]["id"]})
        assert (status, data) == (400, {"error": "Tickets can only be assigned to staff at the ticket's branch"})
        assert ticket_state(db, ticket)["assigned_to"] is None
        assert messages_on(db, ticket) == []

    def test_stats_count_only_the_admins_branch(self, api, db, people, hq):
        miami_hq = db.create_building(branch_id=2, name="Miami HQ", floors=2)
        spot = db.create_location(miami_hq["id"], 1)
        db.create_incident(people["employee"]["id"], status="resolved", assigned_to=people["engineer"]["id"])
        db.create_incident(people["miami_employee"]["id"], status="open", location_id=spot["id"], assigned_to=people["miami_engineer"]["id"])
        db.create_incident(people["miami_employee"]["id"], status="open", location_id=spot["id"])

        _, result = api(handler, "GET", "/api/incidents/stats/overview", user=people["miami_admin"])
        assert (result["total"], result["byStatus"]["open"], result["resolution"]["resolvedCount"]) == (2, 2, 0)
        _, result = api(handler, "GET", "/api/incidents/stats/overview", user=people["admin"])
        assert result["total"] == 1

        _, result = api(handler, "GET", "/api/incidents/stats/engineers", user=people["miami_admin"])
        assert [(row["id"], row["assigned"]) for row in result] == [(people["miami_engineer"]["id"], 1)]

        _, result = api(handler, "GET", "/api/incidents/stats/locations", user=people["miami_admin"])
        assert result["items"] == [{"id": miami_hq["id"], "name": "Miami HQ", "count": 2}]
        status, data = api(handler, "GET", "/api/incidents/stats/locations", user=people["miami_admin"], query={"buildingId": str(hq["id"])})
        assert (status, data) == (404, {"error": "Building not found"})


class TestAssign:
    def test_assigning_an_open_ticket_and_posting_the_message(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/assign", user=people["admin"], body={"assigneeId": people["engineer"]["id"]})
        assert status == 200
        assert data["status"] == "assigned"
        assert data["assignedTo"]["id"] == people["engineer"]["id"]
        assert messages_on(db, ticket) == [{"user_id": people["admin"]["id"], "message": f"Ticket #{ticket}: assigned to {people['engineer']['name']}"}]

    def test_unassigning_reopens_and_other_statuses_stay(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/assign", user=people["admin"], body={"assigneeId": None})
        assert (status, data["status"], data["assignedTo"]) == (200, "open", None)
        assert messages_on(db, ticket)[-1]["message"] == f"Ticket #{ticket}: unassigned"

        busy = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress")
        _, data = api(handler, "PUT", f"/api/incidents/{busy}/assign", user=people["admin"], body={"assigneeId": people["other_engineer"]["id"]})
        assert data["status"] == "in_progress"
        assert data["assignedTo"]["id"] == people["other_engineer"]["id"]

    def test_admins_can_be_assignees_too(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/assign", user=people["admin"], body={"assigneeId": people["admin"]["id"]})
        assert (status, data["assignedTo"]["id"]) == (200, people["admin"]["id"])

    def test_errors_change_nothing(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")
        cases = [
            ({"assigneeId": people["employee"]["id"]}, 400, "Tickets can only be assigned to an engineer or admin"),
            ({"assigneeId": people["db_admin"]["id"]}, 400, "Tickets can only be assigned to an engineer or admin"),
            ({"assigneeId": 9999}, 400, "'assigneeId' does not match a known user"),
            ({"assigneeId": people["engineer"]["id"]}, 400, "Incident already has that assignment"),
        ]
        for body, expected_status, message in cases:
            status, data = api(handler, "PUT", f"/api/incidents/{ticket}/assign", user=people["admin"], body=body)
            assert (status, data) == (expected_status, {"error": message})
        assert api(handler, "PUT", f"/api/incidents/{ticket}/assign", user=people["engineer"], body={"assigneeId": None})[0] == 403
        assert api(handler, "PUT", "/api/incidents/999/assign", user=people["admin"], body={"assigneeId": None})[0] == 404
        assert ticket_state(db, ticket)["assigned_to"] == people["engineer"]["id"]
        assert messages_on(db, ticket) == []


class TestStatus:
    def test_admin_moves_a_ticket_along_with_a_note(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["admin"], body={"status": "in_progress", "note": "Started"})
        assert (status, data["status"]) == (200, "in_progress")
        assert messages_on(db, ticket) == [{"user_id": people["admin"]["id"], "message": f"Ticket #{ticket}: status changed to in progress - Started"}]

    def test_resolved_and_closed_stamp_resolved_at_and_reopening_clears_it(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress")
        _, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["admin"], body={"status": "resolved"})
        assert data["status"] == "resolved" and data["resolvedAt"] is not None
        _, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["admin"], body={"status": "in_progress"})
        assert data["status"] == "in_progress" and data["resolvedAt"] is None
        _, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["admin"], body={"status": "closed"})
        assert data["status"] == "closed" and data["resolvedAt"] is not None

    def test_engineer_requests_resolved_instead_of_setting_it(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress")
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["engineer"], body={"status": "resolved", "note": "Fixed"})
        assert status == 200
        assert data["status"] == "in_progress"
        assert data["resolvedAt"] is None
        assert data["pendingApproval"]["status"] == "resolved"
        assert data["pendingApproval"]["note"] == "Fixed"
        assert data["pendingApproval"]["requestedBy"] == {"id": people["engineer"]["id"], "name": people["engineer"]["name"]}
        assert data["pendingApproval"]["requestedAt"] is not None
        assert messages_on(db, ticket)[-1] == {"user_id": people["engineer"]["id"], "message": f"Ticket #{ticket}: requested resolved, awaiting facility admin approval - Fixed"}

        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["engineer"], body={"status": "resolved"})
        assert status == 400

    def test_engineer_can_still_set_other_statuses_which_drops_a_pending_request(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned",
                                    pending_status="blocked", pending_requested_by=people["engineer"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["engineer"], body={"status": "in_progress"})
        assert (status, data["status"], data["pendingApproval"]) == (200, "in_progress", None)

    def test_assignment_rules_and_access(self, api, db, people):
        assigned = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")
        free = db.create_incident(people["employee"]["id"])
        assert api(handler, "PUT", f"/api/incidents/{assigned}/status", user=people["admin"], body={"status": "open"})[1] == {"error": "Unassign the engineer before setting the ticket back to open"}
        assert api(handler, "PUT", f"/api/incidents/{free}/status", user=people["admin"], body={"status": "assigned"})[1] == {"error": "Assign an engineer to set the ticket to assigned"}
        assert api(handler, "PUT", f"/api/incidents/{free}/status", user=people["admin"], body={"status": "open"})[1] == {"error": "Incident is already open"}
        assert api(handler, "PUT", f"/api/incidents/{assigned}/status", user=people["other_engineer"], body={"status": "in_progress"})[0] == 403
        assert api(handler, "PUT", f"/api/incidents/{assigned}/status", user=people["employee"], body={"status": "in_progress"})[0] == 403
        assert api(handler, "PUT", "/api/incidents/999/status", user=people["admin"], body={"status": "in_progress"})[0] == 404
        assert ticket_state(db, assigned)["status"] == "assigned"
        assert db.count("messages") == 0


class TestApproval:
    def test_approve(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress",
                                    pending_status="resolved", pending_requested_by=people["engineer"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/approval", user=people["admin"], body={"decision": "approve", "note": "Thanks"})
        assert status == 200
        assert data["status"] == "resolved"
        assert data["resolvedAt"] is not None
        assert data["pendingApproval"] is None
        assert messages_on(db, ticket) == [{"user_id": people["admin"]["id"], "message": f"Ticket #{ticket}: status changed to resolved (approved) - Thanks"}]

    def test_reject(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress",
                                    pending_status="blocked", pending_requested_by=people["engineer"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/approval", user=people["admin"], body={"decision": "reject"})
        assert (status, data["status"], data["pendingApproval"]) == (200, "in_progress", None)
        assert ticket_state(db, ticket)["pending_status"] is None
        assert messages_on(db, ticket) == [{"user_id": people["admin"]["id"], "message": f"Ticket #{ticket}: request to mark blocked rejected"}]

    def test_errors(self, api, db, people):
        plain = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress")
        assert api(handler, "PUT", f"/api/incidents/{plain}/approval", user=people["admin"], body={"decision": "approve"})[1] == {"error": "Nothing is waiting for approval on this ticket"}
        assert api(handler, "PUT", f"/api/incidents/{plain}/approval", user=people["engineer"], body={"decision": "approve"})[0] == 403
        assert api(handler, "PUT", "/api/incidents/999/approval", user=people["admin"], body={"decision": "approve"})[0] == 404


class TestApprovalNotes:
    """The optional note travels with the request, the approval and the rejection."""

    def test_request_with_a_note(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress")
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/status", user=people["engineer"], body={"status": "blocked", "note": "Parts missing"})
        assert (status, data["status"], data["pendingApproval"]["note"]) == (200, "in_progress", "Parts missing")
        assert ticket_state(db, ticket)["pending_note"] == "Parts missing"
        assert messages_on(db, ticket) == [{"user_id": people["engineer"]["id"],
                                           "message": f"Ticket #{ticket}: requested blocked, awaiting facility admin approval - Parts missing"}]

    def test_approve_with_a_note(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress",
                                    pending_status="blocked", pending_requested_by=people["engineer"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/approval", user=people["admin"], body={"decision": "approve", "note": "Fine"})
        assert (status, data["status"], data["pendingApproval"]) == (200, "blocked", None)
        assert messages_on(db, ticket) == [{"user_id": people["admin"]["id"], "message": f"Ticket #{ticket}: status changed to blocked (approved) - Fine"}]

    def test_reject_with_a_note(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="in_progress",
                                    pending_status="resolved", pending_requested_by=people["engineer"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/approval", user=people["admin"], body={"decision": "reject", "note": "Not yet"})
        assert (status, data["status"], data["pendingApproval"]) == (200, "in_progress", None)
        assert ticket_state(db, ticket)["pending_status"] is None
        assert messages_on(db, ticket) == [{"user_id": people["admin"]["id"], "message": f"Ticket #{ticket}: request to mark resolved rejected - Not yet"}]


class TestPriority:
    def test_assignee_and_admin_change_it_with_a_message(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned", priority=3)
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/priority", user=people["engineer"], body={"priority": 1})
        assert (status, data["priority"]) == (200, 1)
        assert messages_on(db, ticket) == [{"user_id": people["engineer"]["id"], "message": f"Ticket #{ticket}: priority changed to 1"}]
        assert api(handler, "PUT", f"/api/incidents/{ticket}/priority", user=people["admin"], body={"priority": 5})[1]["priority"] == 5

    def test_errors(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned", priority=3)
        assert api(handler, "PUT", f"/api/incidents/{ticket}/priority", user=people["engineer"], body={"priority": 3})[1] == {"error": "Incident is already priority 3"}
        assert api(handler, "PUT", f"/api/incidents/{ticket}/priority", user=people["other_engineer"], body={"priority": 1})[0] == 403
        assert api(handler, "PUT", f"/api/incidents/{ticket}/priority", user=people["employee"], body={"priority": 1})[0] == 403
        assert ticket_state(db, ticket)["priority"] == 3


class TestCategory:
    def test_assignee_and_admin_change_it_with_a_message(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/category", user=people["engineer"], body={"category": "plumbing"})
        assert (status, data["category"]) == (200, "plumbing")
        assert messages_on(db, ticket) == [{"user_id": people["engineer"]["id"], "message": f"Ticket #{ticket}: category changed to plumbing"}]
        assert api(handler, "PUT", f"/api/incidents/{ticket}/category", user=people["admin"], body={"category": "hvac"})[1]["category"] == "hvac"
        assert db.fetch_one("SELECT category FROM incidents WHERE id = %s", (ticket,)) == {"category": "hvac"}

    def test_errors(self, api, db, people):
        ticket = db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned", category="plumbing")
        assert api(handler, "PUT", f"/api/incidents/{ticket}/category", user=people["engineer"], body={"category": "plumbing"})[1] == {"error": "Incident is already in the plumbing category"}
        assert api(handler, "PUT", f"/api/incidents/{ticket}/category", user=people["engineer"], body={"category": "magic"})[0] == 400
        assert api(handler, "PUT", f"/api/incidents/{ticket}/category", user=people["other_engineer"], body={"category": "hvac"})[0] == 403
        assert api(handler, "PUT", f"/api/incidents/{ticket}/category", user=people["employee"], body={"category": "hvac"})[0] == 403
        assert api(handler, "PUT", "/api/incidents/999/category", user=people["admin"], body={"category": "hvac"})[0] == 404
        assert db.fetch_one("SELECT category FROM incidents WHERE id = %s", (ticket,)) == {"category": "plumbing"}
        assert messages_on(db, ticket) == []


class TestLocation:
    def test_move_and_clear(self, api, db, people, hq):
        ticket = db.create_incident(people["employee"]["id"])
        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/location", user=people["admin"], body={"location": {"buildingId": hq["id"], "floor": 3, "room": 7}})
        assert status == 200
        assert data["location"]["roomLabel"] == "307"
        assert messages_on(db, ticket)[-1]["message"] == f"Ticket #{ticket}: location changed to HQ, floor 3, room 307"

        status, data = api(handler, "PUT", f"/api/incidents/{ticket}/location", user=people["admin"], body={"location": None})
        assert (status, data["location"]) == (200, None)
        assert messages_on(db, ticket)[-1]["message"] == f"Ticket #{ticket}: location changed to no location"

    def test_errors(self, api, db, people, hq):
        location = db.create_location(hq["id"], 2)
        ticket = db.create_incident(people["employee"]["id"], location_id=location["id"])
        assert api(handler, "PUT", f"/api/incidents/{ticket}/location", user=people["admin"], body={"location": {"buildingId": hq["id"], "floor": 2}})[1] == {"error": "Incident already has that location"}
        assert api(handler, "PUT", f"/api/incidents/{ticket}/location", user=people["admin"], body={})[0] == 400
        assert api(handler, "PUT", f"/api/incidents/{ticket}/location", user=people["admin"], body={"location": {"buildingId": hq["id"], "floor": 9}})[0] == 400
        assert api(handler, "PUT", f"/api/incidents/{ticket}/location", user=people["engineer"], body={"location": None})[0] == 403
        assert ticket_state(db, ticket)["location_id"] == location["id"]


class TestStats:
    @pytest.fixture
    def data(self, db, people, hq):
        e, en = people["employee"]["id"], people["engineer"]["id"]
        room = db.create_location(hq["id"], 3, room=7)
        floor = db.create_location(hq["id"], 3)
        basement = db.create_location(hq["id"], -1)
        db.create_incident(e, status="open", location_id=room["id"], priority=1, category="plumbing")
        db.create_incident(e, status="open", location_id=room["id"], assigned_to=en, priority=1, category="plumbing")
        db.create_incident(e, status="in_progress", location_id=floor["id"], assigned_to=en, priority=3, category="electrical")
        db.create_incident(en, status="closed", location_id=basement["id"], priority=5, category="hvac")
        db.create_incident(en, status="resolved", priority=3)
        db.create_incident(e, status="open", created_days_ago=40, priority=2, category="safety")  # outside the default 30 days

    def test_overview_counts_the_last_n_days(self, api, db, people, data):
        status, result = api(handler, "GET", "/api/incidents/stats/overview", user=people["admin"])
        assert status == 200
        assert result["total"] == 5
        assert result["byStatus"] == {"open": 2, "assigned": 0, "in_progress": 1, "blocked": 0, "resolved": 1, "closed": 1}
        assert result["byPriority"] == {"1": 2, "2": 0, "3": 2, "4": 0, "5": 1}
        assert result["byCategory"] == {"plumbing": 2, "electrical": 1, "hvac": 1, "structural": 0, "doors_and_locks": 0, "elevators": 0,
                                        "furniture": 0, "appliances": 0, "safety": 0, "cleaning": 0, "other": 1}
        assert result["resolution"]["resolvedCount"] == 0  # the test rows have no resolved_at stamp
        _, result = api(handler, "GET", "/api/incidents/stats/overview", user=people["admin"], query={"days": "365"})
        assert (result["total"], result["byPriority"]["2"], result["byCategory"]["safety"]) == (6, 1, 1)

    def test_locations_drill_down(self, api, db, people, hq, data):
        _, result = api(handler, "GET", "/api/incidents/stats/locations", user=people["admin"])
        assert result == {"level": "building", "items": [{"id": hq["id"], "name": "HQ", "count": 4}, {"id": None, "name": "No location", "count": 1}]}

        _, result = api(handler, "GET", "/api/incidents/stats/locations", user=people["admin"], query={"buildingId": str(hq["id"])})
        assert result == {"level": "floor", "building": {"id": hq["id"], "name": "HQ"}, "items": [{"floor": 3, "count": 3}, {"floor": -1, "count": 1}]}

        _, result = api(handler, "GET", "/api/incidents/stats/locations", user=people["admin"], query={"buildingId": str(hq["id"]), "floor": "3"})
        assert result == {"level": "room", "building": {"id": hq["id"], "name": "HQ"}, "floor": 3,
                          "items": [{"room": 7, "label": "307", "count": 2}, {"room": None, "label": None, "count": 1}]}

        assert api(handler, "GET", "/api/incidents/stats/locations", user=people["admin"], query={"buildingId": "999"})[0] == 404

    def test_mine(self, api, db, people, data):
        _, result = api(handler, "GET", "/api/incidents/stats/mine", user=people["employee"])
        assert result["reported"]["total"] == 3
        assert result["reported"]["byStatus"]["open"] == 2
        assert result["assigned"] is None

        _, result = api(handler, "GET", "/api/incidents/stats/mine", user=people["engineer"])
        assert result["reported"]["total"] == 2
        assert result["assigned"] == {"total": 2, "byStatus": {"open": 1, "assigned": 0, "in_progress": 1, "blocked": 0, "resolved": 0, "closed": 0}}
