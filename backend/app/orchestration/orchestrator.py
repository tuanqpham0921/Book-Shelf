import asyncio
import logging
import time
from typing import Any, Coroutine

from config import AppConfig
from app.common.sse_stream import SSEStream
from app.common.request_context import RequestContext

from app.domains.base_workflow import FailedGoalOutput
from app.domains.node_input import NodeInput
from app.domains.project.find_project_info import ProjectInfoNodeTypeEnum
from app.registry import UnknownNodeTypeEnum
from app.orchestration.triage import TriageWorkflow
from app.orchestration.task_runner import (
    TaskResult,
    TaskRunnerInput,
    TaskRunnerWorkflow,
)
from app.orchestration.run_recorder import flat_record, record_chat_run
from app.orchestration.token_budget import (
    OUT_OF_TOKENS_MESSAGE,
    SITE_BUDGET_ENFORCED_IN,
    SITE_OUT_OF_TOKENS_MESSAGE,
    debit_session_tokens,
    read_site_spend,
    start_session_turn,
)
from app.orchestration.validation import refusal_for, validate_user_message
from app.orchestration.write_reply import (
    GenerationExecutor,
    RecommendationsInput,
)
from airglider import OperationResult, RuntimeErrorInfo

from clients.messages import (
    APIMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

SAVE_LOG_TIMEOUT = 60  # seconds
CLOSE_SSE_STREAM_TIMEOUT = 10  # seconds
CONVERSATION_TIMEOUT = 120  # seconds

# Above the engine's own worst case, not level with it — the same ladder
# `db/async_engine.py` builds out of this constant, one rung further out. A
# debit can wait `pool_timeout` for a connection and *then* run its statement,
# so a ceiling equal to `DATABASE_TIMEOUT` would cancel a charge that was about
# to succeed. This is the one cleanup step with money attached, and cancelling
# it mid-statement is also the one cancel here that can reach a live
# connection. Leave it the loosest thing that still terminates.
DEBIT_TOKENS_TIMEOUT = AppConfig.DATABASE_TIMEOUT * 3  # seconds

# Relayed by the reply stage as the reason an out-of-scope portion was not done.
OUT_OF_SCOPE_REASON = "it is outside what a book assistant does"


async def _best_effort(
    coro: Coroutine[Any, Any, Any], timeout: float, what: str, turn_id: str
) -> None:
    """Run one cleanup step under a ceiling, and never raise.

    The ceiling is not redundant with the database's own timeouts, because
    `_finalize` runs inside `asyncio.shield` — nothing outside can stop these,
    so this is what makes them terminate at all. It also covers what Postgres
    cannot see: the wait for a connection, the connect handshake, and the two
    steps here that never touch a database.

    **The timeout gets its own branch because it is the only thing that
    normally arrives.** `debit_session_tokens` and `record_chat_run` both
    swallow their own exceptions, so a step that broke has already been logged
    with its traceback by the time we get here; what reaches this function is
    the `TimeoutError` that `wait_for` raises after cancelling them — and their
    own `except Exception` could not have caught that, since `CancelledError`
    has been a `BaseException` since 3.8. Logging both cases as one anonymous
    warning lost the distinction and the cause with it.
    """
    try:
        await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        logger.warning(
            "⏱️ %s gave up after %ss and was cancelled — turn %s",
            what,
            timeout,
            turn_id,
        )
    except Exception:
        # Reachable from `sse_stream.close()`, which catches nothing of its
        # own. With the traceback: an exception that got this far is a surprise.
        logger.exception("%s failed — turn %s", what, turn_id)


class Orchestrator:
    """Main orchestration engine for processing user queries through AI pipelines."""

    reply_failure_message = (
        "Sorry, I couldn't finish writing my reply this time.\n"
        "Please try sending your message again."
    )

    def __init__(self):
        pass

    async def run(self, request_context: RequestContext):
        """Run orchestration with SSE streaming."""

        sse_stream = request_context.sse_stream
        # Bound before the try so a cancellation mid-await still leaves them
        # for the finally block — each workflow mutates its own .record in
        # place and re-raises rather than returning it.
        triage_workflow: TriageWorkflow | None = None
        task_runner: TaskRunnerWorkflow | None = None
        writer: GenerationExecutor | None = None
        # Root of the turn's trace tree; the workflow envelopes are hung off it
        # in the finally block, so ok/duration/token_usage cover the whole turn.
        record = OperationResult(
            name=f"orchestrator_{request_context.user_message.id}",
            input={
                "raw": request_context.user_message.content,
                "pass_validation": request_context.user_message.pass_validation,
            },
        )
        # empty until the message passes validation — an unvalidated one is not
        # an APIMessage, and a refused turn has nothing to record here
        messages: list[APIMessage] = []
        time_start = time.perf_counter()

        # Core work
        try:
            # First and unconditionally: this id exists before any work
            # starts, so the client can attach feedback even if the turn later
            # errors, times out, or is stopped before 'complete' fires.
            await sse_stream.send_chat_id(request_context.user_message.id)

            # Opens the turn: one round trip that creates the sessions row on a
            # first message and reports the balance. Attached by hand because
            # `run` builds this root rather than being a unit of work itself,
            # so nothing is in scope to adopt the step — and attached before
            # the unwrap, so a read that failed is still on the record.
            await sse_stream.send_ui_loading("checking budget...")
            budget_step = await start_session_turn(request_context)
            record.add_step(budget_step)
            remaining_tokens = budget_step.unwrap()
            record.add_details(f"session tokens remaining: {remaining_tokens}")
            if remaining_tokens <= 0:
                record.add_details("refused: session out of tokens")
                logger.warning(
                    f"🚫 Out of tokens, refusing the turn: "
                    f"session={request_context.session_id}"
                )
                await sse_stream.send_error(OUT_OF_TOKENS_MESSAGE)
                return

            if request_context.app_env == SITE_BUDGET_ENFORCED_IN:
                site_step = await read_site_spend(request_context)
                record.add_step(site_step)
                site_spent = site_step.unwrap()
                record.add_details(f"site tokens spent today: {site_spent}")
                if site_spent >= AppConfig.SITE_DAILY_TOKEN_BUDGET:
                    record.add_details("refused: site out of tokens for today")
                    logger.warning(
                        f"🚫 Site daily budget spent ({site_spent}), refusing "
                        f"the turn: session={request_context.session_id}"
                    )
                    await sse_stream.send_error(SITE_OUT_OF_TOKENS_MESSAGE)
                    return

            # The message arrives unvalidated, and nothing past this point reads
            # it until it passes. Unwrapped like the balance read: a check that
            # returned no verdict stops the turn rather than waving it through.
            await sse_stream.send_ui_loading("reading your message...")
            validation_step = await validate_user_message(request_context)
            record.add_step(validation_step)
            validation = validation_step.unwrap()
            if reply := refusal_for(validation):
                # a handled turn, not a failure — the same shape as triage's
                # fixed replies: the answer, then 'complete'
                request_context.user_message.pass_validation = False
                record.add_details(f"refused by validation: {validation!r}")
                await sse_stream.send_chars(reply)
                await sse_stream.send(
                    "complete",
                    {"status": "completed", "chat_id": request_context.user_message.id},
                )
                return

            request_context.user_message.pass_validation = True
            messages.append(request_context.user_message)

            await sse_stream.send_ui_loading("starting conversation...")
            triage_workflow = TriageWorkflow(request_context, messages=messages)
            await asyncio.wait_for(
                triage_workflow(
                    NodeInput(instruction=request_context.user_message.content),
                    # use_caching=False,
                ),
                timeout=CONVERSATION_TIMEOUT,
            )

            # No plan when triage handled the turn without planning (small
            # talk, a refusal, a project question and nothing else, a cache
            # miss on a failed planner): `parse_result` is None and there is
            # nothing for the runner to execute.
            #
            # `record.unwrap()`, because `unwrap` lives on the envelope and not
            # on the workflow — `triage_workflow.record` is what the decorator
            # built. A triage that *failed* stops the turn right here: the
            # `StepFailure` lands in the `except Exception` below, which stamps
            # it on the turn and sends the generic error. That is on top of
            # whatever triage already said for itself, and deliberate — a
            # failed triage read as "no plan" would answer the turn with
            # silence.
            # TODO: if something goes wrong
            # maybe check if the planner and triage has no task
            # then response that hallucationation happended and no retries yet
            triage_output = triage_workflow.record.unwrap()
            plan = triage_output.parse_result

            # What the reply is written from: the project facts triage looked
            # up without planning, first because they came first, then every
            # goal the plan ran. Any one part alone is enough to write from.
            results: list[TaskResult] = []
            if triage_output.project_info:
                results.append(
                    TaskResult(
                        task_id="triage",
                        node_type=ProjectInfoNodeTypeEnum.REQUEST.value,
                        output=triage_output.project_info,
                    )
                )
            if plan and plan.accepted_goals:
                await sse_stream.send_ui_loading("starting tasks...")
                task_runner = TaskRunnerWorkflow(request_context, messages=messages)
                await asyncio.wait_for(
                    # the only place triage and the runner are wired together,
                    # so the runner never learns a triage layer exists
                    task_runner(TaskRunnerInput(plan=plan)),
                    timeout=CONVERSATION_TIMEOUT,
                )
                results.extend(task_runner.result.task_results.values())
            # Last, what the planner set aside as not a book assistant's job —
            # as failures, so the reply says so instead of dropping it. Alone,
            # it is still a reply: "what's the weather?" plans nothing.
            if plan and plan.out_of_scope:
                results.extend(
                    TaskResult(
                        task_id="planjane",
                        node_type=UnknownNodeTypeEnum.UNKNOWN.value,
                        output=FailedGoalOutput(
                            goal_instruction=portion, reason=OUT_OF_SCOPE_REASON
                        ),
                    )
                    for portion in plan.out_of_scope
                )
            if results:
                writer = await self._write_reply(request_context, results, messages)
                if not writer.record.ok:
                    # the sections above are all the user has; without this
                    # the stream ends on them with no reply and no reason
                    await sse_stream.send_error(self.reply_failure_message)
            elif task_runner is not None:
                # a plan whose every goal was unreachable: nothing to write
                # from, so the stage would only invent evidence
                logger.warning("No task results to write a reply from")
                
            # Here rather than after each await, so the timeout/cancel paths
            # record their partial work too. isinstance-guarded rather than
            # letting add_step raise: a raise in this finally would replace the
            # exception in flight and skip the recording and stream close below.
            for workflow in (triage_workflow, task_runner, writer):
                step = getattr(workflow, "record", None)
                if isinstance(step, OperationResult):
                    record.add_step(step)
            record.ok = (
                record.runtime_error is None
                and bool(record.steps)
                and all(step.ok for step in record.steps)
            )
            record.timing.duration = round(time.perf_counter() - time_start, 2)

            # chat_id lets the client attach feedback to the chat_runs row;
            # log_record is the turn's trace so far, for the reply's log
            # button (ok and duration are stamped later, in the finally)
            await sse_stream.send(
                "complete",
                {
                    "status": "completed",
                    "chat_id": request_context.user_message.id,
                    "log_record": flat_record(record),
                },
            )
            await sse_stream.close()
            logger.info("✅ Orchestration completed successfully")
        except asyncio.CancelledError as e:
            # client disconnected mid-turn — the finally block still records
            # what we have, then this propagates so the task is really cancelled
            record.runtime_error = RuntimeErrorInfo.from_exception(e)
            logger.warning(
                f"⚠️ Orchestration cancelled: chat_id={request_context.user_message.id}"
            )
            raise
        except TimeoutError as e:
            record.runtime_error = RuntimeErrorInfo.from_exception(e)
            record.add_details("Orchestration Task timed out")
            logger.warning(
                f"⚠️ Orchestration timed out: chat_id={request_context.user_message.id}"
            )
            await sse_stream.send_error("The request took too long to process.")
        except Exception as e:
            record.runtime_error = RuntimeErrorInfo.from_exception(e)
            logger.exception(f"❌ Unhandled orchestrator error: {e}")
            await sse_stream.send_error(
                "Hmm... something went wrong while processing your query."
            )
        finally:
            # One shielded unit, not two. A second cancellation landing on this
            # task (EventSourceResponse re-cancels every checkpoint on
            # disconnect) is a BaseException, so it would fly past
            # `except Exception` mid-cleanup and skip sse_stream.close().
            # Shielding the whole sequence means close() still runs — we just
            # stop waiting for it here.
            try:
                await asyncio.shield(
                    self._finalize(
                        request_context,
                        record,
                        triage_workflow,
                        task_runner,
                        writer,
                        messages,
                        sse_stream,
                    )
                )
            except asyncio.CancelledError:
                logger.warning(
                    f"cleanup cancelled for chat_id={request_context.user_message.id}, "
                    "continuing in the background"
                )

    @staticmethod
    async def _write_reply(
        request_context: RequestContext,
        results: list[TaskResult],
        messages: list[APIMessage],
    ) -> GenerationExecutor:
        """Write the turn's reply from everything triage and the plan produced.

        The third layer of the turn, and the only one that speaks prose. It is
        wired here rather than reached through the registry because it is not a
        capability: no goal targets it, nothing depends on it, and it runs once
        per turn whatever the plan was. That is the same reason `Triage` is a
        workflow in `orchestration/` rather than a node — and it keeps the
        import pointing downward, since `orchestration/` may read `domains/`.

        Returns the workflow so the caller can hang its record on the turn's
        tree, matching how triage and the runner are handled. The caller never
        passes an empty list — the `ValueError` in the stage's `run` is what
        that would hit.
        """
        writer = GenerationExecutor(request_context, messages=messages)
        await asyncio.wait_for(
            writer(RecommendationsInput(results=results)),
            timeout=CONVERSATION_TIMEOUT,
        )
        return writer

    @staticmethod
    async def _finalize(
        request_context: RequestContext,
        record: OperationResult,
        triage_workflow: TriageWorkflow | None,
        task_runner: TaskRunnerWorkflow | None,
        writer: GenerationExecutor | None,
        messages: list[APIMessage] | None,
        sse_stream: SSEStream,
    ) -> None:
        """Charge the turn, record it, then close the stream. Best-effort —
        never lets a slow/failing step here take down the others, or the caller.

        The debit goes first because it is the only one of the three with money
        attached, and it must not queue behind a dev-only file dump. Each step
        gets its own ceiling and its own log line — see `_best_effort`, which
        is also where the reason a ceiling is still needed lives.

        `record.token_usage.total` is already final here: the `add_step` roll-up
        in `run`'s finally happens before the shield.
        """
        turn_id = request_context.user_message.id

        await _best_effort(
            debit_session_tokens(request_context, record),
            DEBIT_TOKENS_TIMEOUT,
            "debit_session_tokens",
            turn_id,
        )

        await _best_effort(
            record_chat_run(
                request_context,
                record,
                triage_workflow,
                task_runner,
                writer,
                messages,
            ),
            SAVE_LOG_TIMEOUT,
            "record_chat_run",
            turn_id,
        )

        await _best_effort(
            sse_stream.close(),
            CLOSE_SSE_STREAM_TIMEOUT,
            "sse_stream.close",
            turn_id,
        )
