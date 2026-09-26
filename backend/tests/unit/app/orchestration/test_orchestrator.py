"""Tests for Orchestrator.run: verifies a finished conversation workflow is
always handed to record_chat_run — the "don't record" decision for a missing
result lives inside record_chat_run itself (see test_run_recorder.py), not in
the orchestrator, so _finalize calls it unconditionally.

`TestWritingTheReply` covers the third layer the orchestrator gained on
2026-09-08, when the generation node was deregistered into a stage that runs
once after the runner. The wiring is what is asserted here — whether the stage
runs, and what it is fed — not the reply itself, which is
test_write_recommendations_executor.py.

`TestChargingTheSession` covers the fourth thing `_finalize` does: charge the
turn to its session's token budget. `TestRefusingAnExhaustedSession` is the other
end of that budget — the route reads the balance, this is where it is judged.
"""

import asyncio
import logging
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from config import AppConfig
from app.domains.base_workflow import FailedGoalOutput
from app.domains.books.external import BookAnchorOutput
from app.domains.books.find_by_title import FindTitleNodeTypeEnum
from app.domains.planjane import PlanJaneOutput, SystemGoal
from app.orchestration.orchestrator import (
    DEBIT_TOKENS_TIMEOUT,
    Orchestrator,
    _best_effort,
)
from app.orchestration.task_runner import TaskResult, TaskRunnerOutput
from app.orchestration.token_budget import (
    OUT_OF_TOKENS_MESSAGE,
    SITE_OUT_OF_TOKENS_MESSAGE,
)
from app.orchestration.triage import TriageOutput
from app.orchestration.validation import UserMsgValidation
from app.orchestration.validation.validate import HARMFUL_REPLY, INCOHERENT_REPLY
from airglider import OperationResult, Response, TokenUsage
from clients.messages import UserMessage

# request_context comes from tests/conftest.py


def _balance(remaining: int) -> OperationResult:
    """What `start_session_turn` hands back: a `@task` returns its payload in an
    envelope, which `run` attaches to the turn's root and then unwraps."""
    return OperationResult(
        name="app.orchestration.token_budget.start_session_turn",
        ok=True,
        response=Response(result=remaining, output_type="int"),
    )


@pytest.fixture(autouse=True)
def start_turn():
    """The turn's opening balance read, patched for every test in this module.

    `Orchestrator.run` now opens the session's turn itself, and the real call
    would go through conftest's mock `session_factory` to a `SessionStore` on a
    `MagicMock` session — a failed step, which `run` stops on. The tests that
    are *about* the balance take this mock by name and set its envelope.
    """
    with patch(
        "app.orchestration.orchestrator.start_session_turn",
        new_callable=AsyncMock,
        return_value=_balance(AppConfig.SESSION_TOKEN_BUDGET),
    ) as mock_start:
        yield mock_start


def _validation(**flags) -> OperationResult:
    """What `validate_user_message` hands back: a passing check unless a flag
    says otherwise."""
    fields = {
        "reasoning": "",
        "security_issue": False,
        "harmful_content": False,
        "gibberish_or_incoherent": False,
    } | flags
    return OperationResult(
        name="app.orchestration.validation.validate.validate_user_message",
        ok=True,
        response=Response(result=UserMsgValidation(**fields)),
    )


@pytest.fixture(autouse=True)
def validate():
    """The message check, patched to pass for every test in this module — the
    real one is an LLM call. The tests that are *about* it set its envelope."""
    with patch(
        "app.orchestration.orchestrator.validate_user_message",
        new_callable=AsyncMock,
        return_value=_validation(),
    ) as mock_validate:
        yield mock_validate


