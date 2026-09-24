"""
Stand-ins for the database, for unit tests that must not touch PostgreSQL.

install_fake_database() replaces lib.database.get_connection with one that
returns a FakeConnection. The connection accepts commit()/rollback() (so
"with transaction():" blocks in controllers work) but refuses to open a
cursor, so any model call a test forgot to mock fails loudly instead of
silently reaching a real database.
"""

import types

import lib.auth as auth
import lib.database as database


class FakeCursor:
    """A cursor that replays canned results, for testing lib.database itself."""

    def __init__(self, rows=None, description=None, rowcount=0, error=None):
        self.rows = list(rows or [])
        self.description = description
        self.rowcount = rowcount
        self.error = error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.error is not None:
            raise self.error

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    """Counts commits and rollbacks; refuses to run SQL unless given a cursor."""

    def __init__(self, cursor=None):
        self.closed = False
        self.commits = 0
        self.rollbacks = 0
        self._cursor = cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def cursor(self):
        if self._cursor is None:
            raise AssertionError(
                "unit test reached the database: mock the model function this code path calls"
            )
        return self._cursor


def install_fake_database(monkeypatch, cursor=None):
    """Make every lib.database helper use a FakeConnection. Returns it."""
    fake = FakeConnection(cursor)
    monkeypatch.setattr(database, "get_connection", lambda: fake)
    monkeypatch.setattr(database, "_connection", None)
    monkeypatch.setattr(database, "_in_transaction", False)
    return fake


def caller(role=auth.ROLE_EMPLOYEE, user_id=1, branch_id=1, email=None, name=None):
    """The dict lib.auth.current_user() returns for a signed-in user."""
    return {
        "id": user_id,
        "email": email or f"user{user_id}@acme.inc",
        "role": role,
        "branch_id": branch_id,
        "name": name or f"User {user_id}",
    }


def sign_in_as(monkeypatch, role=auth.ROLE_EMPLOYEE, **fields):
    """
    Make lib.auth.current_user() return a fixed caller for every request,
    without a token or a database. Returns the caller dict.
    """
    user = caller(role, **fields)
    monkeypatch.setattr(auth, "current_user", lambda event: dict(user))
    return user


def stub(monkeypatch, module, name, result=None, side_effect=None):
    """
    Replace module.name with a recording stub.

    The stub returns `result`, or calls side_effect(*args, **kwargs) when
    given. Every call is appended to stub.calls as (args, kwargs).
    """
    calls = []

    def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        if side_effect is not None:
            return side_effect(*args, **kwargs)
        return result

    replacement.calls = calls
    monkeypatch.setattr(module, name, replacement)
    return replacement


def namespace(**fields):
    return types.SimpleNamespace(**fields)
