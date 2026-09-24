"""Unit tests for controllers/building_controller.py: the rules, without a database."""

import pytest

from _testing.events import call
from _testing.fakes import sign_in_as, stub
from controllers import building_controller as controller
from function import handler
from lib.responses import HttpError
from models import building as building_model

BODY = {"name": "HQ", "floors": 3, "basementFloors": 1, "roomsPerFloor": 10}


class TestFloorNumbers:
    def test_top_floor_first_then_basements(self):
        assert controller.floor_numbers(3, 2) == [3, 2, 1, -1, -2]

    def test_no_basements(self):
        assert controller.floor_numbers(2, 0) == [2, 1]


class TestRoomsFromBody:
    FLOORS = [3, 2, 1, -1]

    def test_nothing_given_keeps_existing_or_zero(self):
        assert controller.rooms_from_body({}, self.FLOORS, {3: 7}) == {3: 7, 2: 0, 1: 0, -1: 0}

    def test_rooms_per_floor_applies_everywhere(self):
        assert controller.rooms_from_body({"roomsPerFloor": 4}, self.FLOORS, {3: 7}) == {3: 4, 2: 4, 1: 4, -1: 4}

    def test_listed_floors_win_over_rooms_per_floor(self):
        body = {"roomsPerFloor": 4, "rooms": [{"floor": 3, "rooms": 9}, {"floor": -1, "rooms": 0}]}
        assert controller.rooms_from_body(body, self.FLOORS, {}) == {3: 9, 2: 4, 1: 4, -1: 0}

    def test_listed_floors_only_touch_themselves(self):
        assert controller.rooms_from_body({"rooms": [{"floor": 2, "rooms": 5}]}, self.FLOORS, {1: 8}) == {3: 0, 2: 5, 1: 8, -1: 0}

    @pytest.mark.parametrize("body, message", [
        ({"rooms": "many"}, "'rooms' must be a list of {floor, rooms}"),
        ({"rooms": [3]}, "'rooms' must be a list of {floor, rooms}"),
        ({"rooms": [{"floor": 9, "rooms": 1}]}, "'rooms' names a floor this building does not have"),
        ({"rooms": [{"floor": 0, "rooms": 1}]}, "'rooms' names a floor this building does not have"),
        ({"rooms": [{"floor": True, "rooms": 1}]}, "'rooms' names a floor this building does not have"),
        ({"rooms": [{"floor": 3}]}, "'rooms' is required"),
        ({"rooms": [{"floor": 3, "rooms": 501}]}, "'rooms' must be between 0 and 500"),
        ({"roomsPerFloor": -1}, "'roomsPerFloor' must be between 0 and 500"),
        ({"roomsPerFloor": "10"}, "'roomsPerFloor' must be a whole number"),
    ])
    def test_bad_input(self, body, message):
        with pytest.raises(HttpError) as raised:
            controller.rooms_from_body(body, self.FLOORS, {})
        assert (raised.value.status_code, raised.value.message) == (400, message)


class TestOptionalBool:
    def test_default_and_values(self):
        assert controller.optional_bool({}, "flag", default=True) is True
        assert controller.optional_bool({"flag": False}, "flag", default=True) is False

    @pytest.mark.parametrize("value", ["true", 1, 0])
    def test_rejects_non_booleans(self, value):
        with pytest.raises(HttpError) as raised:
            controller.optional_bool({"flag": value}, "flag", default=False)
        assert raised.value.message == "'flag' must be true or false"


