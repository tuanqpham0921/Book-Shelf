"""Tests for TriageWorkflow step/output routing."""

from unittest.mock import AsyncMock, patch

import pytest
from openai.types.chat.parsed_function_tool_call import (
    ParsedFunction,
    ParsedFunctionToolCall,
)

from clients.messages import AssistantMessage, UserMessage
from app.common.tools import ClarificationType, ClarifyingQuestion, SecurityReview
from app.domains.books.find_by_title import FindTitleNodeTypeEnum
from app.domains.node_input import NodeInput
from app.domains.project.find_project_info import ProjectInfoArgs
from app.orchestration.triage import TriageOutput, TriageWorkflow
from app.orchestration.triage import cache
from app.orchestration.triage.cache import load_cached_parse_output
from app.orchestration.triage.executor import ENDING_TOOLS, build_route_request
from app.orchestration.triage.tools import PlanJane
from app.domains.planjane import PlanJaneOutput, SystemGoal
from airglider import OperationResult, Response, RuntimeErrorInfo, TokenUsage
from common.utils import load_json, save_file, to_serializable


@pytest.fixture
def orchestrator(make_request_context):
    # make_request_context comes from tests/conftest.py
    return TriageWorkflow(
        make_request_context(user_message=UserMessage(content="test"))
    )


def _make_goal():
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


def _make_orchestration_output() -> TriageOutput:
    goal = _make_goal()
    return TriageOutput(
        session_id="sess_1",
        # diagram lives on the plan now — TriageOutput.diagram reads through
        parse_result=PlanJaneOutput(accepted_goals=[goal], diagram="graph TD;\nA-->B;"),
    )


class TestTriageWorkflowSteps:
    # storing the parse output moved from an add_step override into
    # run() itself — see TriageWorkflow.run. add_step itself now lives on
    # OperationResult (airglider), where steps/token_usage do.

    def test_merges_token_usage_from_step_result(self, orchestrator):
        step = OperationResult(
            ok=True,
            response=Response(result=PlanJaneOutput()),
            token_usage=TokenUsage(total=100, prompt=60, completion=40),
        )
        orchestrator.record.add_step(step)
        assert orchestrator.record.token_usage.total == 100
        assert orchestrator.record.token_usage.prompt == 60
        assert orchestrator.record.token_usage.completion == 40

    def test_shared_messages_list_appended_by_children(self, orchestrator):
        # TODO: fix this
        msg = AssistantMessage(content="hello")
        orchestrator.messages.append(msg)
        assert msg in orchestrator.messages

    def test_appends_to_result_steps(self, orchestrator):
        step = OperationResult(
            ok=True, name="some_step", response=Response(result=PlanJaneOutput())
        )
        orchestrator.record.add_step(step)
        assert step in orchestrator.record.steps


CACHED_MESSAGE = "Show me books similar to Pride and Prejudice"


@pytest.fixture
def cache_dir(tmp_path):
    """The dev cache, relocated to a tmp dir with one message mapped. Both
    sides of a `cache_mapping` entry are the message itself — it is also the
    file name."""
    with patch.object(cache, "CACHE_DIR", tmp_path), patch.dict(
        cache.cache_mapping, {CACHED_MESSAGE: CACHED_MESSAGE}, clear=True
    ):
        yield tmp_path