@pytest.fixture(autouse=True)
def debit():
    """The session charge, patched for every test in this module.

    Every test here drives the real `_finalize`, which now charges the session
    before recording — and conftest's `session_factory` is a
    `MagicMock(spec=async_sessionmaker)` whose `execute` is not awaitable, so
    the real call would log a swallowed `TypeError` in tests that are about
    something else entirely. The tests that *are* about the charge take this
    mock by name.
    """
    with patch(
        "app.orchestration.orchestrator.debit_session_tokens",
        new_callable=AsyncMock,
    ) as mock_debit:
        yield mock_debit


def _plan() -> PlanJaneOutput:
    """A real plan, not a mock — `TaskRunnerInput.plan` is validated, so a
    stand-in fails at the call site rather than reaching the stage under
    test."""
    return PlanJaneOutput(
        accepted_goals=[
            SystemGoal(
                id="1",
                instruction="Find the book It by title",
                reasoning="A sufficiently long reasoning for the test",
                confidence=1.0,
                target_node_type=FindTitleNodeTypeEnum.REQUEST,
                depends_on=[],
            )
        ]
    )


def _triage_with_plan(plan, token_usage=None):
    """A triage workflow that produced `plan`, or none at all.

    The plan rides on the *record's* payload, because that is where `run` reads
    it from: `triage_workflow.record.unwrap()`. For a real workflow that is the
    same object `.result` returns (`Workflow.result` is `self.record.result`) —
    the difference is only the verb, which stops the turn when triage failed
    rather than reading a failure as "no plan".
    """
    workflow = AsyncMock()
    workflow.record = OperationResult(
        ok=True,
        response=Response(result=TriageOutput(parse_result=plan)),
        token_usage=token_usage or TokenUsage(),
    )
    return workflow


def _runner_with(outputs):
    """A runner whose results map holds `outputs`, each wrapped in a
    `TaskResult` the way the real runner wraps a goal's output."""
    runner = AsyncMock()
    runner.record = OperationResult(ok=True)
    runner.result = TaskRunnerOutput(
        task_results={
            task_id: TaskResult(
                task_id=task_id,
                node_type=FindTitleNodeTypeEnum.REQUEST.value,
                output=output,
            )
            for task_id, output in outputs.items()
        }
    )
    return runner


class TestOrchestratorRun:
    async def test_records_chat_run(self, request_context):
        # None is the real "triage produced no plan" answer, and it is what
        # keeps this test about the hand-off. Left implicit and an AsyncMock
        # would auto-create the payload as a MagicMock, which the orchestrator
        # feeds straight into TaskRunnerInput, which rejects it.
        mock_workflow = _triage_with_plan(None)

        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=mock_workflow,
        ), patch(
            "app.orchestration.orchestrator.record_chat_run",
            new_callable=AsyncMock,
        ) as mock_record:
            await Orchestrator().run(request_context)

        # (context, root record, triage workflow, task runner, writer,
        # messages) — the runner and the writer are None because no plan was
        # produced, so neither ran
        mock_record.assert_awaited_once_with(
            request_context, ANY, mock_workflow, None, None, ANY
        )

    async def test_still_hands_off_to_record_chat_run_when_response_is_none(
        self, request_context
    ):
        mock_workflow = AsyncMock()
        mock_workflow.record = None
        mock_workflow.result.parse_result = None

        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=mock_workflow,
        ), patch(
            "app.orchestration.orchestrator.record_chat_run",
            new_callable=AsyncMock,
        ) as mock_record:
            await Orchestrator().run(request_context)

        # _finalize has no response-is-None guard of its own; record_chat_run's
        # own guard (tested in test_run_recorder.py) is what skips persisting
        mock_record.assert_awaited_once_with(
            request_context, ANY, mock_workflow, None, None, ANY
        )


