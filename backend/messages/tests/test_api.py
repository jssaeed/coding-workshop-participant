"""Integration tests for the messages service: real handler, real PostgreSQL."""

import pytest

from function import handler


@pytest.fixture
def people(db):
    return {
        "admin": db.create_user("facility_admin"),
        "engineer": db.create_user("engineer"),
        "employee": db.create_user("employee"),
        "outsider": db.create_user("employee"),
        "db_admin": db.create_user("db_admin"),
    }


@pytest.fixture
def ticket(db, people):
    return db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")


class TestPost:
    def test_reporter_posts_and_the_message_is_saved(self, api, db, people, ticket):
        status, data = api(handler, "POST", "/api/messages", user=people["employee"], body={"incidentId": ticket, "message": " On my way up. "})
        assert status == 201
        assert data["incidentId"] == ticket
        assert data["message"] == "On my way up."
        assert data["author"] == {"id": people["employee"]["id"], "name": people["employee"]["name"], "email": people["employee"]["email"], "role": "employee"}
        assert data["createdAt"] and data["updatedAt"]
        assert db.fetch_one("SELECT user_id, message FROM messages WHERE id = %s", (data["id"],)) == {"user_id": people["employee"]["id"], "message": "On my way up."}

    def test_who_may_post(self, api, db, people, ticket):
        for who, expected in [("engineer", 201), ("admin", 201), ("outsider", 404), ("db_admin", 404)]:
            status, _ = api(handler, "POST", "/api/messages", user=people[who], body={"incidentId": ticket, "message": "Hi"})
            assert status == expected, who
        assert db.count("messages") == 2

    def test_closed_ticket_is_409(self, api, db, people):
        closed = db.create_incident(people["employee"]["id"], status="closed")
        status, data = api(handler, "POST", "/api/messages", user=people["employee"], body={"incidentId": closed, "message": "Hi"})
        assert (status, data) == (409, {"error": "Incident is closed and cannot receive new messages"})
        assert db.count("messages") == 0

    def test_unknown_ticket_and_bad_input(self, api, db, people, ticket):
        assert api(handler, "POST", "/api/messages", user=people["admin"], body={"incidentId": 999, "message": "Hi"})[0] == 404
        assert api(handler, "POST", "/api/messages", user=people["admin"], body={"incidentId": ticket, "message": ""})[0] == 400
        assert api(handler, "POST", "/api/messages", user=people["admin"], body={"incidentId": ticket, "message": "x" * 5001})[0] == 400
        assert db.count("messages") == 0


class TestRead:
    def test_thread_is_oldest_first_with_authors(self, api, db, people, ticket):
        db.create_message(ticket, people["employee"]["id"], "first", created_seconds_ago=30)
        db.create_message(ticket, people["engineer"]["id"], "second", created_seconds_ago=20)
        db.create_message(ticket, people["admin"]["id"], "third", created_seconds_ago=10)
        status, data = api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": str(ticket)})
        assert status == 200
        assert [m["message"] for m in data] == ["first", "second", "third"]
        assert [m["author"]["role"] for m in data] == ["employee", "engineer", "facility_admin"]

    def test_who_may_read(self, api, db, people, ticket):
        for who, expected in [("employee", 200), ("engineer", 200), ("admin", 200), ("outsider", 404), ("db_admin", 404)]:
            status, _ = api(handler, "GET", "/api/messages", user=people[who], query={"incidentId": str(ticket)})
            assert status == expected, who

    def test_deleted_author_shows_as_null(self, api, db, people, ticket):
        gone = db.create_user("engineer")
        db.create_message(ticket, gone["id"], "I was here")
        db.execute("DELETE FROM users WHERE id = %s", (gone["id"],))
        _, data = api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": str(ticket)})
        assert data[0]["message"] == "I was here"
        assert data[0]["author"] is None

    def test_missing_or_bad_incident_id(self, api, db, people):
        assert api(handler, "GET", "/api/messages", user=people["employee"])[0] == 400
        assert api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": "abc"})[0] == 400
        assert api(handler, "GET", "/api/messages", user=people["admin"], query={"incidentId": "999"})[0] == 404
