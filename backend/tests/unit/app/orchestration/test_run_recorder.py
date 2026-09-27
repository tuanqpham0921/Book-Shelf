"""Tests for run_recorder: column mapping and serialization fidelity of
build_chat_run_row (private attrs like _refusal must survive), and the
env-dependent sink selection in record_chat_run (production → one row and no
file, development → files and no row, test → nothing, failures swallowed
either way)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.domains.books.find_by_title import FindTitleNodeTypeEnum
from app.orchestration.triage import TriageOutput
from app.domains.planjane import PlanJaneOutput, SystemGoal
from app.orchestration.run_recorder import build_chat_run_row, record_chat_run
from app.orchestration.write_recommendations import RecommendationsOutput, TextBlock
from airglider import OperationResult, Response, TokenUsage
from config import FilesLocationConstants
from db.stores.deferred_query import DeferredBookQuery


def _make_goal():
    """A SystemGoal with a refusal recorded, so its private attrs (_refusal,
    _refusal_reasons) carry content to assert survives serialization."""
    goal = SystemGoal(
        id="1",
        instruction="Find a book about machine learning topics",
        reasoning="A sufficiently long reasoning for the test",
        confidence=0.9,
        target_node_type=FindTitleNodeTypeEnum.REQUEST,
        depends_on=[],
    )
    goal.refuse("just to populate a private attr")
    return goal


def _make_planner_record() -> OperationResult:
    goal = _make_goal()
    output = TriageOutput(
        session_id="sess_1",
        # the diagram lives on the plan — TriageOutput.diagram reads through to
        # it, which is what run_recorder promotes into chat_runs.mermaid
        parse_result=PlanJaneOutput(accepted_goals=[goal], diagram="graph TD;"),
    )
    return OperationResult(
        ok=True,
        response=Response(result=output),
        token_usage=TokenUsage(total=42, prompt=30, completion=12),
    )


def _make_root_record(planner: OperationResult) -> OperationResult:
    """The orchestrator's root envelope, built the way Orchestrator.run builds
    it: the planner record hung on as a step, then ok/duration stamped."""
    record = OperationResult(name="orchestrator_chat_1", ok=True)
    record.add_step(planner)
    record.timing.duration = 1.23
    return record


def _make_workflow(planner: OperationResult):
    workflow = MagicMock()
    workflow.record = planner
    workflow.result = planner.result
    return workflow


class TestBuildChatRunRow:
    def test_maps_workflow_onto_columns(self):
        planner = _make_planner_record()

        row = build_chat_run_row(
            session_id="sess_1",
            user_chat_id="chat_1",
            user_message="Find me a book",
            record=_make_root_record(planner),
            planner=planner,
        )

        assert row["chat_id"] == "chat_1"
        assert row["session_id"] == "sess_1"
        assert row["user_message"] == "Find me a book"
        assert row["ok"] is True
        assert row["duration_s"] == 1.23
        # promoted from the root envelope, which rolled the planner's up
        assert row["total_tokens"] == 42
        assert row["mermaid"] == "graph TD;"
        assert row["tasks"] is None
        assert row["planner"]["ok"] is True
        assert (
            row["planner"]["response"]["result"]["parse_result"]["accepted_goals"][0][
                "instruction"
            ]
            == "Find a book about machine learning topics"
        )

    def test_writer_column_keeps_the_prose_rather_than_its_summary(self):
        # RecommendationsOutput.to_summary() is two counts. The reply itself
        # only ever existed as SSE events, so a summarized column would leave
        # no record anywhere of what the turn actually said.
        planner = _make_planner_record()
        writer = OperationResult(
            ok=True,
            response=Response(
                result=RecommendationsOutput(
                    blocks=[
                        TextBlock(type="text", text="Here are three books like Dune.")
                    ],
                    num_books_shown=3,
                )
            ),
        )

        row = build_chat_run_row(
            session_id="sess_1",
            user_chat_id="chat_1",
            user_message="Find me a book",
            record=_make_root_record(planner),
            planner=planner,
            writer=writer,
        )

        assert row["writer"]["ok"] is True
        result = row["writer"]["response"]["result"]
        assert result["blocks"][0]["text"] == "Here are three books like Dune."
        assert result["num_books_shown"] == 3

    def test_planner_column_stays_the_planner_envelope(self):
        # evals/report_system_goals.py — the golden test — reads accepted goals
        # at this exact path. Re-rooting the column on the orchestrator record
        # would empty every diff silently, so pin the path, not just the value.
        planner = _make_planner_record()

        row = build_chat_run_row(
            session_id="sess_1",
            user_chat_id="chat_1",
            user_message="Find me a book",
            record=_make_root_record(planner),
            planner=planner,
        )

        from evals.planjane.report_system_goals import accepted_goal_types

        assert accepted_goal_types(row["planner"]) == [
            FindTitleNodeTypeEnum.REQUEST.value
        ]

    def test_serialization_preserves_private_attrs(self):
        planner = _make_planner_record()

        row = build_chat_run_row(
            session_id="sess_1",
            user_chat_id="chat_1",
            user_message="Find me a book",
            record=_make_root_record(planner),
            planner=planner,
        )

        goal = row["planner"]["response"]["result"]["parse_result"]["accepted_goals"][0]
        assert goal["_refusal"] is True
        assert goal["_refusal_reasons"] == ["just to populate a private attr"]

    def test_a_task_returning_a_live_object_still_encodes(self):
        # build_pool is a @task that returns a DeferredBookQuery, so the query
        # lands on its envelope's result — and the JSONB bind raised on it
        planner = _make_planner_record()
        tasks = OperationResult(ok=True)
        tasks.add_step(
            OperationResult(
                name="build_pool",
                ok=True,
                response=Response(result=DeferredBookQuery(select(1), label="similar")),
            )
        )

        row = build_chat_run_row(
            session_id="sess_1",
            user_chat_id="chat_1",
            user_message="Find me a book",
            record=_make_root_record(planner),
            planner=planner,
            tasks=tasks,
        )

        json.dumps(row["tasks"])  # what the JSONB column does; must not raise
        assert "<DeferredBookQuery similar>" in json.dumps(row["tasks"])


@pytest.fixture
def chat_run_store():
    """The `ChatRunStore` that `ctx.store(ChatRunStore)` builds.

    The real `RequestContext.store` still runs, so `session_factory.begin()` is
    entered and this class is constructed on whatever session it hands over —
    which is what `test_production_opens_its_own_session` reads back.
    `insert_run` has to be an `AsyncMock`: a plain `MagicMock` return value is
    not awaitable, and the `TypeError` would be swallowed as a failed
    recording rather than surfacing as a failed test.
    """
    with patch("app.orchestration.run_recorder.ChatRunStore") as cls:
        cls.return_value.insert_run = AsyncMock()
        yield cls


class TestRecordChatRun:
    async def test_missing_record_records_nothing(self, make_request_context):
        # app_env="development" (not "test") so this exercises the
        # record-is-None guard specifically, not the env-based skip
        ctx = make_request_context(app_env="development")

        with patch("app.orchestration.run_recorder.save_file") as mock_save, patch(
            "app.orchestration.run_recorder.ChatRunStore"
        ) as mock_store_cls:
            await record_chat_run(ctx, None)

        mock_save.assert_not_called()
        mock_store_cls.assert_not_called()

    async def test_test_env_records_nothing(self, make_request_context):
        """Hermetic by default: the fixture's `app_env` is "test", so a suite
        that forgets to set one writes no file and opens no session."""
        ctx = make_request_context(app_env="test")
        planner = _make_planner_record()

        with patch("app.orchestration.run_recorder.save_file") as mock_save, patch(
            "app.orchestration.run_recorder.ChatRunStore"
        ) as mock_store_cls:
            await record_chat_run(
                ctx, _make_root_record(planner), _make_workflow(planner)
            )

        mock_save.assert_not_called()
        mock_store_cls.assert_not_called()
        ctx.session_factory.assert_not_called()

    async def test_production_writes_one_row_and_no_file(
        self, make_request_context, chat_run_store
    ):
        """Cloud Run's filesystem is in-memory, so the row is the only durable
        copy a deployed turn gets — and the only reason `/chat_runs` and the
        eval reports have anything to read."""
        ctx = make_request_context(app_env="production")
        planner = _make_planner_record()

        with patch("app.orchestration.run_recorder.save_file") as mock_save:
            await record_chat_run(
                ctx, _make_root_record(planner), _make_workflow(planner)
            )

        mock_save.assert_not_called()
        insert_run = chat_run_store.return_value.insert_run
        insert_run.assert_awaited_once()
        row = insert_run.await_args.args[0]
        assert row["chat_id"] == ctx.user_message.id
        assert row["session_id"] == "sess_1"
        assert row["user_message"] == "Find me a book"
        assert row["planner"]["ok"] is True

    async def test_production_opens_its_own_session(
        self, make_request_context, chat_run_store
    ):
        """Like the token debit: this runs from `_finalize`, which is shielded
        and outlives the request, so nothing opened at the request boundary is
        still there. `.begin()`, so the block commits — `insert_run` only
        stages the row."""
        ctx = make_request_context(app_env="production")
        planner = _make_planner_record()

        await record_chat_run(ctx, _make_root_record(planner), _make_workflow(planner))

        factory = ctx.session_factory
        factory.begin.assert_called_once_with()
        factory.assert_not_called()
        opened = factory.begin.return_value.__aenter__.return_value
        chat_run_store.assert_called_once_with(opened)

    async def test_a_failed_insert_is_swallowed(
        self, make_request_context, chat_run_store
    ):
        ctx = make_request_context(app_env="production")
        planner = _make_planner_record()
        chat_run_store.return_value.insert_run = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        # must not raise — a lost row cannot cost the user their reply
        await record_chat_run(ctx, _make_root_record(planner), _make_workflow(planner))

    async def test_development_writes_files_only(self, make_request_context):
        ctx = make_request_context(app_env="development")
        planner = _make_planner_record()

        with patch("app.orchestration.run_recorder.save_file") as mock_save, patch(
            "app.orchestration.run_recorder.ChatRunStore"
        ) as mock_store_cls:
            await record_chat_run(
                ctx, _make_root_record(planner), _make_workflow(planner)
            )

        # two files, both inside the turn's own directory: the run as a span
        # list, then the conversation (no writer or task runner on this turn)
        assert mock_save.call_count == 2
        flat_call, convo_call = mock_save.call_args_list

        # the chat_id names the folder now, not each file in it — so a turn's
        # artifacts sit together and a new one is added without renaming
        chat_id = ctx.user_message.id
        turn_dir = FilesLocationConstants.EXPORT_DIR / chat_id
        assert flat_call.kwargs == {"file_name": "record", "path": turn_dir}
        assert convo_call.kwargs == {"file_name": "convo_history", "path": turn_dir}

        # one entry per operation, parent before child, and already serialized
        # — save_file receives jsonable data, not live envelopes
        spans = flat_call.args[0]
        assert all(isinstance(span, dict) for span in spans)
        assert [span.get("parent_id") for span in spans] == [None, spans[0]["id"]]
        # remove_empty_values drops the empty `steps` of a projected span, so
        # no row in the file carries a subtree
        assert not any("steps" in span for span in spans)

        # files *instead of* a row, not alongside one: a local turn finishes
        # whether or not Postgres is up
        mock_store_cls.assert_not_called()
        ctx.session_factory.assert_not_called()

    async def test_file_failure_is_swallowed(self, make_request_context):
        ctx = make_request_context(app_env="development")
        planner = _make_planner_record()

        with patch(
            "app.orchestration.run_recorder.save_file",
            side_effect=OSError("disk full"),
        ):
            # must not raise — recording never breaks the chat response
            await record_chat_run(
                ctx, _make_root_record(planner), _make_workflow(planner)
            )