class TestCreateRules:
    @pytest.mark.parametrize("role", ["employee", "engineer", "db_admin"])
    def test_only_a_facility_admin_may_create(self, no_database, monkeypatch, role):
        sign_in_as(monkeypatch, role)
        status, data = call(handler, "POST", "/api/buildings", body=BODY)
        assert (status, data) == (403, {"error": "Access denied"})

    @pytest.mark.parametrize("changes, message", [
        ({"name": ""}, "'name' is required"),
        ({"name": "x" * 101}, "'name' must be 100 characters or fewer"),
        ({"floors": None}, "'floors' is required"),
        ({"floors": 0}, "'floors' must be between 1 and 200"),
        ({"floors": 201}, "'floors' must be between 1 and 200"),
        ({"floors": "3"}, "'floors' must be a whole number"),
        ({"basementFloors": 21}, "'basementFloors' must be between 0 and 20"),
        ({"roomNumbersIncludeFloor": "yes"}, "'roomNumbersIncludeFloor' must be true or false"),
        ({"rooms": [{"floor": 4, "rooms": 1}]}, "'rooms' names a floor this building does not have"),
    ])
    def test_validation(self, no_database, monkeypatch, changes, message):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "POST", "/api/buildings", body={**BODY, **changes})
        assert (status, data) == (400, {"error": message})

    def test_duplicate_name_is_409(self, no_database, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", branch_id=2)
        taken = stub(monkeypatch, building_model, "name_taken", True)
        status, data = call(handler, "POST", "/api/buildings", body=BODY)
        assert status == 409
        assert taken.calls[0][0] == (2, "HQ")

    def test_created_at_the_admins_branch(self, no_database, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", branch_id=2)
        stub(monkeypatch, building_model, "name_taken", False)
        row = {"id": 5, "branch_id": 2, "name": "HQ", "floors": 3, "basement_floors": 1,
               "room_numbers_include_floor": False, "created_at": None, "updated_at": None}
        create = stub(monkeypatch, building_model, "create", row)
        replace = stub(monkeypatch, building_model, "replace_floors")
        stub(monkeypatch, building_model, "list_floors", [{"floor": 3, "rooms": 10}, {"floor": -1, "rooms": 10}])
        status, data = call(handler, "POST", "/api/buildings", body=BODY)
        assert status == 201
        assert create.calls[0][0] == (2, "HQ", 3, 1, False)
        assert replace.calls[0][0] == (5, {3: 10, 2: 10, 1: 10, -1: 10})
        assert data["branchId"] == 2
        assert data["rooms"] == [{"floor": 3, "rooms": 10}, {"floor": -1, "rooms": 10}]

    def test_create_is_one_transaction(self, no_database, monkeypatch):
        self.test_created_at_the_admins_branch(no_database, monkeypatch)
        assert no_database.commits == 1


class TestListRules:
    def test_any_signed_in_user_sees_their_branch(self, no_database, monkeypatch):
        sign_in_as(monkeypatch, "employee", branch_id=2)
        listed = stub(monkeypatch, building_model, "list_all", [])
        stub(monkeypatch, building_model, "list_floors_for", {})
        status, data = call(handler, "GET", "/api/buildings")
        assert (status, data) == (200, [])
        assert listed.calls[0][0] == (2,)


class TestDeleteRules:
    def test_employee_may_not(self, no_database, monkeypatch):
        sign_in_as(monkeypatch, "employee")
        status, _ = call(handler, "DELETE", "/api/buildings/1")
        assert status == 403

    def test_building_in_use_is_409(self, no_database, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", branch_id=1)
        stub(monkeypatch, building_model, "find_by_id", {"id": 1, "branch_id": 1})

        def in_use(building_id):
            raise building_model.BuildingInUse(building_id)

        stub(monkeypatch, building_model, "delete", side_effect=in_use)
        status, data = call(handler, "DELETE", "/api/buildings/1")
        assert (status, data) == (409, {"error": "Building has tickets located in it and cannot be deleted"})

    def test_other_branch_is_403(self, no_database, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", branch_id=1)
        stub(monkeypatch, building_model, "find_by_id", {"id": 1, "branch_id": 2})
        status, data = call(handler, "DELETE", "/api/buildings/1")
        assert (status, data) == (403, {"error": "That building belongs to another branch"})
