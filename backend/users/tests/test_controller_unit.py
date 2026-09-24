"""
Unit tests for controllers/user_controller.py with the models mocked.

These check the rules (validation, who may do what, what gets revoked)
without a database. Persistence itself is covered by test_api.py.
"""

from datetime import datetime, timezone

import jwt
import pytest

from _testing.events import call
from _testing.fakes import sign_in_as, stub
from controllers import user_controller
from function import handler
from lib import auth
from models import branch as branch_model
from models import refresh_token as refresh_token_model
from models import user as user_model

NOW = datetime(2026, 9, 22, 14, 3, 11, tzinfo=timezone.utc)


def user_row(user_id=1, role="employee", branch_id=1, email=None, **extra):
    return {
        "id": user_id,
        "email": email or f"user{user_id}@acme.inc",
        "name": f"User {user_id}",
        "role": role,
        "branch_id": branch_id,
        "branch_name": "Princeton-Plainsboro" if branch_id == 1 else "Miami",
        "created_at": NOW,
        "updated_at": NOW,
        **extra,
    }


SIGNUP = {"email": "ana@acme.inc", "password": "hunter22!", "name": "Ana", "branchId": 1}


@pytest.fixture
def models(monkeypatch, no_database):
    """Every model function stubbed with a sensible default; tests override."""
    return {
        "branch": stub(monkeypatch, branch_model, "find_by_id", {"id": 1, "name": "Princeton-Plainsboro"}),
        "branches": stub(monkeypatch, branch_model, "list_all", [{"id": 2, "name": "Miami"}, {"id": 1, "name": "Princeton-Plainsboro"}]),
        "email_exists": stub(monkeypatch, user_model, "email_exists", False),
        "create": stub(monkeypatch, user_model, "create", side_effect=lambda **f: user_row(9, f["role"], f["branch_id"], f["email"])),
        "find_by_id": stub(monkeypatch, user_model, "find_by_id", user_row(9)),
        "for_login": stub(monkeypatch, user_model, "find_by_email_for_login", None),
        "list_all": stub(monkeypatch, user_model, "list_all", []),
        "update_role": stub(monkeypatch, user_model, "update_role", side_effect=lambda uid, role: user_row(uid, role)),
        "delete": stub(monkeypatch, user_model, "delete", 1),
        "token_create": stub(monkeypatch, refresh_token_model, "create"),
        "token_find": stub(monkeypatch, refresh_token_model, "find_valid", None),
        "token_revoke": stub(monkeypatch, refresh_token_model, "revoke"),
        "token_revoke_hash": stub(monkeypatch, refresh_token_model, "revoke_by_hash"),
        "token_revoke_all": stub(monkeypatch, refresh_token_model, "revoke_all_for_user"),
        "token_stale": stub(monkeypatch, refresh_token_model, "delete_stale", 0),
    }


class TestBranches:
    def test_public_list(self, models):
        status, data = call(handler, "GET", "/api/users/branches")
        assert status == 200
        assert data == [{"id": 2, "name": "Miami"}, {"id": 1, "name": "Princeton-Plainsboro"}]


class TestSignup:
    def test_creates_an_employee_at_the_chosen_branch(self, models):
        status, data = call(handler, "POST", "/api/users", body=SIGNUP)
        assert status == 201
        kwargs = models["create"].calls[0][1]
        assert kwargs["email"] == "ana@acme.inc"
        assert kwargs["name"] == "Ana"
        assert kwargs["branch_id"] == 1
        assert kwargs["role"] == "employee"
        assert data["role"] == "employee"
        assert data["branch"] == {"id": 1, "name": "Princeton-Plainsboro"}
        assert "password" not in data and "password_hash" not in data

    def test_password_is_stored_hashed(self, models):
        call(handler, "POST", "/api/users", body=SIGNUP)
        stored = models["create"].calls[0][1]["password_hash"]
        assert stored != "hunter22!"
        assert auth.check_password("hunter22!", stored)

    def test_role_in_the_body_is_ignored(self, models):
        status, data = call(handler, "POST", "/api/users", body={**SIGNUP, "role": "facility_admin"})
        assert status == 201
        assert models["create"].calls[0][1]["role"] == "employee"

    def test_email_is_lower_cased_before_checks(self, models):
        call(handler, "POST", "/api/users", body={**SIGNUP, "email": "Ana@ACME.INC"})
        assert models["email_exists"].calls[0][0] == ("ana@acme.inc",)
        assert models["create"].calls[0][1]["email"] == "ana@acme.inc"

    @pytest.mark.parametrize("changes, message", [
        ({"email": None}, "'email' is required"),
        ({"email": "ana"}, "'email' must be a valid email address"),
        ({"email": "ana@gmail.com"}, "'email' must be a company address ending in @acme.inc"),
        ({"password": "short"}, "'password' must be at least 8 characters"),
        ({"password": "x" * 73}, "'password' must be 72 bytes or fewer"),
        ({"name": "  "}, "'name' is required"),
        ({"branchId": None}, "'branchId' is required"),
        ({"branchId": "1"}, "'branchId' must be a positive whole number"),
    ])
    def test_validation_errors_name_the_field(self, models, changes, message):
        status, data = call(handler, "POST", "/api/users", body={**SIGNUP, **changes})
        assert status == 400
        assert data == {"error": message}
        assert models["create"].calls == []

    def test_unknown_branch(self, models, monkeypatch):
        stub(monkeypatch, branch_model, "find_by_id", None)
        status, data = call(handler, "POST", "/api/users", body={**SIGNUP, "branchId": 99})
        assert status == 400
        assert data == {"error": "'branchId' does not match a known branch"}

    def test_duplicate_email_is_409(self, models, monkeypatch):
        stub(monkeypatch, user_model, "email_exists", True)
        status, data = call(handler, "POST", "/api/users", body=SIGNUP)
        assert status == 409
        assert data == {"error": "An account with that email already exists"}

    def test_malformed_json_is_400(self, models):
        status, data = call(handler, "POST", "/api/users", raw_body="{oops")
        assert status == 400
        assert data == {"error": "Request body must be valid JSON"}


