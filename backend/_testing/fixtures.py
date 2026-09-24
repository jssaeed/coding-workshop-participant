"""
pytest fixtures shared by every service's test suite.

A service's tests/conftest.py does:

    from _testing.fixtures import *   # noqa: F401,F403

Fixtures:
  no_database   unit tests: the database is replaced by a fake that refuses
                to run SQL, so the test must mock the model functions it
                needs. Returns the FakeConnection (commits/rollbacks counted).
  db            integration tests: a real, empty test database with the
                schema applied. Skips when PostgreSQL is not reachable.
  api           integration tests: api(handler, method, path, user=..., ...)
                -> (status, payload), signing the request as `user`.
"""

import pytest

from _testing import db as testdb
from _testing import events
from _testing.fakes import install_fake_database

__all__ = ["no_database", "database_schema", "db", "api", "pytest_collection_modifyitems"]


def pytest_collection_modifyitems(items):
    """Mark every test that uses the db fixture as an integration test."""
    for item in items:
        if "db" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def no_database(monkeypatch):
    return install_fake_database(monkeypatch)


@pytest.fixture(scope="session")
def database_schema():
    reason = testdb.unavailable_reason()
    if reason:
        pytest.skip(reason)
    testdb.ensure_test_database()
    testdb.apply_schema()


@pytest.fixture
def db(database_schema):
    testdb.reset()
    yield testdb
    testdb.reset()


@pytest.fixture
def api(db):
    def send(handler, method="GET", path="/", user=None, token=None, **kwargs):
        if user is not None and token is None:
            token = testdb.token_for(user)
        return events.call(handler, method, path, token=token, **kwargs)

    return send
