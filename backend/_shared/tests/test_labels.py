"""lib/labels.py: how floors and rooms are written for people."""

import pytest

from lib.labels import floor_label, room_digits, room_label


@pytest.mark.parametrize("floor, expected", [(3, "3"), (1, "1"), (-1, "B1"), (-2, "B2"), (200, "200")])
def test_floor_label(floor, expected):
    assert floor_label(floor) == expected


@pytest.mark.parametrize("max_rooms, expected", [(None, 2), (0, 2), (99, 2), (100, 3), (500, 3)])
def test_room_digits(max_rooms, expected):
    assert room_digits(max_rooms) == expected


class TestRoomLabel:
    def test_no_room(self):
        assert room_label(5, None, True, 10) is None

    def test_plain_index_when_building_does_not_number_by_floor(self):
        assert room_label(5, 1, False, 10) == "1"
        assert room_label(-1, 12, False, 10) == "12"

    def test_two_digit_rooms_under_a_hundred(self):
        assert room_label(5, 1, True, 99) == "501"
        assert room_label(5, 12, True, 99) == "512"
        assert room_label(12, 3, True, 10) == "1203"

    def test_three_digit_rooms_from_a_hundred(self):
        assert room_label(5, 1, True, 100) == "5001"
        assert room_label(5, 123, True, 150) == "5123"

    def test_basement_rooms(self):
        assert room_label(-1, 1, True, 10) == "B101"
        assert room_label(-2, 7, True, 100) == "B2007"

    def test_missing_max_rooms_means_two_digits(self):
        assert room_label(3, 4, True, None) == "304"
