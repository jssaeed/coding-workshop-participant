"""lib/auth.py: passwords, access tokens, who is calling, and roles."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from _testing.events import event
from lib import auth
from lib.responses import HttpError

USER = {"id": 7, "email": "bob@acme.inc", "role": auth.ROLE_ENGINEER}
DB_ROW = {"id": 7, "email": "bob@acme.inc", "role": auth.ROLE_ENGINEER, "branch_id": 1}


@pytest.fixture
def users_table(monkeypatch):
    """Make current_user()'s database lookup return a chosen row (or None)."""
    holder = {"row": dict(DB_ROW), "queries": []}

    def fetch_one(sql, params):
        holder["queries"].append((sql, params))
        return holder["row"]

    monkeypatch.setattr(auth, "fetch_one", fetch_one)
    return holder


class TestPasswords:
    def test_hash_round_trip(self):
        hashed = auth.hash_password("hunter22!")
        assert hashed != "hunter22!"
        assert hashed.startswith("$2")
        assert auth.check_password("hunter22!", hashed)
        assert not auth.check_password("hunter23!", hashed)

    def test_each_hash_is_salted(self):
        assert auth.hash_password("same") != auth.hash_password("same")

    def test_damaged_hash_is_no_match(self):
        assert auth.check_password("anything", "not-a-bcrypt-hash") is False


class TestSecret:
    def test_environment_secret_wins(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "  from-env  ")
        assert auth.get_secret() == "from-env"

    def test_local_fallback_when_missing(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "")
        monkeypatch.setattr(auth, "IS_LOCAL", True)
        assert auth.get_secret() == auth.LOCAL_DEV_SECRET

    def test_cloud_without_secret_is_a_server_error(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.setattr(auth, "IS_LOCAL", False)
        with pytest.raises(HttpError) as raised:
            auth.get_secret()
        assert raised.value.status_code == 500


class TestAccessToken:
    def test_carries_id_email_role_and_expiry(self):
        token = auth.create_access_token(USER)
        claims = jwt.decode(token, auth.get_secret(), algorithms=["HS256"])
        assert claims["sub"] == "7"
        assert claims["email"] == "bob@acme.inc"
        assert claims["role"] == "engineer"
        lifetime = claims["exp"] - claims["iat"]
        assert lifetime == auth.ACCESS_TOKEN_LIFETIME.total_seconds()

    def test_is_signed_with_the_secret(self):
        token = auth.create_access_token(USER)
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "another-secret-that-is-also-long-enough-x", algorithms=["HS256"])


class TestCurrentUser:
    def test_valid_token_identifies_the_caller(self, users_table):
        token = auth.create_access_token(USER)
        caller = auth.current_user(event(token=token))
        assert caller == {"id": 7, "email": "bob@acme.inc", "role": "engineer", "branch_id": 1}
        # looked the user up by the id inside the token
        assert users_table["queries"][0][1] == (7,)

    def test_role_comes_from_the_database_not_the_token(self, users_table):
        users_table["row"]["role"] = auth.ROLE_ADMIN  # promoted since the token was issued
        token = auth.create_access_token(USER)       # token still says engineer
        assert auth.current_user(event(token=token))["role"] == auth.ROLE_ADMIN

    def test_missing_header_is_401(self, users_table):
        with pytest.raises(HttpError) as raised:
            auth.current_user(event())
        assert (raised.value.status_code, raised.value.message) == (401, "Authentication required")
        assert users_table["queries"] == []

    @pytest.mark.parametrize("value", ["Basic abc", "Token xyz", "eyJhbGciOi"])
    def test_non_bearer_header_is_401(self, users_table, value):
        with pytest.raises(HttpError) as raised:
            auth.current_user(event(headers={"Authorization": value}))
        assert raised.value.status_code == 401

    def test_header_name_and_scheme_are_case_insensitive(self, users_table):
        token = auth.create_access_token(USER)
        caller = auth.current_user(event(headers={"AUTHORIZATION": f"BEARER {token}"}))
        assert caller["id"] == 7

    def test_garbage_token_is_401(self, users_table):
        with pytest.raises(HttpError) as raised:
            auth.current_user(event(token="not.a.jwt"))
        assert (raised.value.status_code, raised.value.message) == (401, "Token is invalid")

    def test_token_signed_with_another_secret_is_401(self, users_table):
        forged = jwt.encode({"sub": "7", "role": "facility_admin"}, "wrong-secret-that-is-also-long-enough-xx", algorithm="HS256")
        with pytest.raises(HttpError) as raised:
            auth.current_user(event(token=forged))
        assert raised.value.message == "Token is invalid"

    def test_expired_token_says_so(self, users_table):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        expired = jwt.encode({"sub": "7", "iat": past - timedelta(minutes=15), "exp": past},
                             auth.get_secret(), algorithm="HS256")
        with pytest.raises(HttpError) as raised:
            auth.current_user(event(token=expired))
        assert (raised.value.status_code, raised.value.message) == (401, "Token has expired")

    def test_deleted_account_is_401(self, users_table):
        users_table["row"] = None
        with pytest.raises(HttpError) as raised:
            auth.current_user(event(token=auth.create_access_token(USER)))
        assert (raised.value.status_code, raised.value.message) == (401, "Account no longer exists")


class TestRefreshTokens:
    def test_token_is_random_and_only_its_hash_is_stored(self):
        token, token_hash, expires_at = auth.create_refresh_token()
        other, _, _ = auth.create_refresh_token()
        assert token != other
        assert len(token) >= 40
        assert token_hash == auth.hash_refresh_token(token)
        assert token not in token_hash
        remaining = expires_at - datetime.now(timezone.utc)
        assert timedelta(days=13, hours=23) < remaining <= auth.REFRESH_TOKEN_LIFETIME

    def test_hash_is_deterministic_sha256(self):
        assert auth.hash_refresh_token("abc") == auth.hash_refresh_token("abc")
        assert len(auth.hash_refresh_token("abc")) == 64


class TestRoles:
    def test_require_role(self):
        auth.require_role({"role": "engineer"}, ["engineer", "facility_admin"])
        with pytest.raises(HttpError) as raised:
            auth.require_role({"role": "employee"}, ["engineer"])
        assert (raised.value.status_code, raised.value.message) == (403, "Access denied")

    def test_role_predicates(self):
        assert auth.is_admin({"role": "facility_admin"})
        assert not auth.is_admin({"role": "db_admin"})  # a db admin is not facilities staff
        assert auth.is_db_admin({"role": "db_admin"})
        assert auth.is_staff({"role": "engineer"})
        assert auth.is_staff({"role": "facility_admin"})
        assert not auth.is_staff({"role": "employee"})
        assert not auth.is_staff({"role": "db_admin"})

    @pytest.mark.parametrize("old, new, expected", [
        ("facility_admin", "engineer", True),
        ("engineer", "employee", True),
        ("db_admin", "facility_admin", True),
        ("employee", "engineer", False),
        ("engineer", "engineer", False),
        ("employee", "db_admin", False),
    ])
    def test_is_demotion(self, old, new, expected):
        assert auth.is_demotion(old, new) is expected

    def test_role_lists(self):
        assert auth.ROLE_DB_ADMIN not in auth.BRANCH_ROLES
        assert set(auth.BRANCH_ROLES) | {auth.ROLE_DB_ADMIN} == set(auth.ALL_ROLES)
        assert set(auth.STAFF_ROLES) == {auth.ROLE_ADMIN, auth.ROLE_ENGINEER}