class TestWritingTheReply:
    """The stage runs from here rather than from the registry, so these are the
    only tests that the reply happens at all."""

    @staticmethod
    def _drive(request_context, runner, plan="default"):
        """Run a turn with triage and the runner faked, capturing the writer."""
        return (
            patch(
                "app.orchestration.orchestrator.TriageWorkflow",
                return_value=_triage_with_plan(_plan() if plan == "default" else plan),
            ),
            patch(
                "app.orchestration.orchestrator.TaskRunnerWorkflow",
                return_value=runner,
            ),
            # return_value explicit: the default MagicMock is not awaitable,
            # and the orchestrator awaits the workflow it constructs
            patch(
                "app.orchestration.orchestrator.GenerateRecommendationsExecutor",
                return_value=AsyncMock(),
            ),
            patch(
                "app.orchestration.orchestrator.record_chat_run",
                new_callable=AsyncMock,
            ),
        )

    async def test_the_whole_results_map_is_what_the_reply_is_written_from(
        self, request_context
    ):
        """Not one chain's outputs: deregistering is precisely what widened
        this from the planner's `depends_on` to everything that ran, which is
        how a lookup running beside a recommendation reaches the reply."""
        results = {
            "1": BookAnchorOutput(num_books=0, goal_instruction="Find It"),
            "2": FailedGoalOutput(goal_instruction="Books like It"),
        }
        triage, runner_p, writer_p, record = self._drive(
            request_context, _runner_with(results)
        )
        with triage, runner_p, writer_p as writer_cls, record:
            await Orchestrator().run(request_context)

        node_input = writer_cls.return_value.await_args.args[0]
        assert [result.output for result in node_input.results] == list(
            results.values()
        )

    async def test_no_reply_is_written_when_the_plan_produced_nothing(
        self, request_context
    ):
        # nothing to write from, so the stage would only invent evidence
        triage, runner_p, writer_p, record = self._drive(
            request_context, _runner_with({})
        )
        with triage, runner_p, writer_p as writer_cls, record:
            await Orchestrator().run(request_context)

        writer_cls.return_value.assert_not_awaited()

    async def test_a_turn_that_never_planned_writes_no_reply(self, request_context):
        # small talk and refusals are triage's own answer; the runner never ran
        triage, runner_p, writer_p, record = self._drive(
            request_context, _runner_with({}), plan=None
        )
        with triage, runner_p, writer_p as writer_cls, record:
            await Orchestrator().run(request_context)

        writer_cls.assert_not_called()

    async def test_the_replys_record_lands_on_the_turns_trace(self, request_context):
        """Its spend and duration belong to the turn — the root envelope is
        what `chat_runs` promotes its stats from, and the stage is a whole LLM
        call the totals would otherwise miss."""
        triage, runner_p, writer_p, record = self._drive(
            request_context,
            _runner_with({"1": BookAnchorOutput(num_books=1)}),
        )
        with triage, runner_p, writer_p as writer_cls, record as mock_record:
            writer_cls.return_value.record = OperationResult(name="writer", ok=True)
            await Orchestrator().run(request_context)

        root = mock_record.await_args.args[1]
        assert "writer" in [step.name for step in root.steps]


class TestChargingTheSession:
    """`_finalize` charges the turn before it records it — the one write here
    with money attached."""

    @staticmethod
    def _triage_costing(total: int):
        """A triage workflow whose envelope spent `total` tokens."""
        return _triage_with_plan(
            None, token_usage=TokenUsage(total=total, prompt=total)
        )

    async def test_the_charge_is_the_whole_turns_spend(self, request_context, debit):
        """The root envelope, not the runner's — airglider sums `token_usage` up
        the tree, so the planner's spend (the whole tool catalog) is in it."""
        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=self._triage_costing(1234),
        ), patch(
            "app.orchestration.orchestrator.record_chat_run", new_callable=AsyncMock
        ):
            await Orchestrator().run(request_context)

        context, record = debit.await_args.args
        assert context is request_context
        assert record.token_usage.total == 1234

    async def test_the_charge_lands_even_when_recording_fails(
        self, request_context, debit
    ):
        """Recording is a dev-only file dump; the charge must not queue behind
        it. This is why the debit goes first in `_finalize`."""
        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=self._triage_costing(99),
        ), patch(
            "app.orchestration.orchestrator.record_chat_run",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ):
            await Orchestrator().run(request_context)

        debit.assert_awaited_once()

    async def test_a_failed_charge_does_not_take_down_the_stream(
        self, request_context, debit
    ):
        """`_finalize` is best-effort throughout: the stream still closes, so
        the client is never left hanging on a database problem."""
        debit.side_effect = RuntimeError("database is down")
        request_context.sse_stream.close = AsyncMock()

        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=self._triage_costing(10),
        ), patch(
            "app.orchestration.orchestrator.record_chat_run", new_callable=AsyncMock
        ):
            await Orchestrator().run(request_context)

        request_context.sse_stream.close.assert_awaited()


