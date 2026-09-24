"""Unit tests for the inbox controller, model grouping and view, without a database."""

from datetime import datetime, timedelta, timezone

import pytest

from _testing.events import call
from _testing.fakes import sign_in_as, stub
from function import handler
from models import inbox as inbox_model
from views import inbox_view

NOW = datetime(2026, 9, 22, 15, 42, 37, tzinfo=timezone.utc)


def message(message_id, incident_id, text, author_id=7, seconds_ago=0):
    return {"id": message_id, "incident_id": incident_id, "message": text, "created_at": NOW - timedelta(seconds=seconds_ago),
            "author_id": author_id, "author_name": None if author_id is None else f"User {author_id}",
            "title": f"Ticket {incident_id}", "status": "open", "priority": 2}


class TestGrouping:
    def test_unread_by_ticket_groups_newest_first(self, monkeypatch, no_database):
        stub(monkeypatch, inbox_model, "unread_messages", [
            message(3, 12, "latest on 12", seconds_ago=0),
            message(2, 9, "only on 9", seconds_ago=5),
            message(1, 12, "older on 12", seconds_ago=10),
        ])
        entries = inbox_model.unread_by_ticket(4)
        assert [e["incident"]["id"] for e in entries] == [12, 9]
        assert entries[0]["unread_count"] == 2
        assert entries[0]["latest_message"]["message"] == "latest on 12"
        assert entries[0]["incident"] == {"id": 12, "title": "Ticket 12", "status": "open", "priority": 2}
        assert entries[1]["unread_count"] == 1

    def test_unread_count_is_one_count_query(self, monkeypatch, no_database):
        stub(monkeypatch, inbox_model, "fetch_one", {"n": 2})
        assert inbox_model.unread_count(4) == 2
        sql, params = inbox_model.fetch_one.calls[0][0]
        assert "COUNT(*)" in sql and params == {"user_id": 4}


class TestView:
    def test_serialize_inbox_totals_and_authors(self):
        entries = [
            {"incident": {"id": 12}, "unread_count": 2, "latest_message": {"message": "m", "created_at": NOW, "author_id": 7, "author_name": "Bob"}},
            {"incident": {"id": 9}, "unread_count": 1, "latest_message": {"message": "n", "created_at": NOW, "author_id": None, "author_name": None}},
        ]
        data = inbox_view.serialize_inbox(entries)
        assert data["unread"] == 3
        assert data["items"][0]["latestMessage"] == {"message": "m", "createdAt": NOW, "author": {"id": 7, "name": "Bob"}}
        assert data["items"][1]["latestMessage"]["author"] is None
        assert data["items"][1]["unreadCount"] == 1

    def test_empty_inbox(self):
        assert inbox_view.serialize_inbox([]) == {"unread": 0, "items": []}


class TestMarkReadRules:
    @pytest.fixture
    def models(self, monkeypatch, no_database):
        return {
            "incident": stub(monkeypatch, inbox_model, "find_basic_incident", {"id": 12, "reported_by": 4, "assigned_to": 7}),
            "mark": stub(monkeypatch, inbox_model, "mark_read", {"incident_id": 12, "last_read_at": NOW}),
            "count": stub(monkeypatch, inbox_model, "unread_count", 1),
        }

    @pytest.mark.parametrize("role, user_id, expected", [
        ("employee", 4, 200), ("engineer", 7, 200), ("facility_admin", 1, 200),
        ("employee", 5, 404), ("engineer", 8, 404), ("db_admin", 9, 404),
    ])
    def test_only_participants(self, models, monkeypatch, role, user_id, expected):
        sign_in_as(monkeypatch, role, user_id=user_id)
        status, data = call(handler, "PUT", "/api/inbox/12/read")
        assert status == expected
        if expected == 200:
            assert data == {"incidentId": 12, "lastReadAt": NOW.isoformat(), "unread": 1}
            assert models["mark"].calls[0][0] == (user_id, 12)

    def test_mark_read_is_one_transaction(self, models, monkeypatch, no_database):
        sign_in_as(monkeypatch, "employee", user_id=4)
        assert call(handler, "PUT", "/api/inbox/12/read")[0] == 200
        assert (no_database.commits, no_database.rollbacks) == (1, 0)

    def test_refused_mark_read_saves_nothing(self, models, monkeypatch, no_database):
        sign_in_as(monkeypatch, "employee", user_id=5)
        assert call(handler, "PUT", "/api/inbox/12/read")[0] == 404
        assert models["mark"].calls == []
        assert (no_database.commits, no_database.rollbacks) == (0, 1)

    def test_unknown_ticket(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        stub(monkeypatch, inbox_model, "find_basic_incident", None)
        assert call(handler, "PUT", "/api/inbox/12/read")[0] == 404

    def test_read_all_is_personal(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee", user_id=4)
        marked = stub(monkeypatch, inbox_model, "mark_all_read")
        status, data = call(handler, "PUT", "/api/inbox/read-all")
        assert (status, data) == (200, {"unread": 0})
        assert marked.calls[0][0] == (4,)
