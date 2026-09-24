"""
lib/database.py: the transaction rules, tested against a fake connection.

The rule under test: every helper finishes its own transaction (commit for
writes, rollback for reads) unless it runs inside "with transaction():", in
which case the block commits once at the end, or rolls back if anything
inside it raises.
"""

import pytest

from _testing.fakes import FakeConnection, FakeCursor
from lib import database


@pytest.fixture
def connection(monkeypatch):
    """A fake connection whose cursor replays canned rows."""
    cursor = FakeCursor(rows=[{"id": 1}, {"id": 2}], description=None, rowcount=2)
    fake = FakeConnection(cursor)
    fake.cursor_obj = cursor
    monkeypatch.setattr(database, "get_connection", lambda: fake)
    monkeypatch.setattr(database, "_in_transaction", False)
    return fake


class TestReads:
    def test_fetch_all_returns_rows_and_ends_the_transaction(self, connection):
        assert database.fetch_all("SELECT 1", (1,)) == [{"id": 1}, {"id": 2}]
        assert connection.cursor_obj.executed == [("SELECT 1", (1,))]
        assert (connection.commits, connection.rollbacks) == (0, 1)

    def test_fetch_one_returns_first_row(self, connection):
        assert database.fetch_one("SELECT 1") == {"id": 1}
        assert (connection.commits, connection.rollbacks) == (0, 1)

    def test_fetch_one_returns_none_when_empty(self, connection):
        connection.cursor_obj.rows = []
        assert database.fetch_one("SELECT 1") is None

    def test_read_error_rolls_back_and_re_raises(self, connection):
        connection.cursor_obj.error = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            database.fetch_all("SELECT 1")
        assert (connection.commits, connection.rollbacks) == (0, 1)


class TestWrites:
    def test_execute_with_returning_gives_the_row(self, connection):
        connection.cursor_obj.description = [("id",)]
        assert database.execute("INSERT ... RETURNING id") == {"id": 1}
        assert (connection.commits, connection.rollbacks) == (1, 0)

    def test_execute_without_returning_gives_the_row_count(self, connection):
        connection.cursor_obj.rowcount = 3
        assert database.execute("DELETE ...") == 3
        assert connection.commits == 1

    def test_execute_many_runs_every_statement_then_commits_once(self, connection):
        database.execute_many([("A", (1,)), ("B", (2,))])
        assert connection.cursor_obj.executed == [("A", (1,)), ("B", (2,))]
        assert (connection.commits, connection.rollbacks) == (1, 0)

    def test_write_error_rolls_back_and_re_raises(self, connection):
        connection.cursor_obj.error = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            database.execute("INSERT ...")
        assert (connection.commits, connection.rollbacks) == (0, 1)


class TestTransactionBlock:
    def test_commits_once_at_the_end(self, connection):
        with database.transaction():
            database.execute("A")
            database.fetch_one("B")
            database.execute("C")
            assert (connection.commits, connection.rollbacks) == (0, 0)
        assert (connection.commits, connection.rollbacks) == (1, 0)
        assert database._in_transaction is False

    def test_rolls_back_everything_when_the_block_raises(self, connection):
        with pytest.raises(ValueError):
            with database.transaction():
                database.execute("A")
                raise ValueError("half way")
        assert (connection.commits, connection.rollbacks) == (0, 1)
        assert database._in_transaction is False

    def test_a_failing_statement_inside_the_block_rolls_back_once(self, connection):
        with pytest.raises(RuntimeError):
            with database.transaction():
                database.execute("A")
                connection.cursor_obj.error = RuntimeError("boom")
                database.execute("B")
        assert (connection.commits, connection.rollbacks) == (0, 1)

    def test_nested_blocks_join_the_outer_one(self, connection):
        with database.transaction():
            with database.transaction():
                database.execute("A")
            assert connection.commits == 0  # inner block did not commit
        assert connection.commits == 1

    def test_flag_is_reset_after_the_block(self, connection):
        with database.transaction():
            assert database._in_transaction is True
        assert database._in_transaction is False
        database.fetch_one("A")
        assert connection.rollbacks == 1  # back to one transaction per helper


class TestConnection:
    def test_connection_string_uses_environment(self):
        assert "dbname=" in database.CONNECTION_STRING
        assert "connect_timeout=15" in database.CONNECTION_STRING
        assert "sslmode=disable" in database.CONNECTION_STRING  # IS_LOCAL=true in tests

    def test_get_connection_reuses_an_open_connection(self, monkeypatch):
        opened = []

        def connect(*args, **kwargs):
            opened.append(kwargs)
            return FakeConnection()

        monkeypatch.setattr(database, "connect", connect)
        monkeypatch.setattr(database, "_connection", None)
        first = database.get_connection()
        assert database.get_connection() is first
        assert len(opened) == 1
        assert "row_factory" in opened[0]

    def test_get_connection_reopens_a_closed_connection(self, monkeypatch):
        monkeypatch.setattr(database, "connect", lambda *a, **k: FakeConnection())
        monkeypatch.setattr(database, "_connection", None)
        first = database.get_connection()
        first.closed = True
        assert database.get_connection() is not first
