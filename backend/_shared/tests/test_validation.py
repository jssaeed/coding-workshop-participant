"""lib/validation.py: one function per request field, 400 with the field's name."""

import pytest

from lib import validation
from lib.responses import HttpError


def rejects(function, *args, status=400, contains=None, **kwargs):
    with pytest.raises(HttpError) as raised:
        function(*args, **kwargs)
    assert raised.value.status_code == status
    if contains:
        assert contains in raised.value.message
    return raised.value.message


class TestRequiredString:
    def test_trims_the_value(self):
        assert validation.required_string({"name": "  Ana "}, "name") == "Ana"

    @pytest.mark.parametrize("body", [{}, {"name": None}, {"name": ""}, {"name": "   "}, {"name": 5}, {"name": ["a"]}])
    def test_missing_or_blank_or_not_text(self, body):
        assert rejects(validation.required_string, body, "name") == "'name' is required"

    def test_max_length(self):
        assert validation.required_string({"name": "a" * 10}, "name", max_length=10) == "a" * 10
        rejects(validation.required_string, {"name": "a" * 11}, "name", max_length=10,
                contains="10 characters or fewer")


class TestOptionalString:
    def test_missing_gives_empty_string(self):
        assert validation.optional_string({}, "note") == ""
        assert validation.optional_string({"note": None}, "note") == ""

    def test_trims_and_limits(self):
        assert validation.optional_string({"note": " hi "}, "note") == "hi"
        rejects(validation.optional_string, {"note": "abc"}, "note", max_length=2)

    def test_must_be_text(self):
        assert rejects(validation.optional_string, {"note": 1}, "note") == "'note' must be text"


class TestEmail:
    def test_lower_cases(self):
        assert validation.email({"email": " Ana@ACME.inc "}) == "ana@acme.inc"

    @pytest.mark.parametrize("value", ["bob@", "bob.example.com", "@acme.inc", "bob @acme.inc", "bob@acme"])
    def test_rejects_invalid_addresses(self, value):
        rejects(validation.email, {"email": value}, contains="valid email")

    def test_required(self):
        assert rejects(validation.email, {}) == "'email' is required"


class TestPassword:
    def test_accepts_eight_characters(self):
        assert validation.password({"password": "12345678"}) == "12345678"

    @pytest.mark.parametrize("body", [{}, {"password": ""}, {"password": None}, {"password": 12345678}])
    def test_required(self, body):
        assert rejects(validation.password, body) == "'password' is required"

    def test_too_short(self):
        rejects(validation.password, {"password": "1234567"}, contains="at least 8")

    def test_too_long_for_bcrypt(self):
        assert validation.password({"password": "a" * 72}) == "a" * 72
        rejects(validation.password, {"password": "a" * 73}, contains="72 bytes or fewer")

    def test_length_is_measured_in_bytes(self):
        # 25 three-byte characters = 75 bytes, over the bcrypt limit
        rejects(validation.password, {"password": "€" * 25}, contains="72 bytes")


class TestOneOf:
    def test_accepts_allowed_values(self):
        assert validation.one_of({"status": "open"}, "status", ["open", "closed"]) == "open"

    def test_default_when_missing(self):
        assert validation.one_of({}, "status", ["open"], default="open") == "open"

    def test_required_without_default(self):
        assert rejects(validation.one_of, {}, "status", ["open"]) == "'status' is required"

    def test_rejects_other_values(self):
        message = rejects(validation.one_of, {"status": "done"}, "status", ["open", "closed"])
        assert message == "'status' must be one of: open, closed"


class TestIntegerInRange:
    def test_accepts_bounds(self):
        assert validation.integer_in_range({"p": 1}, "p", 1, 5) == 1
        assert validation.integer_in_range({"p": 5}, "p", 1, 5) == 5

    def test_default(self):
        assert validation.integer_in_range({}, "p", 1, 5, default=3) == 3
        assert validation.integer_in_range({"p": None}, "p", 1, 5, default=3) == 3

    def test_required_without_default(self):
        assert rejects(validation.integer_in_range, {}, "p", 1, 5) == "'p' is required"

    @pytest.mark.parametrize("value", [True, False, "3", 3.0, [3]])
    def test_must_be_a_whole_number(self, value):
        assert rejects(validation.integer_in_range, {"p": value}, "p", 1, 5) == "'p' must be a whole number"

    @pytest.mark.parametrize("value", [0, 6, -1])
    def test_out_of_range(self, value):
        assert rejects(validation.integer_in_range, {"p": value}, "p", 1, 5) == "'p' must be between 1 and 5"


class TestIds:
    def test_optional_id(self):
        assert validation.optional_id({}, "x") is None
        assert validation.optional_id({"x": None}, "x") is None
        assert validation.optional_id({"x": 7}, "x") == 7

    @pytest.mark.parametrize("value", [0, -1, True, "7", 7.5])
    def test_optional_id_rejects_non_positive_or_non_int(self, value):
        assert rejects(validation.optional_id, {"x": value}, "x") == "'x' must be a positive whole number"

    def test_required_id(self):
        assert validation.required_id({"x": 3}, "x") == 3
        assert rejects(validation.required_id, {}, "x") == "'x' is required"
        rejects(validation.required_id, {"x": 0}, "x")
