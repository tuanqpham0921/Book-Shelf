"""Tests for debit_session_tokens — charging a finished turn to its session.

Two things are load-bearing here and neither is the arithmetic (that is SQL's
job, see test_session_store.py):

- **Which database session it writes on.** Its own, opened from
  `session_factory`, never a store off `ctx.stores` — that one's scope is gone by
  the time this runs.
- **That it never raises.** It is called from `Orchestrator._finalize`, where an
  exception would cost the user their reply over a bookkeeping problem.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from airglider import OperationResult, TokenUsage
from app.orchestration.token_budget import debit_session_tokens


def _record(total: int) -> OperationResult:
    """A turn's root envelope, carrying the summed spend the orchestrator hangs
    every workflow's usage onto."""
    return OperationResult(
        name="orchestrator_chat_1",
        ok=True,
        token_usage=TokenUsage(total=total, prompt=total),
    )


@pytest.fixture
def store() -> MagicMock:
    """The SessionStore the helper constructs, with `debit` awaitable."""
    store = MagicMock()
    store.debit = AsyncMock(return_value=49_000)
    return store


@pytest.fixture
def patched_store(store):
    with patch(
        "app.orchestration.token_budget.SessionStore", return_value=store
    ) as cls:
        yield cls


class TestWhatGetsCharged:
    async def test_the_session_is_charged_the_turns_whole_spend(
        self, request_context, store, patched_store
    ):
        await debit_session_tokens(request_context, _record(1_000))

        store.debit.assert_awaited_once_with(request_context.session_id, 1_000)

    async def test_a_free_turn_still_settles(
        self, request_context, store, patched_store
    ):
        """A turn that made no LLM call (a cached plan, a refused message) spends
        nothing. Charging zero keeps `last_updated` honest about activity."""
        await debit_session_tokens(request_context, _record(0))

        store.debit.assert_awaited_once_with(request_context.session_id, 0)


class TestWhichDatabaseSessionItUses:
    async def test_it_opens_its_own_session(
        self, make_request_context, store, patched_store
    ):
        """From `session_factory`, because this runs inside the orchestrator's
        shielded cleanup and outlives the request — by which point the stores'
        session is long out of scope."""
        factory = MagicMock(spec=async_sessionmaker)
        ctx = make_request_context(session_factory=factory)

        await debit_session_tokens(ctx, _record(10))

        factory.assert_called_once_with()
        opened = factory.return_value.__aenter__.return_value
        patched_store.assert_called_once_with(opened)

    async def test_it_does_not_reach_for_a_store_on_the_request(
        self, request_context, store, patched_store
    ):
        """`ctx.stores` holds stores built on the request-scoped session; using
        one here would write on a connection nothing owns, and silently succeed."""
        book_store = request_context.stores[
            next(iter(request_context.stores))
        ]

        await debit_session_tokens(request_context, _record(10))

        assert not book_store.method_calls


class TestItNeverRaises:
    async def test_a_failing_store_is_swallowed(self, request_context, store):
        store.debit = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("app.orchestration.token_budget.SessionStore", return_value=store):
            # must not raise — a lost charge cannot cost the user their reply
            await debit_session_tokens(request_context, _record(10))

    async def test_an_unopenable_session_is_swallowed(self, make_request_context):
        factory = MagicMock(
            spec=async_sessionmaker, side_effect=RuntimeError("pool exhausted")
        )

        await debit_session_tokens(
            make_request_context(session_factory=factory), _record(10)
        )

    async def test_a_session_with_no_row_is_swallowed(
        self, request_context, store, patched_store
    ):
        """`debit` returns None when nothing matched — a turn that never went
        through the chat route, so nothing created its row."""
        store.debit = AsyncMock(return_value=None)

        await debit_session_tokens(request_context, _record(10))
