"""Tests for the session token budget at the turn's two ends: opening it
(`start_session_turn`), who may spend (`session_is_out_of_tokens`) and what a
finished turn cost (`debit_session_tokens`).

For the charge, two things are load-bearing and neither is the arithmetic (that
is SQL's job, see test_session_store.py):

- **Which database session it writes on.** Its own, opened from
  `session_factory` through `ctx.store`, because this runs inside the
  orchestrator's shielded cleanup and outlives the request.
- **That it never raises.** It is called from `Orchestrator._finalize`, where an
  exception would cost the user their reply over a bookkeeping problem.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from airglider import OperationResult, TokenUsage
from tests.conftest import fake_session_factory
from app.orchestration.token_budget import (
    debit_session_tokens,
    session_is_out_of_tokens,
    start_session_turn,
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
    """The SessionStore the two helpers construct, with both calls awaitable."""
    store = MagicMock()
    store.debit = AsyncMock(return_value=49_000)
    store.start_turn = AsyncMock(return_value=50_000)
    return store


@pytest.fixture
def patched_store(store):
    with patch(
        "app.orchestration.token_budget.SessionStore", return_value=store
    ) as cls:
        yield cls


class TestOpeningTheTurn:
    """`start_session_turn` — the turn's first round trip, which both creates
    the row on a first message and reports the balance about to be judged."""

    async def test_it_hands_back_the_balance(
        self, request_context, store, patched_store
    ):
        step = await start_session_turn(request_context)

        assert step.unwrap() == 50_000

    async def test_it_is_a_step_of_its_own(self, request_context, patched_store):
        """A `@task`, so the round trip's duration and any failure land in the
        trace under their own name rather than folded into whatever ran next.
        `Orchestrator.run` hangs it on the turn's root with `add_step`."""
        step = await start_session_turn(request_context)

        assert isinstance(step, OperationResult)
        assert step.name.endswith("start_session_turn")
        assert step.ok is True

    async def test_it_opens_its_own_session(self, make_request_context, patched_store):
        """Like the debit: the turn runs after the handler that started it has
        returned, so nothing built at the request boundary is still open."""
        factory = fake_session_factory()
        ctx = make_request_context(session_factory=factory)

        await start_session_turn(ctx)

        factory.begin.assert_called_once_with()
        factory.assert_not_called()
        opened = factory.begin.return_value.__aenter__.return_value
        patched_store.assert_called_once_with(opened)

    async def test_a_failed_read_comes_back_as_a_failed_step(
        self, request_context, store
    ):
        """It does not raise — a `@task` reports through its envelope, which is
        what lets `run` record the failure before deciding to stop on it."""
        store.start_turn = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("app.orchestration.token_budget.SessionStore", return_value=store):
            step = await start_session_turn(request_context)

        assert step.ok is False
        assert step.runtime_error is not None


class TestWhoMaySpend:
    """The decision, on the balance the opening round trip just read."""

    @pytest.mark.parametrize("remaining", [0, -1, -50_000])
    def test_a_spent_session_is_refused(self, remaining):
        """Negative included: a turn is charged after it runs, so a session's
        last turn ends in the red."""
        assert session_is_out_of_tokens(remaining) is True

    @pytest.mark.parametrize("remaining", [1, 50_000])
    def test_anything_left_is_enough(self, remaining):
        """`<= 0`, not "can this turn afford it" — the charge comes afterwards,
        so one token buys a whole turn."""
        assert session_is_out_of_tokens(remaining) is False


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
        """Its own, from `session_factory`: this runs inside the orchestrator's
        shielded cleanup and outlives the request, so anything built at the
        request boundary is long out of scope by now."""
        factory = fake_session_factory()
        ctx = make_request_context(session_factory=factory)

        await debit_session_tokens(ctx, _record(10))

        # `.begin()`, so the write is committed when the block exits — the
        # store does not commit for itself
        factory.begin.assert_called_once_with()
        factory.assert_not_called()
        opened = factory.begin.return_value.__aenter__.return_value
        patched_store.assert_called_once_with(opened)


class TestItNeverRaises:
    async def test_a_failing_store_is_swallowed(self, request_context, store):
        store.debit = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("app.orchestration.token_budget.SessionStore", return_value=store):
            # must not raise — a lost charge cannot cost the user their reply
            await debit_session_tokens(request_context, _record(10))

    async def test_an_unopenable_session_is_swallowed(self, make_request_context):
        factory = fake_session_factory()
        factory.begin.side_effect = RuntimeError("pool exhausted")

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