class TestLogin:
    @pytest.fixture
    def account(self, models, monkeypatch):
        row = user_row(9, password_hash=auth.hash_password("hunter22!"))
        stub(monkeypatch, user_model, "find_by_email_for_login", row)
        return row

    def test_returns_user_and_both_tokens(self, models, account):
        status, data = call(handler, "POST", "/api/users/login", body={"email": "user9@acme.inc", "password": "hunter22!"})
        assert status == 200
        assert data["user"]["id"] == 9
        claims = jwt.decode(data["token"], auth.get_secret(), algorithms=["HS256"])
        assert claims["sub"] == "9"
        assert claims["role"] == "employee"
        # only the refresh token's hash is stored
        (user_id, token_hash, expires_at), _ = models["token_create"].calls[0]
        assert user_id == 9
        assert token_hash == auth.hash_refresh_token(data["refreshToken"])
        assert expires_at > datetime.now(timezone.utc)

    def test_login_cleans_up_stale_refresh_tokens(self, models, account):
        call(handler, "POST", "/api/users/login", body={"email": "user9@acme.inc", "password": "hunter22!"})
        assert len(models["token_stale"].calls) == 1

    def test_wrong_password_and_unknown_email_look_the_same(self, models, account, monkeypatch):
        status1, data1 = call(handler, "POST", "/api/users/login", body={"email": "user9@acme.inc", "password": "nope-nope"})
        stub(monkeypatch, user_model, "find_by_email_for_login", None)
        status2, data2 = call(handler, "POST", "/api/users/login", body={"email": "ghost@acme.inc", "password": "hunter22!"})
        assert (status1, status2) == (401, 401)
        assert data1 == data2 == {"error": "Email or password is incorrect"}
        assert models["token_create"].calls == []

    def test_missing_password_is_400(self, models, account):
        status, data = call(handler, "POST", "/api/users/login", body={"email": "user9@acme.inc"})
        assert status == 400
        assert data == {"error": "'password' is required"}

    def test_login_is_one_transaction(self, models, account, no_database):
        call(handler, "POST", "/api/users/login", body={"email": "user9@acme.inc", "password": "hunter22!"})
        assert no_database.commits == 1


class TestRefresh:
    def test_missing_token_is_400(self, models):
        status, data = call(handler, "POST", "/api/users/refresh", body={})
        assert status == 400
        assert data == {"error": "'refreshToken' is required"}

    def test_unknown_token_is_401(self, models):
        status, data = call(handler, "POST", "/api/users/refresh", body={"refreshToken": "old"})
        assert status == 401
        assert data == {"error": "Refresh token is invalid or expired"}

    def test_rotates_the_token(self, models, monkeypatch):
        stub(monkeypatch, refresh_token_model, "find_valid", {"token_id": 55, **user_row(9)})
        status, data = call(handler, "POST", "/api/users/refresh", body={"refreshToken": "old"})
        assert status == 200
        assert models["token_revoke"].calls[0][0] == (55,)
        assert models["token_create"].calls[0][0][1] == auth.hash_refresh_token(data["refreshToken"])
        assert data["refreshToken"] != "old"
        assert jwt.decode(data["token"], auth.get_secret(), algorithms=["HS256"])["sub"] == "9"


class TestLogout:
    def test_revokes_the_given_token(self, models):
        status, data = call(handler, "POST", "/api/users/logout", body={"refreshToken": "abc"})
        assert (status, data) == (204, None)
        assert models["token_revoke_hash"].calls[0][0] == (auth.hash_refresh_token("abc"),)

    def test_without_a_token_is_still_204(self, models):
        status, _ = call(handler, "POST", "/api/users/logout", body={})
        assert status == 204
        assert models["token_revoke_hash"].calls == []


class TestMe:
    def test_returns_the_account_behind_the_token(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=9)
        status, data = call(handler, "GET", "/api/users/me")
        assert status == 200
        assert data["id"] == 9

    def test_deleted_account_is_401(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=9)
        stub(monkeypatch, user_model, "find_by_id", None)
        status, data = call(handler, "GET", "/api/users/me")
        assert status == 401


