"""Tests for the session token budget: who may spend (`session_is_out_of_tokens`)
and what a finished turn cost (`debit_session_tokens`).

For the charge, two things are load-bearing and neither is the arithmetic (that
is SQL's job, see test_session_store.py):

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
from app.orchestration.token_budget import (
    debit_session_tokens,
    session_is_out_of_tokens,
)


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


class TestWhoMaySpend:
    """The decision, which reads the balance off the context rather than the
    database — the route put it there in the round trip that created the row."""

    @pytest.mark.parametrize("remaining", [0, -1, -50_000])
    def test_a_spent_session_is_refused_in_production(
        self, make_request_context, remaining
    ):
        """Negative included: a turn is charged after it runs, so a session's
        last turn ends in the red."""
        ctx = make_request_context(app_env="production", remaining_tokens=remaining)

        assert session_is_out_of_tokens(ctx) is True

    @pytest.mark.parametrize("remaining", [1, 50_000])
    def test_anything_left_is_enough(self, make_request_context, remaining):
        """`<= 0`, not "can this turn afford it" — the charge comes afterwards,
        so one token buys a whole turn."""
        ctx = make_request_context(app_env="production", remaining_tokens=remaining)

        assert session_is_out_of_tokens(ctx) is False

    @pytest.mark.parametrize("app_env", ["development", "test"])
    def test_nothing_is_refused_outside_production(self, make_request_context, app_env):
        """The row is still created and still debited there — only the refusal is
        production-only, so that `make dev` and the eval suites (one session for
        a whole suite) are not cut off partway."""
        ctx = make_request_context(app_env=app_env, remaining_tokens=-10_000)

        assert session_is_out_of_tokens(ctx) is False


class TestWhatGetsCharged:
    async def test_the_session_is_charged_the_turns_whole_spend(
        self, request_context, store, patched_store
    ):
        await debit_session_tokens(request_context, _record(1_000))

        store.debit.assert_awaited_once_with(request_context.session_id, 1_000)

    async def test_a_turn_that_spent_nothing_is_not_written(
        self, request_context, store, patched_store
    ):
        """A refused turn makes no LLM call, so there is nothing to subtract —
        and `start_turn` has already moved `last_updated` for it."""
        await debit_session_tokens(request_context, _record(0))

        store.debit.assert_not_awaited()


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
