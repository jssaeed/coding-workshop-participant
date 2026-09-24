"""lib/request.py: reading the Lambda event."""

import pytest

from _testing.events import event
from lib.request import headers, http_method, json_body, path_id, path_segments, query_params
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