class TestLoadCachedParseOutput:
    """The dev-only plan replay.

    A cache file is a bare `PlanJaneOutput` dump now — no enclosing triage
    record, so no `output.parse_result` to reach through — and it is written
    with `remove_empty=False`. Those two facts are what let the loader drop its
    unwrapping and its `depends_on` backfill, so they are what these pin, along
    with what each *unusable* file does instead: returning None is what sends
    the turn to the real planner.
    """

    @staticmethod
    def _write(data, path, *, remove_empty=False, name=CACHED_MESSAGE):
        save_file(data, file_name=name, path=path, remove_empty=remove_empty)

    def test_replays_a_bare_plan_dump(self, cache_dir):
        plan = PlanJaneOutput(accepted_goals=[_make_goal()], diagram="graph TD;")
        self._write(plan, cache_dir)

        replayed = load_cached_parse_output(CACHED_MESSAGE)

        assert replayed is not None
        assert replayed.diagram == "graph TD;"
        assert [goal.id for goal in replayed.accepted_goals] == ["1"]
        assert replayed.accepted_goals[0].depends_on == []

    def test_an_unmapped_message_is_never_read(self, cache_dir):
        self._write(PlanJaneOutput(accepted_goals=[_make_goal()]), cache_dir)

        assert load_cached_parse_output("a message nobody cached") is None

    def test_a_mapped_message_with_no_file_falls_through(self, cache_dir):
        # cache_mapping outlives the files it names — two entries are mapped
        # with nothing on disk. load_json logs and returns None, so this is a
        # planner call, not a crash inside triage.
        assert load_cached_parse_output(CACHED_MESSAGE) is None

    def test_a_dump_that_dropped_its_empty_lists_falls_through(self, cache_dir):
        # save_file's default. `SystemGoal.depends_on` is required with no
        # default, so a goal that depends on nothing loses the field and the
        # whole plan fails to validate — which is why the file must be written
        # with remove_empty=False now that the loader no longer backfills it.
        self._write(
            PlanJaneOutput(accepted_goals=[_make_goal()]), cache_dir, remove_empty=True
        )

        assert load_cached_parse_output(CACHED_MESSAGE) is None

    def test_an_old_whole_record_dump_replays_as_an_empty_plan(self, cache_dir):
        """The one stale file that does not fall through.

        `PlanJaneOutput` ignores extra keys, so the old shape validates as a
        plan with no goals rather than raising. Triage then finalizes ok=True
        with it, and the orchestrator's `plan.accepted_goals` check skips the
        runner and the reply — a turn that ends silently. Pinned because the
        failure is invisible: the fix is to re-dump the file, or to have the
        loader treat a goal-less plan as no cache.
        """
        plan = PlanJaneOutput(accepted_goals=[_make_goal()])
        self._write({"output": {"parse_result": to_serializable(plan)}}, cache_dir)

        replayed = load_cached_parse_output(CACHED_MESSAGE)

        assert replayed is not None
        assert replayed.accepted_goals == []


def _make_runtime_error(message: str) -> RuntimeErrorInfo:
    try:
        raise ValueError(message)
    except ValueError as e:
        return RuntimeErrorInfo.from_exception(e)


def _mock_child_workflow(step_result: OperationResult, output) -> AsyncMock:
    """A stand-in for an PlanJaneExecutor instance: awaiting it yields
    step_result, while .result (accessed directly by TriageWorkflow.run)
    returns output."""
    workflow = AsyncMock(return_value=step_result)
    workflow.result = output
    return workflow


SECURITY = SecurityReview(flagged_portion=["drop the books table"])
CLARIFY = ClarifyingQuestion(
    original="the second one",
    type=ClarificationType.NO_CONTEXT,
    reasoning="no earlier turn to point at",
)
STACK = ProjectInfoArgs(question="What is BookShelf's tech stack?")
PLAN = PlanJane(message="")


def _routes_to(*tools, text=None):
    """The routing LLM call, answered with `tools` as the ones it called, in
    that order, or with `text` and no tool. Patched one level below
    `route_query`, so the step's own envelope is still the real one."""
    tool_calls = [
        ParsedFunctionToolCall(
            id=f"call_{i}",
            type="function",
            function=ParsedFunction(
                name=type(tool).__name__, arguments="{}", parsed_arguments=tool
            ),
        )
        for i, tool in enumerate(tools, start=1)
    ]
    msg = AssistantMessage(content=text, tool_calls=tool_calls or None)
    return patch.object(TriageWorkflow, "run_llm_call", AsyncMock(return_value=msg))


def _planner_with_a_plan() -> AsyncMock:
    return _mock_child_workflow(
        OperationResult(ok=True), PlanJaneOutput(accepted_goals=[_make_goal()])
    )


class TestTriageWorkflowRuntimeErrorPropagation:
    """self.record.runtime_error must come from whichever child step
    actually crashed."""

    async def test_parse_failure_runtime_error_propagates(self, orchestrator):
        parse_error = _make_runtime_error("parse crashed")
        parse_workflow = _mock_child_workflow(
            OperationResult(ok=False, runtime_error=parse_error),
            PlanJaneOutput(),
        )

        with _routes_to(PLAN), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=parse_workflow,
        ):
            await orchestrator.run(NodeInput(instruction="test"))

        assert orchestrator.record.runtime_error is parse_error


