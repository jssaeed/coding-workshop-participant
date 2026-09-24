"""Integration tests for the buildings service: real handler, real PostgreSQL."""

import pytest

from function import handler


@pytest.fixture
def admin(db):
    return db.create_user("facility_admin", branch_id=1)


def floors_of(db, building_id):
    return {r["floor"]: r["rooms"] for r in db.fetch_all("SELECT floor, rooms FROM building_floors WHERE building_id = %s", (building_id,))}


class TestList:
    def test_own_branch_only_alphabetical_with_floors_in_display_order(self, api, db):
        employee = db.create_user("employee", branch_id=1)
        db.create_building(branch_id=1, name="Zeta", floors=2, basement_floors=2, rooms={2: 5, -1: 3})
        db.create_building(branch_id=1, name="Annex", floors=1)
        db.create_building(branch_id=2, name="Beta", floors=1)

        status, data = api(handler, "GET", "/api/buildings", user=employee)
        assert status == 200
        assert [b["name"] for b in data] == ["Annex", "Zeta"]
        zeta = data[1]
        assert zeta["floors"] == 2 and zeta["basementFloors"] == 2
        assert zeta["rooms"] == [{"floor": 2, "rooms": 5}, {"floor": 1, "rooms": 0}, {"floor": -1, "rooms": 3}, {"floor": -2, "rooms": 0}]
        assert zeta["branchId"] == 1

    def test_empty_branch(self, api, db):
        status, data = api(handler, "GET", "/api/buildings", user=db.create_user(branch_id=2))
        assert (status, data) == (200, [])


class TestCreate:
    def test_persists_building_and_floors(self, api, db, admin):
        body = {"name": " HQ ", "floors": 3, "basementFloors": 2, "roomsPerFloor": 10,
                "rooms": [{"floor": -1, "rooms": 4}, {"floor": -2, "rooms": 0}], "roomNumbersIncludeFloor": True}
        status, data = api(handler, "POST", "/api/buildings", user=admin, body=body)
        assert status == 201
        assert data["name"] == "HQ"
        assert data["branchId"] == 1
        assert data["roomNumbersIncludeFloor"] is True
        assert data["rooms"] == [{"floor": 3, "rooms": 10}, {"floor": 2, "rooms": 10}, {"floor": 1, "rooms": 10},
                                 {"floor": -1, "rooms": 4}, {"floor": -2, "rooms": 0}]
        assert floors_of(db, data["id"]) == {3: 10, 2: 10, 1: 10, -1: 4, -2: 0}
        row = db.fetch_one("SELECT branch_id, floors, basement_floors, room_numbers_include_floor FROM buildings WHERE id = %s", (data["id"],))
        assert row == {"branch_id": 1, "floors": 3, "basement_floors": 2, "room_numbers_include_floor": True}

    def test_defaults(self, api, db, admin):
        status, data = api(handler, "POST", "/api/buildings", user=admin, body={"name": "Shed", "floors": 1})
        assert status == 201
        assert data["basementFloors"] == 0
        assert data["roomNumbersIncludeFloor"] is False
        assert data["rooms"] == [{"floor": 1, "rooms": 0}]

    def test_name_is_unique_per_branch_ignoring_case(self, api, db, admin):
        db.create_building(branch_id=1, name="HQ")
        db.create_user("facility_admin", branch_id=2)
        status, data = api(handler, "POST", "/api/buildings", user=admin, body={"name": "hq", "floors": 1})
        assert (status, data) == (409, {"error": "A building with that name already exists at your branch"})

        other_admin = db.create_user("facility_admin", branch_id=2)
        status, _ = api(handler, "POST", "/api/buildings", user=other_admin, body={"name": "HQ", "floors": 1})
        assert status == 201  # Miami may have its own HQ

    def test_validation_saves_nothing(self, api, db, admin):
        status, data = api(handler, "POST", "/api/buildings", user=admin, body={"name": "HQ", "floors": 2, "rooms": [{"floor": 3, "rooms": 1}]})
        assert status == 400
        assert data == {"error": "'rooms' names a floor this building does not have"}
        assert db.count("buildings") == 0

    def test_engineer_is_403(self, api, db):
        status, _ = api(handler, "POST", "/api/buildings", user=db.create_user("engineer"), body={"name": "HQ", "floors": 1})
        assert status == 403
        assert db.count("buildings") == 0