class TestBestEffortCleanup:
    """Every step in `_finalize` runs under its own ceiling and logs its own
    outcome.

    The ceiling is not the engine's timeouts restated: `_finalize` runs inside
    `asyncio.shield`, so nothing outside can stop these — it is what makes them
    terminate at all — and two of the three never touch a database.
    """

    async def test_a_step_that_runs_out_of_time_names_itself_and_the_turn(
        self, caplog
    ):
        """The old single `except Exception` logged neither which step it was
        nor why, so a timeout and a crash read identically in the console."""

        async def forever():
            await asyncio.Event().wait()

        with caplog.at_level(logging.WARNING):
            await _best_effort(forever(), 0.01, "debit_session_tokens", "turn_abc")

        assert "debit_session_tokens" in caplog.text
        assert "turn_abc" in caplog.text
        assert "0.01" in caplog.text

    async def test_a_step_that_runs_out_of_time_is_cancelled(self):
        """`wait_for` cancels what it gave up on, so nothing is left running
        behind the shield after `_finalize` returns."""
        cancelled = asyncio.Event()

        async def forever():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        await _best_effort(forever(), 0.01, "record_chat_run", "turn_abc")

        assert cancelled.is_set()

    async def test_an_unexpected_failure_is_logged_with_its_traceback(self, caplog):
        """Both recorders swallow their own exceptions, so anything arriving
        here is a surprise worth the stack — `sse_stream.close()` is the one
        step with no `except` of its own."""

        async def boom():
            raise RuntimeError("the stream is already gone")

        with caplog.at_level(logging.ERROR):
            await _best_effort(boom(), 1, "sse_stream.close", "turn_abc")

        assert "the stream is already gone" in caplog.text
        assert "Traceback" in caplog.text

    async def test_the_debit_ceiling_sits_above_the_databases_own(self):
        """Level with `DATABASE_TIMEOUT` it would cancel a debit that had spent
        `pool_timeout` waiting for a connection and was about to succeed — and
        a cancel here is the one in `_finalize` that can reach a live
        connection."""
        assert DEBIT_TOKENS_TIMEOUT > AppConfig.DATABASE_TIMEOUT * 2