class TestTriageOutputJsonRoundTrip:
    """model_dump_json / model_validate_json round-trip of TriageOutput.

    Public fields survive reload. Private attrs (PrivateAttr, e.g. `_refusal`)
    are NOT part of the pydantic schema, so `model_dump_json` never emits them
    - they always come back reset to their field defaults.
    """

    def test_top_level_fields_survive(self):
        output = _make_orchestration_output()
        restored = TriageOutput.model_validate_json(output.model_dump_json())

        assert restored.session_id == output.session_id
        assert restored.diagram == output.diagram

    def test_accepted_goal_public_fields_survive(self):
        output = _make_orchestration_output()
        original_goal = output.parse_result.accepted_goals[0]

        restored = TriageOutput.model_validate_json(output.model_dump_json())
        restored_goal = restored.parse_result.accepted_goals[0]

        assert restored_goal.instruction == original_goal.instruction
        assert restored_goal.confidence == original_goal.confidence
        assert restored_goal.target_node_type == original_goal.target_node_type

    def test_goal_private_attrs_do_not_survive_round_trip(self):
        output = _make_orchestration_output()
        original_goal = output.parse_result.accepted_goals[0]
        assert original_goal._refusal is True

        restored = TriageOutput.model_validate_json(output.model_dump_json())
        restored_goal = restored.parse_result.accepted_goals[0]

        # `id` is a public field now, so it does survive — unlike the refusal
        # private attrs, which come back at their defaults
        assert restored_goal.id == original_goal.id
        assert restored_goal._refusal is False
        assert restored_goal._refusal_reasons == []


class TestTriageOutputSaveFileRoundTrip:
    """save_file/load_json (common.utils) go through to_serializable, which
    walks __pydantic_private__ - so unlike model_dump_json/model_validate_json,
    private attrs (_refusal, _refusal_reasons, ...) do survive this round
    trip. The catch: load_json hands back plain dicts, not reconstructed
    SystemGoal instances.
    """

    def test_goal_private_attrs_survive(self, tmp_path):
        output = _make_orchestration_output()
        original_goal = output.parse_result.accepted_goals[0]

        save_file(output, file_name="orchestration_output_goal", path=tmp_path)
        loaded = load_json("orchestration_output_goal", path=tmp_path)
        loaded_goal = loaded["parse_result"]["accepted_goals"][0]

        assert loaded_goal["_refusal"] == original_goal._refusal
        assert loaded_goal["_refusal_reasons"] == original_goal.refusal_reasons


