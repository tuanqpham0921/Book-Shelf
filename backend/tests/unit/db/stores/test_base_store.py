"""Tests for BaseStore.execute_statement — the single execute path every store
goes through.

The point of the funnel is that there is exactly one place to put what should
hold for every query. Today that is two things: the compiled SQL at DEBUG, and
the timeout. So the test that matters most is the last one here — that no store
method has quietly gone around it by calling `self.session.execute` itself.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from config import AppConfig
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

    async def test_a_statement_that_hangs_is_given_up_on(self, session, monkeypatch):
        """`asyncio.wait_for`, so the bound covers the whole await — including the
        wait for a connection out of the pool, which Postgres' own
        statement_timeout cannot see, because nothing has reached it yet.

        The bound is read off the constant rather than written here, so this fails
        if the timeout stops coming from config instead of passing vacuously.
        """
        monkeypatch.setattr(AppConfig, "DATABASE_TIMEOUT", 0.01)

        async def never_finishes(_):
            await asyncio.Event().wait()

        session.execute = never_finishes

        with pytest.raises(TimeoutError):
            await _Store(session).execute_statement(select(SessionModel))

    async def test_the_statement_is_cancelled_rather_than_left_running(
        self, session, monkeypatch
    ):
        """Which is also why a timed-out session is finished: SQLAlchemy no
        longer knows the connection's state, so the caller must let it go rather
        than retry on it. Every caller does — a store lives for one request."""
        monkeypatch.setattr(AppConfig, "DATABASE_TIMEOUT", 0.01)
        cancelled = asyncio.Event()

        async def never_finishes(_):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        session.execute = never_finishes

        with pytest.raises(TimeoutError):
            await _Store(session).execute_statement(select(SessionModel))

        assert cancelled.is_set()


class TestEveryStoreGoesThroughIt:
    def test_no_store_calls_session_execute_directly(self):
        """The funnel is only worth having if nothing bypasses it. A new store
        method that reaches for `self.session.execute` lands here.

        `check_connection` in db/async_engine.py is deliberately not covered: it
        is the readiness probe, has no store, and must answer whether the
        database is reachable at all rather than run a statement on one.
        """
        from pathlib import Path

        stores = Path(__file__).parents[4] / "db" / "stores"
        offenders = [
            path.name
            for path in sorted(stores.glob("*.py"))
            if "self.session.execute(" in path.read_text()
        ]

        assert offenders == ["base_store.py"]