class TestListUsers:
    @pytest.mark.parametrize("role", ["employee", "engineer"])
    def test_only_admins(self, models, monkeypatch, role):
        sign_in_as(monkeypatch, role)
        status, data = call(handler, "GET", "/api/users")
        assert (status, data) == (403, {"error": "Access denied"})

    def test_facility_admin_sees_own_branch(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", branch_id=2)
        status, _ = call(handler, "GET", "/api/users", query={"role": "engineer"})
        assert status == 200
        assert models["list_all"].calls[0][0] == (2, "engineer")

    def test_db_admin_sees_every_branch(self, models, monkeypatch):
        sign_in_as(monkeypatch, "db_admin", branch_id=1)
        call(handler, "GET", "/api/users")
        assert models["list_all"].calls[0][0] == (None, None)

    def test_unknown_role_filter_is_400(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin")
        status, data = call(handler, "GET", "/api/users", query={"role": "boss"})
        assert status == 400
        assert data["error"].startswith("'role' must be one of")


class TestUpdateRole:
    def test_employee_may_not(self, models, monkeypatch):
        sign_in_as(monkeypatch, "employee")
        status, _ = call(handler, "PUT", "/api/users/9/role", body={"role": "engineer"})
        assert status == 403

    def test_promotion_keeps_sessions(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, user_model, "find_by_id", user_row(9, "employee"))
        status, data = call(handler, "PUT", "/api/users/9/role", body={"role": "engineer"})
        assert status == 200
        assert data["role"] == "engineer"
        assert models["update_role"].calls[0][0] == (9, "engineer")
        assert models["token_revoke_all"].calls == []

    def test_demotion_revokes_refresh_tokens(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, user_model, "find_by_id", user_row(9, "engineer"))
        status, _ = call(handler, "PUT", "/api/users/9/role", body={"role": "employee"})
        assert status == 200
        assert models["token_revoke_all"].calls[0][0] == (9,)

    def test_cannot_change_own_role(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        status, data = call(handler, "PUT", "/api/users/1/role", body={"role": "employee"})
        assert (status, data) == (403, {"error": "You cannot change your own role"})

    def test_unknown_user_is_404(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, user_model, "find_by_id", None)
        status, data = call(handler, "PUT", "/api/users/9/role", body={"role": "engineer"})
        assert (status, data) == (404, {"error": "User not found"})

    def test_unknown_role_is_400(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        status, data = call(handler, "PUT", "/api/users/9/role", body={"role": "boss"})
        assert status == 400
        assert data == {"error": "'role' must be one of: facility_admin, engineer, employee"}

    def test_facility_admin_cannot_hand_out_db_admin(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        status, _ = call(handler, "PUT", "/api/users/9/role", body={"role": "db_admin"})
        assert status == 400
        assert models["update_role"].calls == []

    def test_facility_admin_cannot_touch_another_branch(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1, branch_id=1)
        stub(monkeypatch, user_model, "find_by_id", user_row(9, "employee", branch_id=2))
        status, data = call(handler, "PUT", "/api/users/9/role", body={"role": "engineer"})
        assert (status, data) == (403, {"error": "That user belongs to another branch"})

    def test_facility_admin_cannot_touch_a_db_admin(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, user_model, "find_by_id", user_row(9, "db_admin"))
        status, _ = call(handler, "PUT", "/api/users/9/role", body={"role": "employee"})
        assert status == 403

    def test_db_admin_can_do_anything_anywhere(self, models, monkeypatch):
        sign_in_as(monkeypatch, "db_admin", user_id=1, branch_id=1)
        stub(monkeypatch, user_model, "find_by_id", user_row(9, "employee", branch_id=2))
        status, data = call(handler, "PUT", "/api/users/9/role", body={"role": "db_admin"})
        assert status == 200
        assert models["update_role"].calls[0][0] == (9, "db_admin")


class TestDeleteUser:
    def test_admin_deletes_a_user(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        status, data = call(handler, "DELETE", "/api/users/9")
        assert (status, data) == (204, None)
        assert models["delete"].calls[0][0] == (9,)

    def test_cannot_delete_yourself(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        status, data = call(handler, "DELETE", "/api/users/1")
        assert (status, data) == (403, {"error": "You cannot delete your own account"})
        assert models["delete"].calls == []

    def test_unknown_user_is_404(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1)
        stub(monkeypatch, user_model, "find_by_id", None)
        status, _ = call(handler, "DELETE", "/api/users/9")
        assert status == 404

    def test_other_branch_is_403(self, models, monkeypatch):
        sign_in_as(monkeypatch, "facility_admin", user_id=1, branch_id=1)
        stub(monkeypatch, user_model, "find_by_id", user_row(9, branch_id=2))
        status, _ = call(handler, "DELETE", "/api/users/9")
        assert status == 403

    def test_engineer_may_not(self, models, monkeypatch):
        sign_in_as(monkeypatch, "engineer", user_id=1)
        status, _ = call(handler, "DELETE", "/api/users/9")
        assert status == 403