class TestUpdate:
    def test_fields_left_out_keep_their_value(self, api, db, admin):
        building = db.create_building(branch_id=1, name="HQ", floors=2, basement_floors=1, rooms={2: 8, 1: 6, -1: 2})
        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"name": "Head Office"})
        assert status == 200
        assert data["name"] == "Head Office"
        assert data["floors"] == 2 and data["basementFloors"] == 1
        assert floors_of(db, building["id"]) == {2: 8, 1: 6, -1: 2}

    def test_adding_floors_keeps_existing_room_counts(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=2, rooms={2: 8, 1: 6})
        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin,
                           body={"floors": 4, "basementFloors": 1, "rooms": [{"floor": 4, "rooms": 3}]})
        assert status == 200
        assert floors_of(db, building["id"]) == {4: 3, 3: 0, 2: 8, 1: 6, -1: 0}

    def test_removing_unused_floors_drops_their_rows(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=3, basement_floors=1)
        status, _ = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"floors": 1, "basementFloors": 0})
        assert status == 200
        assert floors_of(db, building["id"]) == {1: 0}

    def test_cannot_remove_a_floor_a_ticket_uses(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=5, basement_floors=2)
        db.create_location(building["id"], 4)
        db.create_location(building["id"], -2)

        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"floors": 3})
        assert (status, data) == (400, {"error": "'floors' cannot be less than 4: a ticket is on floor 4"})
        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"basementFloors": 1})
        assert (status, data) == (400, {"error": "'basementFloors' cannot be less than 2: a ticket is on floor B2"})
        assert floors_of(db, building["id"]) == {5: 0, 4: 0, 3: 0, 2: 0, 1: 0, -1: 0, -2: 0}

    def test_cannot_cut_rooms_below_one_in_use(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=2, rooms={2: 20})
        db.create_location(building["id"], 2, room=15)
        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"rooms": [{"floor": 2, "rooms": 10}]})
        assert (status, data) == (400, {"error": "Floor 2 cannot have fewer than 15 rooms: a ticket is in room 15"})
        # setting the floor to "unspecified" (0) is allowed
        status, _ = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"rooms": [{"floor": 2, "rooms": 0}]})
        assert status == 200

    def test_room_message_uses_the_buildings_numbering(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=5, rooms={5: 20}, include_floor=True)
        db.create_location(building["id"], 5, room=15)
        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"roomsPerFloor": 10})
        assert (status, data) == (400, {"error": "Floor 5 cannot have fewer than 15 rooms: a ticket is in room 515"})

    def test_turning_on_floor_numbering_converts_typed_rooms(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=6, rooms={5: 10})  # floor 6: any room number
        reporter = db.create_user()
        typed = db.create_location(building["id"], 5, room=502)      # typed as "502" on floor 5
        plain = db.create_location(building["id"], 5, room=3)        # already a plain index
        other_floor = db.create_location(building["id"], 6, room=502)  # leading digits are not its floor
        existing = db.create_location(building["id"], 5, room=7)
        duplicate = db.create_location(building["id"], 5, room=507)  # converts to 7, which already exists
        ticket = db.create_incident(reporter["id"], location_id=duplicate["id"])

        status, data = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"roomNumbersIncludeFloor": True})
        assert status == 200
        assert data["roomNumbersIncludeFloor"] is True
        rooms = {r["id"]: r["room"] for r in db.fetch_all("SELECT id, room FROM locations")}
        assert rooms[typed["id"]] == 2
        assert rooms[plain["id"]] == 3
        assert rooms[other_floor["id"]] == 502
        assert duplicate["id"] not in rooms  # merged into the existing row
        assert db.fetch_one("SELECT location_id FROM incidents WHERE id = %s", (ticket,))["location_id"] == existing["id"]

    def test_rename_to_a_taken_name_is_409_but_own_name_is_fine(self, api, db, admin):
        db.create_building(branch_id=1, name="Annex")
        building = db.create_building(branch_id=1, name="HQ")
        status, _ = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"name": "annex"})
        assert status == 409
        status, _ = api(handler, "PUT", f"/api/buildings/{building['id']}", user=admin, body={"name": "HQ", "floors": 2})
        assert status == 200

    def test_other_branch_404_and_role(self, api, db, admin):
        elsewhere = db.create_building(branch_id=2)
        status, _ = api(handler, "PUT", f"/api/buildings/{elsewhere['id']}", user=admin, body={"name": "X"})
        assert status == 403
        status, _ = api(handler, "PUT", "/api/buildings/9999", user=admin, body={"name": "X"})
        assert status == 404
        status, _ = api(handler, "PUT", f"/api/buildings/{elsewhere['id']}", user=db.create_user("engineer", branch_id=2), body={"name": "X"})
        assert status == 403


class TestDelete:
    def test_deletes_building_and_its_floors(self, api, db, admin):
        building = db.create_building(branch_id=1, floors=3)
        status, data = api(handler, "DELETE", f"/api/buildings/{building['id']}", user=admin)
        assert (status, data) == (204, None)
        assert db.count("buildings") == 0
        assert db.count("building_floors") == 0

    def test_building_with_tickets_is_409(self, api, db, admin):
        building = db.create_building(branch_id=1)
        location = db.create_location(building["id"], 1)
        db.create_incident(db.create_user()["id"], location_id=location["id"])
        status, data = api(handler, "DELETE", f"/api/buildings/{building['id']}", user=admin)
        assert status == 409
        assert db.count("buildings") == 1

    def test_other_branch_unknown_and_role(self, api, db, admin):
        elsewhere = db.create_building(branch_id=2)
        status, _ = api(handler, "DELETE", f"/api/buildings/{elsewhere['id']}", user=admin)
        assert status == 403
        status, _ = api(handler, "DELETE", "/api/buildings/9999", user=admin)
        assert status == 404
        status, _ = api(handler, "DELETE", f"/api/buildings/{elsewhere['id']}", user=db.create_user("employee", branch_id=2))
        assert status == 403
        assert db.count("buildings") == 1