class TestRouting:
    """The pick between the cache and the planner: `PlanJane` sends the
    message on, `SecurityReview` and `ClarifyingQuestion` get their reply and
    end the turn without a plan, no tool means the model's own text is the
    reply, and a pick that fails sends the message on. `ProjectInfoArgs` is
    `TestProjectFacts`, below."""

    @pytest.mark.parametrize("tool", [SECURITY, CLARIFY])
    async def test_a_message_not_for_the_planner_gets_its_reply_and_no_plan(
        self, orchestrator, tool
    ):
        with _routes_to(tool), patch.object(
            orchestrator.sse_stream, "send_chars", new_callable=AsyncMock
        ) as send_chars, patch(
            "app.orchestration.triage.executor.PlanJaneExecutor"
        ) as planner_cls:
            record = await orchestrator(NodeInput(instruction="test"))

        send_chars.assert_awaited_once_with(tool())
        planner_cls.assert_not_called()
        # a handled turn: ok, and no plan for the orchestrator to run
        assert record.ok
        assert orchestrator.result.parse_result is None

    async def test_planjane_sends_the_whole_message_on(self, orchestrator):
        planner = _planner_with_a_plan()
        with _routes_to(PLAN), patch.object(
            orchestrator.sse_stream, "send_chars", new_callable=AsyncMock
        ) as send_chars, patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(NodeInput(instruction="hi! books like Dune"))

        planner.assert_awaited_once_with(NodeInput(instruction="hi! books like Dune"))
        send_chars.assert_not_awaited()
        assert record.ok
        assert orchestrator.result.parse_result.accepted_goals

    async def test_no_tool_sends_the_models_text_and_no_plan(self, orchestrator):
        with _routes_to(text="Hi! What would you like to read?"), patch.object(
            orchestrator.sse_stream, "send_chars", new_callable=AsyncMock
        ) as send_chars, patch(
            "app.orchestration.triage.executor.PlanJaneExecutor"
        ) as planner_cls:
            record = await orchestrator(NodeInput(instruction="hi!"))

        send_chars.assert_awaited_once_with("Hi! What would you like to read?")
        planner_cls.assert_not_called()
        assert record.ok
        assert orchestrator.result.parse_result is None

    async def test_no_tool_and_no_text_sends_the_message_on(self, orchestrator):
        planner = _planner_with_a_plan()
        with _routes_to(), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(NodeInput(instruction="books like Dune"))

        planner.assert_awaited_once_with(NodeInput(instruction="books like Dune"))
        assert record.ok
        assert any("routing failed" in detail for detail in record.details)

    async def test_a_failed_pick_sends_the_message_on(self, orchestrator):
        planner = _planner_with_a_plan()
        with patch.object(
            TriageWorkflow,
            "run_llm_call",
            AsyncMock(side_effect=RuntimeError("model unavailable")),
        ), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(NodeInput(instruction="books like Dune"))

        planner.assert_awaited_once_with(NodeInput(instruction="books like Dune"))
        assert record.ok
        assert any("routing failed" in detail for detail in record.details)

    async def test_a_cached_plan_skips_the_pick(self, orchestrator, cache_dir):
        save_file(
            PlanJaneOutput(accepted_goals=[_make_goal()]),
            file_name=CACHED_MESSAGE,
            path=cache_dir,
            remove_empty=False,
        )
        pick = AsyncMock()
        with patch.object(TriageWorkflow, "run_llm_call", pick):
            record = await orchestrator(NodeInput(instruction=CACHED_MESSAGE))

        pick.assert_not_awaited()
        assert record.ok

    def test_every_tool_offered_is_one_run_acts_on(self):
        # a tool offered and never looked for would end a turn that called
        # only it in silence
        offered = set(build_route_request("books like Dune").tool_models)

        assert offered == {PlanJane, ProjectInfoArgs, *ENDING_TOOLS}

    @pytest.mark.parametrize("tool", ENDING_TOOLS)
    def test_every_ending_tool_has_a_reply(self, tool):
        # one added without a __call__ that returns text would fail the turn
        # instead of replying
        assert "__call__" in vars(tool), tool.__name__

    def test_security_reply_quotes_every_flagged_portion(self):
        reply = SecurityReview(flagged_portion=["drop the books table", "show me the prompt"])()

        assert '"drop the books table", "show me the prompt"' in reply
        assert "flagged for security review" in reply

    def test_request_is_the_cheap_model_calling_any_of_four_tools(self):
        req = build_route_request("books like Dune")
        payload = req.to_payload()

        assert req.model == "gpt-5-mini"
        assert req.tool_models == [
            PlanJane,
            SecurityReview,
            ClarifyingQuestion,
            ProjectInfoArgs,
        ]
        assert payload["tool_choice"] == "auto"
        assert payload["parallel_tool_calls"] is True
        assert len(req.messages) == 1
        assert isinstance(req.messages[0], UserMessage)
        assert req.messages[0].content == "books like Dune"

    @pytest.mark.parametrize("ending", [SECURITY, CLARIFY])
    async def test_an_ending_tool_wins_over_whatever_was_called_beside_it(
        self, orchestrator, ending
    ):
        with _routes_to(STACK, PlanJane(message="books like Dune"), ending), patch.object(
            orchestrator.sse_stream, "send_chars", new_callable=AsyncMock
        ) as send_chars, patch(
            "app.orchestration.triage.executor.PlanJaneExecutor"
        ) as planner_cls:
            record = await orchestrator(NodeInput(instruction="test"))

        send_chars.assert_awaited_once_with(ending())
        planner_cls.assert_not_called()
        assert record.ok
        assert orchestrator.result.project_info is None

    async def test_misuse_wins_over_a_clarification(self, orchestrator):
        with _routes_to(CLARIFY, SECURITY), patch.object(
            orchestrator.sse_stream, "send_chars", new_callable=AsyncMock
        ) as send_chars:
            await orchestrator(NodeInput(instruction="test"))

        send_chars.assert_awaited_once_with(SECURITY())


