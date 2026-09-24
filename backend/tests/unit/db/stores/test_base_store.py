"""Tests for BaseStore.execute_statement — the single execute path every store
goes through.

The point of the funnel is that there is exactly one place to put what should
hold for every query. Today that is the compiled SQL at DEBUG; the timeout used
to live here too and now belongs to the engine (`db/async_engine.py`), because
Postgres cancelling its own query leaves the connection usable and
`asyncio.wait_for` did not.

So the tests that matter most are the last two — that no store method has
quietly gone around the funnel by calling `self.session.execute` itself, and
that none commits, since the transaction belongs to whoever opened the session.
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from db.schema import SessionModel
from db.stores.base_store import BaseStore


class _Store(BaseStore[SessionModel]):
    """A store with no methods of its own: the base class is what is under test."""

    def __init__(self, session):
        super().__init__(session, SessionModel)


@pytest.fixture
def session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(return_value="the result")
    return session


class TestExecuteStatement:
    async def test_it_runs_the_statement_and_returns_the_result(self, session):
        stmt = select(SessionModel)

        assert await _Store(session).execute_statement(stmt) == "the result"
        session.execute.assert_awaited_once_with(stmt)

    async def test_it_does_not_wrap_the_await_in_a_timeout(self, session):
        """The bound is the engine's now — Postgres' `statement_timeout` and
        asyncpg's `command_timeout`, both set in `get_async_engine`. Nothing
        here may cancel the await: a coroutine cancelled mid-execute leaves the
        connection in a state SQLAlchemy no longer knows, while the server
        cancelling its own query hands the connection back usable.

        Asserted as "the statement is awaited exactly once and returns", which
        is what a `wait_for` wrapper would change.
        """
        stmt = select(SessionModel)

        result = await _Store(session).execute_statement(stmt)

        assert result == "the result"
        session.execute.assert_awaited_once_with(stmt)

    async def test_it_logs_the_compiled_sql_at_debug(self, session, caplog):
        """The one thing the funnel is still for."""
        with caplog.at_level(logging.DEBUG, logger="db.stores.base_store"):
            await _Store(session).execute_statement(select(SessionModel.session_id))

        assert any("sessions.session_id" in record.message for record in caplog.records)


class TestEveryStoreGoesThroughIt:
    def test_no_store_calls_session_execute_directly(self):
        """The funnel is only worth having if nothing bypasses it. A new store
        method that reaches for `self.session.execute` lands here.

        `check_connection` in db/async_engine.py is deliberately not covered: it
        is the readiness probe, has no store, and must answer whether the
        database is reachable at all rather than run a statement on one.
        """
        assert _stores_containing("self.session.execute(") == ["base_store.py"]

    def test_no_store_commits_for_itself(self):
        """The transaction belongs to whoever opened the session — the
        `session_factory.begin()` block in `RequestContext.store` and in
        `get_sqlalchemy_session`, which commits on a clean exit.

        A store that commits mid-block closes that transaction early, and the
        next statement in the block then raises `InvalidRequestError`. It is a
        trap rather than a crash, which is why it is guarded here.
        """
        assert _stores_containing("self.session.commit(") == []


def _stores_containing(needle: str) -> list[str]:
    """The store modules whose source contains `needle`, by filename."""
    from pathlib import Path

    stores = Path(__file__).parents[4] / "db" / "stores"
    return [
        path.name
        for path in sorted(stores.glob("*.py"))
        if needle in path.read_text()
    ]
