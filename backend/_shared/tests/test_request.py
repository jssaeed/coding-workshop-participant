"""lib/request.py: reading the Lambda event."""

import pytest

from _testing.events import event
from lib.request import (choice_param, headers, http_method, int_param, json_body, page_params, path_id,
                         path_segments, positive_int_param, query_params, text_param)
from lib.responses import HttpError


class TestHttpMethod:
    def test_upper_cases_the_method(self):
        assert http_method(event("post")) == "POST"

    def test_defaults_to_get_when_missing(self):
        assert http_method({}) == "GET"


class TestPathSegments:
    @pytest.mark.parametrize("path, expected", [
        ("/api/incidents", []),
        ("/api/incidents/", []),
        ("/api/incidents/12", ["12"]),
        ("/api/incidents/12/status", ["12", "status"]),
        ("/incidents/12", ["12"]),          # without the /api prefix
        ("/", []),
        ("", []),
    ])
    def test_strips_the_service_prefix(self, path, expected):
        assert path_segments({"rawPath": path}, "incidents") == expected

    def test_other_service_name_is_kept(self):
        assert path_segments({"rawPath": "/api/users/5"}, "incidents") == ["users", "5"]


class TestPathId:
    def test_reads_a_positive_whole_number(self):
        assert path_id(["12", "status"]) == 12
        assert path_id(["12", "7"], index=1) == 7

    @pytest.mark.parametrize("segments", [[], ["abc"], ["0"], ["-3"], ["1.5"], [""]])
    def test_anything_else_is_404(self, segments):
        with pytest.raises(HttpError) as raised:
            path_id(segments)
        assert raised.value.status_code == 404


class TestQueryAndHeaders:
    def test_query_params_default_to_empty_dict(self):
        assert query_params({}) == {}
        assert query_params({"queryStringParameters": None}) == {}
        assert query_params(event(query={"status": "open"})) == {"status": "open"}

    def test_header_names_are_lower_cased(self):
        result = headers({"headers": {"Authorization": "Bearer x", "X-Thing": "1"}})
        assert result == {"authorization": "Bearer x", "x-thing": "1"}

    def test_missing_headers(self):
        assert headers({}) == {}
        assert headers({"headers": None}) == {}


class TestJsonBody:
    def test_empty_body_is_empty_dict(self):
        assert json_body({}) == {}
        assert json_body({"body": ""}) == {}
        assert json_body({"body": None}) == {}

    def test_parses_a_json_object(self):
        assert json_body(event(body={"a": 1})) == {"a": 1}

    def test_decodes_base64_bodies(self):
        assert json_body(event(body={"a": 1}, base64_body=True)) == {"a": 1}

    def test_invalid_json_is_400(self):
        with pytest.raises(HttpError) as raised:
            json_body(event(raw_body="{not json"))
        assert raised.value.status_code == 400
        assert raised.value.message == "Request body must be valid JSON"

    @pytest.mark.parametrize("raw", ["[1, 2]", '"text"', "42", "null"])
    def test_non_object_json_is_400(self, raw):
        with pytest.raises(HttpError) as raised:
            json_body(event(raw_body=raw))
        assert raised.value.status_code == 400
        assert raised.value.message == "Request body must be a JSON object"


class TestQueryParameters:
    def test_int_param_reads_a_number_in_range(self):
        assert int_param({"page": "3"}, "page", 1, 10) == 3
        assert int_param({}, "page", 1, 10, default=1) == 1
        assert int_param({"page": ""}, "page", 1, 10, default=7) == 7
        assert int_param({}, "page", 1, 10) is None

    @pytest.mark.parametrize("value", ["0", "11", "abc", "1.5", " 2", "-1"])
    def test_int_param_rejects_anything_else(self, value):
        with pytest.raises(HttpError) as raised:
            int_param({"page": value}, "page", 1, 10)
        assert (raised.value.status_code, raised.value.message) == (400, "'page' must be between 1 and 10")

    def test_positive_int_param_reads_an_id_or_nothing(self):
        assert positive_int_param({"buildingId": "2"}, "buildingId") == 2
        assert positive_int_param({"buildingId": ""}, "buildingId") is None
        assert positive_int_param({}, "buildingId") is None

    @pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", " 2"])
    def test_positive_int_param_rejects_anything_else(self, value):
        with pytest.raises(HttpError) as raised:
            positive_int_param({"buildingId": value}, "buildingId")
        assert (raised.value.status_code, raised.value.message) == (400, "'buildingId' must be a positive whole number")

    def test_page_params_defaults_and_offset(self):
        assert page_params({}) == (1, 25, 0)
        assert page_params({"page": "3", "limit": "10"}) == (3, 10, 20)
        assert page_params({"limit": "100"}) == (1, 100, 0)

    @pytest.mark.parametrize("params, message", [
        ({"page": "0"}, "'page' must be between 1 and 1000000"),
        ({"limit": "101"}, "'limit' must be between 1 and 100"),
        ({"limit": "0"}, "'limit' must be between 1 and 100"),
    ])
    def test_page_params_limits(self, params, message):
        with pytest.raises(HttpError) as raised:
            page_params(params)
        assert raised.value.message == message

    def test_choice_param(self):
        assert choice_param({"sort": "name"}, "sort", ["name", "created"]) == "name"
        assert choice_param({}, "sort", ["name"], default="name") == "name"
        assert choice_param({"sort": ""}, "sort", ["name"]) is None
        with pytest.raises(HttpError) as raised:
            choice_param({"sort": "age"}, "sort", ["name", "created"])
        assert raised.value.message == "'sort' must be one of: name, created"

    def test_text_param_trims_and_limits(self):
        assert text_param({"q": "  leak "}, "q") == "leak"
        assert text_param({"q": "   "}, "q") is None
        assert text_param({}, "q") is None
        with pytest.raises(HttpError) as raised:
            text_param({"q": "x" * 11}, "q", max_length=10)
        assert raised.value.message == "'q' must be 10 characters or fewer"