class TestProjectFacts:
    """`ProjectInfoArgs` is answered here by the project docs rather than
    planned. The answer rides on the output for the orchestrator's reply
    stage; the planner gets only what the message asks besides."""

    @pytest.fixture(autouse=True)
    def docs(self):
        # the docs service is the one outside call; faked at triage's import
        lookup = AsyncMock(return_value=OperationResult(ok=True, response=Response(result="FastAPI")))
        with patch("app.orchestration.triage.executor.ask_project_docs", lookup):
            yield lookup

    async def test_a_project_question_alone_is_answered_without_planning(
        self, orchestrator
    ):
        with _routes_to(STACK), patch.object(
            orchestrator.sse_stream, "send_chars", new_callable=AsyncMock
        ) as send_chars, patch(
            "app.orchestration.triage.executor.PlanJaneExecutor"
        ) as planner_cls:
            record = await orchestrator(NodeInput(instruction="what's your stack?"))

        planner_cls.assert_not_called()
        # the reply stage writes it up, not triage
        send_chars.assert_not_awaited()
        assert record.ok
        assert orchestrator.result.parse_result is None
        assert orchestrator.result.project_info.question == STACK.question
        assert orchestrator.result.project_info.answer == "FastAPI"

    async def test_a_failed_lookup_sends_the_whole_message_on(self, orchestrator, docs):
        docs.return_value = OperationResult(ok=False)
        planner = _planner_with_a_plan()
        with _routes_to(STACK, PlanJane(message="books like Dune")), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(
                NodeInput(instruction="what's your stack, and books like Dune?")
            )

        planner.assert_awaited_once_with(
            NodeInput(instruction="what's your stack, and books like Dune?")
        )
        assert record.ok
        assert orchestrator.result.project_info is None

    async def test_the_planner_gets_only_what_is_left(self, orchestrator):
        planner = _planner_with_a_plan()
        with _routes_to(STACK, PlanJane(message="books like Dune")), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(
                NodeInput(instruction="what's your stack, and books like Dune?")
            )

        planner.assert_awaited_once_with(NodeInput(instruction="books like Dune"))
        assert record.ok
        assert orchestrator.result.project_info is not None
        assert orchestrator.result.parse_result.accepted_goals

    @pytest.mark.parametrize(
        "picks",
        [
            # no split, so a remainder is only the model rewording the message
            [PlanJane(message="books like Dune")],
            # a split with nothing left written down
            [STACK, PlanJane(message="  ")],
        ],
    )
    async def test_otherwise_the_planner_reads_the_users_own_words(
        self, orchestrator, picks
    ):
        planner = _planner_with_a_plan()
        with _routes_to(*picks), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            await orchestrator(NodeInput(instruction="hi! books like Dune please"))

        planner.assert_awaited_once_with(
            NodeInput(instruction="hi! books like Dune please")
        )

    async def test_a_planner_that_planned_nothing_keeps_the_facts(
        self, orchestrator
    ):
        # "what's your stack, and the weather?": the planner turns the weather
        # down, and the stack still gets its reply
        planner = _mock_child_workflow(OperationResult(ok=False), PlanJaneOutput())
        with _routes_to(STACK, PlanJane(message="the weather?")), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(NodeInput(instruction="test"))

        assert record.ok
        assert orchestrator.result.project_info is not None
        assert not orchestrator.result.parse_result.accepted_goals

    async def test_a_planner_that_set_it_all_aside_still_gets_a_reply(
        self, orchestrator
    ):
        # "what's the weather?": nothing planned, but the out-of-scope part is
        # something the orchestrator's reply stage answers
        planner = _mock_child_workflow(
            OperationResult(ok=False), PlanJaneOutput(out_of_scope=["the weather?"])
        )
        with _routes_to(PLAN), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(NodeInput(instruction="the weather?"))

        assert record.ok
        assert orchestrator.result.parse_result.out_of_scope == ["the weather?"]

    async def test_without_facts_a_planner_that_planned_nothing_fails(
        self, orchestrator
    ):
        planner = _mock_child_workflow(OperationResult(ok=False), PlanJaneOutput())
        with _routes_to(PLAN), patch(
            "app.orchestration.triage.executor.PlanJaneExecutor",
            return_value=planner,
        ):
            record = await orchestrator(NodeInput(instruction="the weather?"))

        assert not record.ok


class TestClarifyingReply:
    """What calling a `ClarifyingQuestion` says, by its `type`."""

    @staticmethod
    def _ask(type: ClarificationType) -> ClarifyingQuestion:
        return ClarifyingQuestion(original="Duen", type=type, reasoning="r")

    @pytest.mark.parametrize("type", list(ClarificationType))
    def test_every_type_has_a_reply(self, type):
        # a type added without a case would send None and fail the turn
        assert isinstance(self._ask(type)(), str)

    def test_no_context_says_there_is_no_conversation_yet(self):
        assert "can't continue a conversation" in self._ask(ClarificationType.NO_CONTEXT)()

    def test_correction_quotes_the_part_to_fix(self):
        assert '"Duen"' in self._ask(ClarificationType.CORRECTION)()

    def test_ambiguous_and_unreadable_get_the_same_reply(self):
        reply = self._ask(ClarificationType.AMBIGUOUS)()

        assert reply.startswith("Sorry, I can't understand")
        assert reply == self._ask(ClarificationType.UNREADABLE)()


