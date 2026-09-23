"""Tests for SessionStore — the statements a session's token budget is kept by.

The session is an AsyncMock rather than a database: what these assert is the SQL
that *would* be sent, which is the established shape for store tests here. That
is the whole point for `debit`, whose correctness **is** the shape of the
statement — the subtraction has to happen in Postgres, because two turns
overlapping in one session hold separate database sessions and a read-modify-write
would lose one of the charges.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from config import AppConfig
from db.schema import SessionModel
from db.stores.session_store import SessionStore


@pytest.fixture
def session() -> MagicMock:
    """A stand-in for the AsyncSession: awaiting it works, nothing is executed.

    Only the two methods the store awaits are async, and `execute` resolves to a
    plain MagicMock: every child of an AsyncMock is async too, which would make
    `result.scalar_one_or_none()` a coroutine nobody awaits.
    """
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    return session


def statement_of(session):
    """The statement the store handed to `session.execute`."""
    return session.execute.call_args.args[0]


def sql_of(session) -> str:
    """That statement as Postgres would receive it."""
    return str(statement_of(session).compile(dialect=postgresql.dialect()))


class TestDebit:
    """The charge itself."""

    @pytest.fixture(autouse=True)
    async def charged(self, session):
        await SessionStore(session).debit("sess_1", 500)

    async def test_the_subtraction_happens_in_sql(self, session):
        """Not in Python. This is the assertion the method exists for."""
        assert "remaining_tokens=(sessions.remaining_tokens - " in sql_of(session)

    async def test_it_returns_the_new_balance(self, session):
        # so the caller can log what is left without a second round trip
        assert "RETURNING sessions.remaining_tokens" in sql_of(session)

    async def test_it_touches_last_updated(self, session):
        assert "last_updated=now()" in sql_of(session)

    async def test_it_charges_only_the_one_session(self, session):
        assert "WHERE sessions.session_id = " in sql_of(session)

    async def test_the_amount_is_the_spend_it_was_given(self, session):
        assert 500 in statement_of(session).compile().params.values()

    async def test_it_does_not_commit(self, session):
        """The `session_factory.begin()` block this store is built inside owns
        the transaction and commits it on exit. Committing here would close
        that transaction early, and the next statement in the block would
        raise."""
        session.commit.assert_not_awaited()


class TestDebitReturnValue:
    async def test_a_missing_row_comes_back_as_none(self, session):
        """Rather than raising: the caller is the orchestrator's cleanup, where a
        session that was never created is worth a warning and nothing more."""
        session.execute.return_value.scalar_one_or_none.return_value = None

        assert await SessionStore(session).debit("nobody", 10) is None

    async def test_the_balance_is_passed_through(self, session):
        session.execute.return_value.scalar_one_or_none.return_value = 49_500

        assert await SessionStore(session).debit("sess_1", 500) == 49_500


class TestStartTurn:
    @pytest.fixture(autouse=True)
    async def started(self, session):
        await SessionStore(session).start_turn("sess_1")

    async def test_a_conflict_updates_rather_than_doing_nothing(self, session):
        """DO NOTHING returns no row on conflict — the common case here, every
        message after the first — which would cost the caller a second SELECT."""
        assert "ON CONFLICT (session_id) DO UPDATE" in sql_of(session)
        assert "DO NOTHING" not in sql_of(session)

    async def test_the_conflict_only_moves_last_updated(self, session):
        """Never the balance: a returning visitor does not get a refill."""
        assigned = sql_of(session).split("DO UPDATE SET")[1].split("RETURNING")[0]

        assert "last_updated = now()" in assigned
        assert "remaining_tokens" not in assigned

    async def test_it_returns_the_balance_and_not_the_row(self, session):
        """A scalar, deliberately: `returning(SessionModel)` hands back an ORM
        entity, and a session whose identity map already holds the row gets the
        copy it remembers — which `debit` does not update and
        `expire_on_commit=False` never refreshes. It was measured returning a
        stale full budget for an overdrawn session."""
        returning = sql_of(session).split("RETURNING")[1]

        assert returning.strip() == "sessions.remaining_tokens"

    async def test_a_new_session_is_given_the_configured_budget(self, session):
        """From the constant, not a literal — the table carries no DEFAULT, so
        this is the only place the starting allowance is decided."""
        params = statement_of(session).compile().params

        assert params["remaining_tokens"] == AppConfig.SESSION_TOKEN_BUDGET


class TestTheColumnItWrites:
    def test_remaining_tokens_has_no_default(self):
        """A client-side default would not reach a `postgresql.insert()` anyway,
        and a server default would be a second copy of the budget, free to drift
        from the constant."""
        column = SessionModel.__table__.columns["remaining_tokens"]

        assert column.default is None
        assert column.server_default is None
        assert not column.nullable
