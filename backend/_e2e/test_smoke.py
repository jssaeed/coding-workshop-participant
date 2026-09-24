"""
One pass through the main user journeys against a running server.

The tests run in file order and hand ids to each other through the `state`
fixture: a ticket is filed, then read, listed, commented on, and so on.
"""

import pytest

from conftest import PASSWORD


def expect(response, status, body=None):
    """
    Assert on status (and body). When the server answered with HTML instead
    of JSON the failure says so, because that is what a CloudFront 404 ->
    index.html fallback (meant for the React app) looks like on /api/*.
    """
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        pytest.fail(
            f"{response.request.method} {response.request.path_url} answered {response.status_code} with HTML, "
            f"not JSON. On the cloud this is CloudFront's 404 -> /index.html custom_error_response "
            f"(infra/cloudfront.tf) applying to /api/* as well as the app."
        )
    assert response.status_code == status, f"{response.status_code}: {response.text[:200]}"
    if body is not None:
        assert response.json() == body


def test_public_endpoint_answers_json(api):
    response = api.get("/api/users/branches")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert all({"id", "name"} <= set(branch) for branch in response.json())


def test_signup_creates_an_employee_and_duplicates_are_409(api, branch_id, people):
    reporter = people["reporter"]
    response = api.post("/api/users", json={"email": reporter["email"], "password": PASSWORD, "name": "Again", "branchId": branch_id})
    assert response.status_code == 409
    assert response.json() == {"error": "An account with that email already exists"}

    response = api.get("/api/users/me", token=reporter["token"])
    assert response.status_code == 200
    assert response.json()["role"] == "employee"
    assert response.json()["branch"]["id"] == branch_id


def test_login_rejects_a_wrong_password(api, people):
    response = api.post("/api/users/login", json={"email": people["reporter"]["email"], "password": "not-the-password"})
    assert response.status_code == 401
    assert response.json() == {"error": "Email or password is incorrect"}


def test_protected_endpoints_need_a_token(api):
    assert api.get("/api/users/me").status_code == 401
    assert api.get("/api/incidents").status_code == 401
    assert api.get("/api/inbox/count", token="not.a.token").status_code == 401


def test_file_a_ticket_and_read_it_back(api, people, state):
    reporter = people["reporter"]
    response = api.post("/api/incidents", token=reporter["token"], json={"title": "Smoke test ticket", "priority": 2})
    assert response.status_code == 201, response.text
    ticket = response.json()
    assert ticket["status"] == "open"
    assert ticket["priority"] == 2
    assert ticket["reportedBy"]["id"] == reporter["id"]
    state["ticket_id"] = ticket["id"]

    response = api.get(f"/api/incidents/{ticket['id']}", token=reporter["token"])
    assert response.status_code == 200
    assert response.json()["title"] == "Smoke test ticket"


def test_ticket_is_listed_under_mine(api, people, state):
    response = api.get("/api/incidents", token=people["reporter"]["token"], params={"status": "open"})
    assert response.status_code == 200
    assert state["ticket_id"] in [t["id"] for t in response.json()]


def test_a_stranger_gets_404_not_403(api, people, state):
    response = api.get(f"/api/incidents/{state['ticket_id']}", token=people["stranger"]["token"])
    expect(response, 404, {"error": "Incident not found"})
    response = api.get("/api/messages", token=people["stranger"]["token"], params={"incidentId": state["ticket_id"]})
    expect(response, 404, {"error": "Incident not found"})


def test_message_thread(api, people, state):
    reporter = people["reporter"]
    response = api.post("/api/messages", token=reporter["token"], json={"incidentId": state["ticket_id"], "message": "Still leaking."})
    assert response.status_code == 201, response.text
    assert response.json()["author"]["id"] == reporter["id"]

    response = api.get("/api/messages", token=reporter["token"], params={"incidentId": state["ticket_id"]})
    assert response.status_code == 200
    assert [m["message"] for m in response.json()] == ["Still leaking."]


def test_own_messages_do_not_show_in_the_inbox(api, people):
    response = api.get("/api/inbox/count", token=people["reporter"]["token"])
    assert response.status_code == 200
    assert response.json() == {"unread": 0}
    response = api.get("/api/inbox", token=people["reporter"]["token"])
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_buildings_and_stats_are_readable_by_any_user(api, people):
    response = api.get("/api/buildings", token=people["reporter"]["token"])
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = api.get("/api/incidents/stats/mine", token=people["reporter"]["token"], params={"days": 30})
    assert response.status_code == 200
    assert response.json()["reported"]["total"] >= 1
    assert response.json()["assigned"] is None  # employees are not assigned tickets


def test_error_responses_have_one_shape(api, people):
    token = people["reporter"]["token"]
    response = api.post("/api/incidents", token=token, json={"priority": 9})
    assert (response.status_code, response.json()) == (400, {"error": "'title' is required"})
    response = api.post("/api/incidents", token=token, data="{not json", headers={"Content-Type": "application/json"})
    assert (response.status_code, response.json()) == (400, {"error": "Request body must be valid JSON"})
    response = api.get("/api/incidents/999999999", token=token)
    expect(response, 404, {"error": "Incident not found"})
    response = api.delete("/api/incidents", token=token)
    assert (response.status_code, response.json()) == (405, {"error": "Method DELETE not allowed"})
    response = api.get("/api/incidents", token=token, params={"scope": "all"})
    assert (response.status_code, response.json()) == (403, {"error": "Access denied"})


def test_refresh_rotates_the_token(api, people):
    reporter = people["reporter"]
    response = api.post("/api/users/refresh", json={"refreshToken": reporter["refreshToken"]})
    assert response.status_code == 200, response.text
    fresh = response.json()
    assert fresh["token"] and fresh["refreshToken"] != reporter["refreshToken"]
    assert api.get("/api/users/me", token=fresh["token"]).status_code == 200

    response = api.post("/api/users/refresh", json={"refreshToken": reporter["refreshToken"]})
    assert response.status_code == 401  # the old one was used up
    reporter["refreshToken"] = fresh["refreshToken"]


def test_logout_revokes_the_refresh_token(api, people):
    stranger = people["stranger"]
    response = api.post("/api/users/logout", json={"refreshToken": stranger["refreshToken"]})
    assert response.status_code == 204
    response = api.post("/api/users/refresh", json={"refreshToken": stranger["refreshToken"]})
    assert response.status_code == 401


def test_db_admin_can_list_every_account(api, admin, people):
    if admin is None:
        pytest.skip("db admin credentials do not work on this server; set SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD")
    response = api.get("/api/users", token=admin)
    assert response.status_code == 200
    assert {people["reporter"]["id"], people["stranger"]["id"]} <= {u["id"] for u in response.json()}
