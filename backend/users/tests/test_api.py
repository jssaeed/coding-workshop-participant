"""
Integration tests for the users service: real handler, real PostgreSQL.

Each test starts with an empty test database (only the two branches exist)
and sets up its own accounts with the _testing.db factories.
"""

import jwt
import pytest

from _testing import db as testdb
from function import handler
from lib import auth

SIGNUP = {"email": "Ana@ACME.inc", "password": "hunter22!", "name": "Ana", "branchId": 1}


class TestBranches:
    def test_public_and_alphabetical(self, api):
        status, data = api(handler, "GET", "/api/users/branches")
        assert status == 200
        assert data == [{"id": 2, "name": "Miami"}, {"id": 1, "name": "Princeton-Plainsboro"}]


class TestSignup:
    def test_creates_and_persists_an_employee(self, api, db):
        status, data = api(handler, "POST", "/api/users", body=SIGNUP)
        assert status == 201
        assert data["email"] == "ana@acme.inc"
        assert data["role"] == "employee"
        assert data["branch"] == {"id": 1, "name": "Princeton-Plainsboro"}
        assert data["createdAt"] and data["updatedAt"]

        row = db.fetch_one("SELECT email, name, role, branch_id, password_hash FROM users WHERE id = %s", (data["id"],))
        assert row["email"] == "ana@acme.inc"
        assert row["role"] == "employee"
        assert row["password_hash"] != "hunter22!"
        assert auth.check_password("hunter22!", row["password_hash"])

    def test_duplicate_email_any_case_is_409(self, api, db):
        db.create_user(email="ana@acme.inc")
        status, data = api(handler, "POST", "/api/users", body=SIGNUP)
        assert status == 409
        assert db.count("users") == 1

    def test_unknown_branch_is_400(self, api, db):
        status, data = api(handler, "POST", "/api/users", body={**SIGNUP, "branchId": 99})
        assert status == 400
        assert data == {"error": "'branchId' does not match a known branch"}
        assert db.count("users") == 0

    def test_non_company_email_is_400(self, api, db):
        status, _ = api(handler, "POST", "/api/users", body={**SIGNUP, "email": "ana@example.com"})
        assert status == 400
        assert db.count("users") == 0


class TestLogin:
    def test_returns_tokens_that_work(self, api, db):
        user = db.create_user(email="ana@acme.inc", password="hunter22!")
        status, data = api(handler, "POST", "/api/users/login", body={"email": "ANA@acme.inc", "password": "hunter22!"})
        assert status == 200
        assert data["user"]["id"] == user["id"]
        assert data["user"]["branch"]["name"] == "Princeton-Plainsboro"

        status, me = api(handler, "GET", "/api/users/me", token=data["token"])
        assert status == 200
        assert me["email"] == "ana@acme.inc"

        # the refresh token is stored as a hash only
        rows = db.fetch_all("SELECT token_hash, revoked_at FROM refresh_tokens WHERE user_id = %s", (user["id"],))
        assert [r["token_hash"] for r in rows] == [auth.hash_refresh_token(data["refreshToken"])]
        assert rows[0]["revoked_at"] is None

    def test_wrong_password_is_401(self, api, db):
        db.create_user(email="ana@acme.inc", password="hunter22!")
        status, data = api(handler, "POST", "/api/users/login", body={"email": "ana@acme.inc", "password": "wrong-one"})
        assert status == 401
        assert data == {"error": "Email or password is incorrect"}
        assert db.count("refresh_tokens") == 0

    def test_login_deletes_stale_refresh_tokens(self, api, db):
        user = db.create_user(password="hunter22!")
        db.create_refresh_token(user["id"], expires_in_days=-1)   # expired
        db.create_refresh_token(user["id"], revoked=True)          # used or logged out
        live = db.create_refresh_token(user["id"])                 # still good
        api(handler, "POST", "/api/users/login", body={"email": user["email"], "password": "hunter22!"})
        hashes = {r["token_hash"] for r in db.fetch_all("SELECT token_hash FROM refresh_tokens")}
        assert auth.hash_refresh_token(live) in hashes
        assert len(hashes) == 2  # the live one plus the one login just issued


