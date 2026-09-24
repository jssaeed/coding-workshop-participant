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
        assert [m["message"] for m in data["items"]] == ["first", "second", "third"]
        assert [m["author"]["role"] for m in data["items"]] == ["employee", "engineer", "facility_admin"]
        assert (data["total"], data["hasMore"]) == (3, False)

    def test_pages_walk_back_from_the_newest(self, api, db, people, ticket):
        """?limit= gives the newest page; ?before= the page of older ones ending just before a message."""
        for n in range(5):
            db.create_message(ticket, people["employee"]["id"], f"m{n}", created_seconds_ago=50 - n * 10)

        def page(**query):
            _, data = api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": str(ticket), **query})
            return [m["message"] for m in data["items"]], data["hasMore"], data["items"][0]["id"] if data["items"] else None

        texts, has_more, oldest = page(limit="2")
        assert (texts, has_more) == (["m3", "m4"], True)
        texts, has_more, oldest = page(limit="2", before=str(oldest))
        assert (texts, has_more) == (["m1", "m2"], True)
        texts, has_more, _ = page(limit="2", before=str(oldest))
        assert (texts, has_more) == (["m0"], False)

    def test_a_message_posted_while_reading_does_not_shift_the_pages(self, api, db, people, ticket):
        ids = [db.create_message(ticket, people["employee"]["id"], f"m{n}", created_seconds_ago=30 - n * 10) for n in range(3)]
        _, first = api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": str(ticket), "limit": "1"})
        assert [m["id"] for m in first["items"]] == [ids[2]]
        db.create_message(ticket, people["engineer"]["id"], "new")  # arrives now, newest of all
        _, older = api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": str(ticket), "limit": "1", "before": str(ids[2])})
        assert [m["id"] for m in older["items"]] == [ids[1]]  # not shifted by the new message
        assert older["total"] == 4

    def test_who_may_read(self, api, db, people, ticket):
        for who, expected in [("employee", 200), ("engineer", 200), ("admin", 200), ("outsider", 404), ("db_admin", 404)]:
            status, _ = api(handler, "GET", "/api/messages", user=people[who], query={"incidentId": str(ticket)})
            assert status == expected, who

    def test_deleted_author_shows_as_null(self, api, db, people, ticket):
        gone = db.create_user("engineer")
        db.create_message(ticket, gone["id"], "I was here")
        db.execute("DELETE FROM users WHERE id = %s", (gone["id"],))
        _, data = api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": str(ticket)})
        assert data["items"][0]["message"] == "I was here"
        assert data["items"][0]["author"] is None

    def test_missing_or_bad_incident_id(self, api, db, people):
        assert api(handler, "GET", "/api/messages", user=people["employee"])[0] == 400
        assert api(handler, "GET", "/api/messages", user=people["employee"], query={"incidentId": "abc"})[0] == 400
        assert api(handler, "GET", "/api/messages", user=people["admin"], query={"incidentId": "999"})[0] == 404
