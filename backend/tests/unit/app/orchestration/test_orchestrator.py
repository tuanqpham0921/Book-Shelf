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
turn to its session's token budget.
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.domains.base_workflow import FailedGoalOutput
from app.domains.books.external import BookAnchorOutput
from app.domains.books.find_by_title import FindTitleNodeTypeEnum
from app.domains.planjane import PlanJaneOutput, SystemGoal
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.task_runner import TaskResult, TaskRunnerOutput
from airglider import OperationResult, TokenUsage

# request_context comes from tests/conftest.py


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


def _triage_with_plan(plan):
    """A triage workflow that produced `plan`, or none at all."""
    workflow = AsyncMock()
    workflow.record = OperationResult(ok=True)
    workflow.result.parse_result = plan
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
        mock_workflow = AsyncMock()
        mock_workflow.record = OperationResult(ok=True)
        # explicit: an AsyncMock would auto-create `.result.parse_result` as a
        # MagicMock, and the orchestrator feeds that straight into
        # TaskRunnerInput, which rejects it. None is the real "triage produced
        # no plan" answer, and it is what keeps this test about the hand-off.
        mock_workflow.result.parse_result = None

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
        workflow = AsyncMock()
        workflow.record = OperationResult(
            ok=True, token_usage=TokenUsage(total=total, prompt=total)
        )
        workflow.result.parse_result = None
        return workflow

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