class TestRefusingAnExhaustedSession:
    """The other end of the budget. `run` reads the balance itself, as its first
    step, and this is the only place it is judged — with a message rather than a
    status code, because the route's response is an SSE stream and the client
    renders a non-200 as its own generic error."""

    @staticmethod
    def _context(make_request_context, start_turn, remaining_tokens=0):
        ctx = make_request_context()
        ctx.sse_stream.send_error = AsyncMock()
        start_turn.return_value = _balance(remaining_tokens)
        return ctx

    @staticmethod
    async def _turn(ctx):
        """Run one turn with triage and recording faked. Returns the two mocks:
        the `TriageWorkflow` class, which answers whether the turn started at
        all, and `record_chat_run`, which carries the root envelope."""
        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=_triage_with_plan(None),
        ) as triage_cls, patch(
            "app.orchestration.orchestrator.record_chat_run", new_callable=AsyncMock
        ) as record:
            await Orchestrator().run(ctx)
        return triage_cls, record

    async def test_a_spent_session_gets_no_turn(
        self, make_request_context, start_turn
    ):
        """Nothing is even planned — the refusal is ahead of triage, which is
        the first thing that costs money."""
        ctx = self._context(make_request_context, start_turn)

        triage_cls, _ = await self._turn(ctx)

        triage_cls.assert_not_called()

    async def test_the_user_is_told_why(self, make_request_context, start_turn):
        """Verbatim: the client renders an `error` event's text as-is, so this
        string is what actually reaches the screen."""
        ctx = self._context(make_request_context, start_turn)

        await self._turn(ctx)

        ctx.sse_stream.send_error.assert_awaited_once_with(OUT_OF_TOKENS_MESSAGE)

    async def test_a_negative_balance_counts_as_spent(
        self, make_request_context, start_turn
    ):
        """It goes negative by design — a turn is charged after it runs, so a
        session's last turn overshoots into the red."""
        ctx = self._context(make_request_context, start_turn, remaining_tokens=-3_000)

        triage_cls, _ = await self._turn(ctx)

        triage_cls.assert_not_called()

    async def test_one_token_left_is_enough(self, make_request_context, start_turn):
        """`<= 0`, not "can this turn afford it": the charge comes afterwards, so
        the only question is whether anything was left."""
        ctx = self._context(make_request_context, start_turn, remaining_tokens=1)

        triage_cls, _ = await self._turn(ctx)

        triage_cls.assert_called_once()

    async def test_an_unreadable_balance_stops_the_turn(
        self, make_request_context, start_turn
    ):
        """`run` unwraps the opening step, so a database that cannot be reached
        stops the turn there rather than letting it spend against a balance
        nobody could see."""
        start_turn.return_value = OperationResult(name="start_session_turn")

        triage_cls, _ = await self._turn(make_request_context())

        triage_cls.assert_not_called()

    async def test_the_refusal_is_on_the_turns_record(
        self, make_request_context, start_turn
    ):
        """So a refused turn reads as one, rather than as a turn that did
        nothing for no reason. Its one step is the balance read that refused
        it."""
        ctx = self._context(make_request_context, start_turn)

        _, record = await self._turn(ctx)

        assert "refused: session out of tokens" in record.await_args.args[1].details

    async def test_the_balance_is_recorded_on_every_turn(
        self, make_request_context, start_turn
    ):
        """Tracking rather than enforcement, which is why it is not inside the
        guard: what the session had before this turn, so the turn's cost can be
        read against it."""
        ctx = self._context(make_request_context, start_turn, remaining_tokens=1_234)

        _, record = await self._turn(ctx)

        assert "session tokens remaining: 1234" in record.await_args.args[1].details


class TestRefusingWhenTheSiteIsSpent:
    """The site-wide daily cap — the backstop for a session budget that anyone
    can reset by inventing a session id. Production only."""

    @staticmethod
    def _spend(spent: int) -> OperationResult:
        return OperationResult(
            name="app.orchestration.token_budget.read_site_spend",
            ok=True,
            response=Response(result=spent, output_type="int"),
        )

    async def _turn(self, ctx, spent):
        with patch(
            "app.orchestration.orchestrator.read_site_spend",
            new_callable=AsyncMock,
            return_value=self._spend(spent),
        ) as read, patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=_triage_with_plan(None),
        ) as triage_cls, patch(
            "app.orchestration.orchestrator.record_chat_run", new_callable=AsyncMock
        ):
            await Orchestrator().run(ctx)
        return read, triage_cls

    async def test_a_spent_site_gets_no_turn(self, make_request_context):
        ctx = make_request_context(app_env="production")
        ctx.sse_stream.send_error = AsyncMock()

        _, triage_cls = await self._turn(ctx, AppConfig.SITE_DAILY_TOKEN_BUDGET)

        triage_cls.assert_not_called()
        ctx.sse_stream.send_error.assert_awaited_once_with(SITE_OUT_OF_TOKENS_MESSAGE)

    async def test_under_the_cap_the_turn_runs(self, make_request_context):
        ctx = make_request_context(app_env="production")

        _, triage_cls = await self._turn(ctx, AppConfig.SITE_DAILY_TOKEN_BUDGET - 1)

        triage_cls.assert_called_once()

    async def test_outside_production_it_is_not_read(self, make_request_context):
        """A local eval campaign is spend the owner chose."""
        ctx = make_request_context(app_env="development")

        read, triage_cls = await self._turn(ctx, AppConfig.SITE_DAILY_TOKEN_BUDGET)

        read.assert_not_called()
        triage_cls.assert_called_once()


