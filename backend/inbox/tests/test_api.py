"""
Integration tests for the inbox service: real handler, real PostgreSQL.

The rule: a message is unread for you when it is on a ticket you reported or
are assigned to, someone else wrote it, and it is newer than the last time
you opened that ticket.
"""

import pytest

from function import handler


@pytest.fixture
def people(db):
    return {
        "admin": db.create_user("facility_admin"),
        "engineer": db.create_user("engineer"),
        "employee": db.create_user("employee"),
        "outsider": db.create_user("employee"),
        "miami_admin": db.create_user("facility_admin", branch_id=2),  # the ticket is at branch 1
    }


@pytest.fixture
def ticket(db, people):
    return db.create_incident(people["employee"]["id"], assigned_to=people["engineer"]["id"], status="assigned")


def unread(api, user):
    return api(handler, "GET", "/api/inbox/count", user=user)[1]["unread"]


class TestWhatCountsAsUnread:
    def test_someone_elses_message_on_my_ticket(self, api, db, people, ticket):
        db.create_message(ticket, people["engineer"]["id"])
        assert unread(api, people["employee"]) == 1   # reporter
        assert unread(api, people["engineer"]) == 0   # wrote it themselves
        assert unread(api, people["admin"]) == 0      # not involved: the inbox is personal, admins get no special view
        assert unread(api, people["outsider"]) == 0

    def test_assignee_sees_the_reporters_message(self, api, db, people, ticket):
        db.create_message(ticket, people["employee"]["id"])
        assert unread(api, people["engineer"]) == 1
        assert unread(api, people["employee"]) == 0

    def test_status_changes_count_because_they_are_messages(self, api, db, people, ticket):
        db.create_message(ticket, people["admin"]["id"], f"Ticket #{ticket}: status changed to in progress")
        assert unread(api, people["employee"]) == 1
        assert unread(api, people["engineer"]) == 1

    def test_a_deleted_authors_message_still_counts(self, api, db, people, ticket):
        db.create_message(ticket, None, "from a deleted account")
        assert unread(api, people["employee"]) == 1
        _, data = api(handler, "GET", "/api/inbox", user=people["employee"])
        assert data["items"][0]["latestMessage"]["author"] is None

    def test_tickets_i_am_not_on_never_count(self, api, db, people):
        other = db.create_incident(people["outsider"]["id"])
        db.create_message(other, people["admin"]["id"])
        assert unread(api, people["employee"]) == 0


class TestMarkingRead:
    def test_mark_read_then_new_messages_count_again(self, api, db, people, ticket):
        db.create_message(ticket, people["engineer"]["id"], "one", created_seconds_ago=20)
        db.create_message(ticket, people["engineer"]["id"], "two", created_seconds_ago=10)
        other = db.create_incident(people["employee"]["id"])
        db.create_message(other, people["admin"]["id"], "elsewhere", created_seconds_ago=5)
        assert unread(api, people["employee"]) == 3

        status, data = api(handler, "PUT", f"/api/inbox/{ticket}/read", user=people["employee"])
        assert status == 200
        assert data["incidentId"] == ticket
        assert data["lastReadAt"]
        assert data["unread"] == 1  # the message on the other ticket remains
        assert db.count("ticket_reads", "user_id = %s AND incident_id = %s", (people["employee"]["id"], ticket)) == 1

        db.execute("INSERT INTO messages (incident_id, user_id, message, created_at) VALUES (%s, %s, 'three', NOW() + interval '1 second')", (ticket, people["engineer"]["id"]))
        assert unread(api, people["employee"]) == 2

        # marking read again updates the same row rather than adding one
        api(handler, "PUT", f"/api/inbox/{ticket}/read", user=people["employee"])
        assert db.count("ticket_reads", "user_id = %s", (people["employee"]["id"],)) == 1

    def test_read_all(self, api, db, people, ticket):
        db.create_message(ticket, people["engineer"]["id"])
        other = db.create_incident(people["employee"]["id"])
        db.create_message(other, people["admin"]["id"])
        assert unread(api, people["employee"]) == 2
        status, data = api(handler, "PUT", "/api/inbox/read-all", user=people["employee"])
        assert (status, data) == (200, {"unread": 0})
        assert unread(api, people["employee"]) == 0
        # only the caller's marks were touched
        assert db.count("ticket_reads", "user_id = %s", (people["employee"]["id"],)) == 2
        assert db.count("ticket_reads", "user_id <> %s", (people["employee"]["id"],)) == 0

    def test_who_may_mark_a_ticket_read(self, api, db, people, ticket):
        for who, expected in [("employee", 200), ("engineer", 200), ("admin", 200), ("outsider", 404), ("miami_admin", 404)]:
            assert api(handler, "PUT", f"/api/inbox/{ticket}/read", user=people[who])[0] == expected, who
        assert api(handler, "PUT", "/api/inbox/999/read", user=people["admin"])[0] == 404
        assert db.count("ticket_reads", "user_id = %s", (people["outsider"]["id"],)) == 0


class TestListing:
    def test_grouped_by_ticket_most_recent_first(self, api, db, people, ticket):
        quiet = db.create_incident(people["employee"]["id"], title="Quiet one", priority=1)
        db.create_message(ticket, people["engineer"]["id"], "older", created_seconds_ago=30)
        db.create_message(quiet, people["admin"]["id"], "middle", created_seconds_ago=20)
        db.create_message(ticket, people["engineer"]["id"], "newest", created_seconds_ago=10)
        db.create_message(ticket, people["employee"]["id"], "my own reply", created_seconds_ago=5)

        status, data = api(handler, "GET", "/api/inbox", user=people["employee"])
        assert status == 200
        assert data["unread"] == 3
        assert [item["incident"]["id"] for item in data["items"]] == [ticket, quiet]
        first = data["items"][0]
        assert first["unreadCount"] == 2
        assert first["incident"]["status"] == "assigned"
        assert first["latestMessage"]["message"] == "newest"
        assert first["latestMessage"]["author"] == {"id": people["engineer"]["id"], "name": people["engineer"]["name"]}
        second = data["items"][1]
        assert second["incident"] == {"id": quiet, "title": "Quiet one", "status": "open", "priority": 1}
        assert second["unreadCount"] == 1

    def test_empty(self, api, db, people):
        status, data = api(handler, "GET", "/api/inbox", user=people["employee"])
        assert (status, data) == (200, {"unread": 0, "items": []})
