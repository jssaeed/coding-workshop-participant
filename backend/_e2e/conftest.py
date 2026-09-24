"""
Smoke tests against a RUNNING server, local or cloud, over plain HTTP.

    API_BASE_URL=https://xxxx.cloudfront.net backend/.venv/bin/python -m pytest backend/_e2e
    ./bin/smoke-test.sh https://xxxx.cloudfront.net       (same thing)

Unlike the service suites these do not import any service code: they only
know the URL, so they prove what a deploy actually serves. They create their
own throw-away accounts (smoke-<id>@acme.inc) and, when the db admin
credentials work, delete them again at the end. Tickets and messages those
accounts made are kept by design (the API keeps history) and show up as
"Deleted user".
"""

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:3001").rstrip("/")
ADMIN_EMAIL = os.environ.get("SMOKE_ADMIN_EMAIL", "admin@admin.com")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "admin123")
PASSWORD = "smoke-test-pw1"
TIMEOUT = 20


class Api:
    """A thin client: api.get("/api/users/me", token=...) -> requests.Response."""

    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()

    def request(self, method, path, token=None, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.session.request(method, self.base_url + path, headers=headers, timeout=TIMEOUT, **kwargs)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def signup_and_login(self, branch_id, name):
        email = f"smoke-{uuid.uuid4().hex[:10]}@acme.inc"
        response = self.post("/api/users", json={"email": email, "password": PASSWORD, "name": name, "branchId": branch_id})
        assert response.status_code == 201, f"signup failed: {response.status_code} {response.text}"
        response = self.post("/api/users/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, f"login failed: {response.status_code} {response.text}"
        data = response.json()
        return {"id": data["user"]["id"], "email": email, "token": data["token"], "refreshToken": data["refreshToken"]}


@pytest.fixture(scope="session")
def api():
    client = Api(BASE_URL)
    try:
        response = client.get("/api/users/branches")
    except requests.RequestException as error:
        pytest.fail(f"{BASE_URL} is not reachable: {error}")
    assert response.status_code == 200, f"{BASE_URL}/api/users/branches answered {response.status_code}"
    return client


@pytest.fixture(scope="session")
def branch_id(api):
    return api.get("/api/users/branches").json()[0]["id"]


@pytest.fixture(scope="session")
def admin(api):
    """The db admin's token, or None when the credentials do not work here."""
    response = api.post("/api/users/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    return response.json()["token"] if response.status_code == 200 else None


@pytest.fixture(scope="session")
def people(api, branch_id, admin):
    """Two fresh accounts: the reporter, and a stranger who must not see their ticket."""
    created = {
        "reporter": api.signup_and_login(branch_id, "Smoke Reporter"),
        "stranger": api.signup_and_login(branch_id, "Smoke Stranger"),
    }
    yield created
    if admin:
        for person in created.values():
            api.delete(f"/api/users/{person['id']}", token=admin)


@pytest.fixture(scope="session")
def state():
    """Ids created by earlier tests in the file, for later ones to use."""
    return {}