class TestValidatingTheMessage:
    """The message arrives with `pass_validation=None`, and only a passing check
    lets it reach triage — the same `UserMessage`, stamped True."""

    @staticmethod
    async def _turn(ctx):
        with patch(
            "app.orchestration.orchestrator.TriageWorkflow",
            return_value=_triage_with_plan(None),
        ) as triage_cls, patch(
            "app.orchestration.orchestrator.record_chat_run", new_callable=AsyncMock
        ) as record:
            await Orchestrator().run(ctx)
        return triage_cls, record

    @staticmethod
    def _unvalidated(make_request_context):
        ctx = make_request_context(user_message=UserMessage(content="books like Dune"))
        ctx.sse_stream.send_chars = AsyncMock()
        return ctx

    async def test_a_passing_message_reaches_triage_validated(
        self, make_request_context
    ):
        """Same message, so the chat_id already sent to the client still names it."""
        ctx = self._unvalidated(make_request_context)
        raw = ctx.user_message

        triage_cls, _ = await self._turn(ctx)

        triage_cls.assert_called_once()
        assert ctx.user_message is raw
        assert ctx.user_message.pass_validation is True

    async def test_the_turns_record_shows_the_message_arrived_unchecked(
        self, make_request_context
    ):
        """The root's input is stamped before the check runs."""
        ctx = self._unvalidated(make_request_context)

        _, record = await self._turn(ctx)

        assert record.await_args.args[1].input["pass_validation"] is None

    @pytest.mark.parametrize(
        ("flags", "reply"),
        [
            ({"security_issue": True}, HARMFUL_REPLY),
            ({"harmful_content": True}, HARMFUL_REPLY),
            ({"gibberish_or_incoherent": True}, INCOHERENT_REPLY),
            # the order is the priority: harm is named before gibberish
            ({"harmful_content": True, "gibberish_or_incoherent": True}, HARMFUL_REPLY),
        ],
    )
    async def test_a_failed_check_gets_its_fixed_reply_and_no_triage(
        self, make_request_context, validate, flags, reply
    ):
        ctx = self._unvalidated(make_request_context)
        validate.return_value = _validation(**flags)

        triage_cls, _ = await self._turn(ctx)

        triage_cls.assert_not_called()
        ctx.sse_stream.send_chars.assert_awaited_once_with(reply)
        assert ctx.user_message.pass_validation is False

    async def test_the_refusal_is_on_the_turns_record(
        self, make_request_context, validate
    ):
        ctx = self._unvalidated(make_request_context)
        validate.return_value = _validation(gibberish_or_incoherent=True)

        _, record = await self._turn(ctx)

        root = record.await_args.args[1]
        assert any(d.startswith("refused by validation") for d in root.details)
        assert root.ok

    async def test_a_check_with_no_verdict_stops_the_turn(
        self, make_request_context, validate
    ):
        """Nothing unchecked goes further: a failed step is unwrapped, not
        waved through."""
        validate.return_value = OperationResult(name="validate_user_message")

        ctx = self._unvalidated(make_request_context)

        triage_cls, _ = await self._turn(ctx)

        triage_cls.assert_not_called()
        assert ctx.user_message.pass_validation is None