class TestRefresh:
    def test_each_refresh_token_works_exactly_once(self, api, db):
        user = db.create_user()
        token = db.create_refresh_token(user["id"])

        status, first = api(handler, "POST", "/api/users/refresh", body={"refreshToken": token})
        assert status == 200
        assert first["user"]["id"] == user["id"]
        assert first["refreshToken"] != token

        status, again = api(handler, "POST", "/api/users/refresh", body={"refreshToken": token})
        assert status == 401
        assert again == {"error": "Refresh token is invalid or expired"}

        status, _ = api(handler, "POST", "/api/users/refresh", body={"refreshToken": first["refreshToken"]})
        assert status == 200

    @pytest.mark.parametrize("kwargs", [{"expires_in_days": -1}, {"revoked": True}])
    def test_expired_or_revoked_token_is_401(self, api, db, kwargs):
        user = db.create_user()
        token = db.create_refresh_token(user["id"], **kwargs)
        status, _ = api(handler, "POST", "/api/users/refresh", body={"refreshToken": token})
        assert status == 401

    def test_new_access_token_carries_the_current_role(self, api, db):
        user = db.create_user(role="employee")
        token = db.create_refresh_token(user["id"])
        db.execute("UPDATE users SET role = 'engineer' WHERE id = %s", (user["id"],))
        status, data = api(handler, "POST", "/api/users/refresh", body={"refreshToken": token})
        assert status == 200
        assert jwt.decode(data["token"], auth.get_secret(), algorithms=["HS256"])["role"] == "engineer"
        assert data["user"]["role"] == "engineer"


class TestLogout:
    def test_revokes_the_refresh_token(self, api, db):
        user = db.create_user()
        token = db.create_refresh_token(user["id"])
        status, _ = api(handler, "POST", "/api/users/logout", body={"refreshToken": token})
        assert status == 204
        status, _ = api(handler, "POST", "/api/users/refresh", body={"refreshToken": token})
        assert status == 401


class TestMe:
    def test_deleted_account_is_401(self, api, db):
        user = db.create_user()
        token = db.token_for(user)
        db.execute("DELETE FROM users WHERE id = %s", (user["id"],))
        status, data = api(handler, "GET", "/api/users/me", token=token)
        assert (status, data) == (401, {"error": "Account no longer exists"})


class TestListUsers:
    def test_facility_admin_sees_only_their_branch_newest_first(self, api, db):
        admin = db.create_user("facility_admin", branch_id=1)
        here = db.create_user("employee", branch_id=1)
        db.create_user("employee", branch_id=2)
        status, data = api(handler, "GET", "/api/users", user=admin)
        assert status == 200
        assert [u["id"] for u in data] == [here["id"], admin["id"]]
        assert all(u["branch"]["id"] == 1 for u in data)

    def test_db_admin_sees_every_branch(self, api, db):
        root = db.create_user("db_admin", branch_id=1)
        db.create_user("employee", branch_id=1)
        db.create_user("engineer", branch_id=2)
        status, data = api(handler, "GET", "/api/users", user=root)
        assert status == 200
        assert len(data) == 3

    def test_role_filter(self, api, db):
        admin = db.create_user("facility_admin")
        engineer = db.create_user("engineer")
        db.create_user("employee")
        status, data = api(handler, "GET", "/api/users", user=admin, query={"role": "engineer"})
        assert status == 200
        assert [u["id"] for u in data] == [engineer["id"]]

    def test_employee_is_403(self, api, db):
        status, data = api(handler, "GET", "/api/users", user=db.create_user("employee"))
        assert (status, data) == (403, {"error": "Access denied"})


class TestRoles:
    def test_promotion_applies_on_the_users_next_request(self, api, db):
        admin = db.create_user("facility_admin")
        user = db.create_user("employee")
        old_token = db.token_for(user)  # issued while still an employee

        status, _ = api(handler, "GET", "/api/users", token=old_token)
        assert status == 403

        status, data = api(handler, "PUT", f"/api/users/{user['id']}/role", user=admin, body={"role": "facility_admin"})
        assert status == 200
        assert data["role"] == "facility_admin"

        status, _ = api(handler, "GET", "/api/users", token=old_token)
        assert status == 200  # same token, new powers

    def test_demotion_ends_the_users_sessions(self, api, db):
        admin = db.create_user("facility_admin")
        user = db.create_user("engineer")
        refresh = db.create_refresh_token(user["id"])

        status, _ = api(handler, "PUT", f"/api/users/{user['id']}/role", user=admin, body={"role": "employee"})
        assert status == 200
        assert db.fetch_one("SELECT role FROM users WHERE id = %s", (user["id"],))["role"] == "employee"

        status, _ = api(handler, "POST", "/api/users/refresh", body={"refreshToken": refresh})
        assert status == 401

    def test_promotion_keeps_the_users_sessions(self, api, db):
        admin = db.create_user("facility_admin")
        user = db.create_user("employee")
        refresh = db.create_refresh_token(user["id"])
        api(handler, "PUT", f"/api/users/{user['id']}/role", user=admin, body={"role": "engineer"})
        status, _ = api(handler, "POST", "/api/users/refresh", body={"refreshToken": refresh})
        assert status == 200

    def test_facility_admin_is_limited_to_their_branch_and_below_db_admin(self, api, db):
        admin = db.create_user("facility_admin", branch_id=1)
        elsewhere = db.create_user("employee", branch_id=2)
        root = db.create_user("db_admin", branch_id=1)
        local = db.create_user("employee", branch_id=1)

        status, _ = api(handler, "PUT", f"/api/users/{elsewhere['id']}/role", user=admin, body={"role": "engineer"})
        assert status == 403
        status, _ = api(handler, "PUT", f"/api/users/{root['id']}/role", user=admin, body={"role": "employee"})
        assert status == 403
        status, _ = api(handler, "PUT", f"/api/users/{local['id']}/role", user=admin, body={"role": "db_admin"})
        assert status == 400
        status, _ = api(handler, "PUT", f"/api/users/{admin['id']}/role", user=admin, body={"role": "employee"})
        assert status == 403
        status, _ = api(handler, "PUT", "/api/users/9999/role", user=admin, body={"role": "engineer"})
        assert status == 404
        # nothing changed
        roles = {r["id"]: r["role"] for r in db.fetch_all("SELECT id, role FROM users")}
        assert roles[elsewhere["id"]] == "employee" and roles[root["id"]] == "db_admin"

    def test_db_admin_manages_any_branch_and_can_make_db_admins(self, api, db):
        root = db.create_user("db_admin", branch_id=1)
        elsewhere = db.create_user("employee", branch_id=2)
        status, data = api(handler, "PUT", f"/api/users/{elsewhere['id']}/role", user=root, body={"role": "db_admin"})
        assert status == 200
        assert data["role"] == "db_admin"


class TestDelete:
    def test_history_is_kept_and_sessions_are_removed(self, api, db):
        admin = db.create_user("facility_admin")
        engineer = db.create_user("engineer")
        victim = db.create_user("employee")
        db.create_refresh_token(victim["id"])
        reported = db.create_incident(reported_by=victim["id"])
        assigned = db.create_incident(reported_by=admin["id"], assigned_to=victim["id"], status="assigned")
        db.create_message(reported, victim["id"], "hello")
        db.execute("INSERT INTO ticket_reads (user_id, incident_id) VALUES (%s, %s)", (victim["id"], reported))

        status, data = api(handler, "DELETE", f"/api/users/{victim['id']}", user=admin)
        assert (status, data) == (204, None)

        assert db.count("users", "id = %s", (victim["id"],)) == 0
        assert db.count("refresh_tokens", "user_id = %s", (victim["id"],)) == 0
        assert db.count("ticket_reads", "user_id = %s", (victim["id"],)) == 0
        assert db.fetch_one("SELECT reported_by FROM incidents WHERE id = %s", (reported,))["reported_by"] is None
        assert db.fetch_one("SELECT assigned_to FROM incidents WHERE id = %s", (assigned,))["assigned_to"] is None
        assert db.fetch_one("SELECT user_id, message FROM messages WHERE incident_id = %s", (reported,)) == {"user_id": None, "message": "hello"}
        assert db.count("incidents") == 2
        # untouched
        assert db.count("users", "id = %s", (engineer["id"],)) == 1

    def test_cannot_delete_yourself_or_across_branches(self, api, db):
        admin = db.create_user("facility_admin", branch_id=1)
        elsewhere = db.create_user("employee", branch_id=2)
        status, _ = api(handler, "DELETE", f"/api/users/{admin['id']}", user=admin)
        assert status == 403
        status, _ = api(handler, "DELETE", f"/api/users/{elsewhere['id']}", user=admin)
        assert status == 403
        status, _ = api(handler, "DELETE", "/api/users/9999", user=admin)
        assert status == 404
        assert db.count("users") == 2
