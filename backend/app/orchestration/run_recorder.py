"""Record each orchestrated chat turn.

The single place that decides which sink a run goes to — one per environment,
and never more than one:

- **production** — one `chat_runs` row, which is the only durable copy a
  deployed turn gets. Files are never the production sink: Cloud Run's
  filesystem is in-memory, so each one would cost instance RAM and vanish with
  the instance.
- **development** — JSON files under `logs/<chat_id>/`, for local eyeballing.
  Deliberately no row: a local turn finishes whether or not Postgres is up, and
  the files carry more than the row does (the flattened span list, the
  conversation, exactly what the writer was fed).
- **test** — nothing.

The two sinks take the same turn and differ only in where it lands, so they are
selected in one place and wrapped in one `try` — see `record_chat_run`.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from airglider import OperationResult
from common.utils import (
    save_file,
    to_serializable,
    remove_empty_values,
    strip_zero_token_usage,
)
from config import FilesLocationConstants
from db.stores.chat_run_store import ChatRunStore
from app.common.request_context import RequestContext
from app.orchestration.triage import TriageWorkflow, TriageOutput
from app.orchestration.task_runner import TaskRunnerWorkflow, TaskRunnerOutput
from app.orchestration.write_recommendations import (
    GenerateRecommendationsExecutor,
    RecommendationsOutput,
)

from clients.messages import (
    APIMessage,
)

logger = logging.getLogger(__name__)


def build_chat_run_row(
    session_id: str,
    user_chat_id: str,
    user_message: str,
    record: OperationResult,
    planner: OperationResult[TriageOutput] | None,
    tasks: OperationResult[TaskRunnerOutput] | None = None,
    writer: OperationResult[RecommendationsOutput] | None = None,
) -> dict[str, Any]:
    """Map a finished turn onto ChatRunModel columns: promoted stats up front
    for cheap querying, full-fidelity JSONB envelopes last.

    The stats come from `record`, the orchestrator's root envelope, so they
    cover the whole turn. The JSONB columns stay the individual workflow
    envelopes — one per layer of the turn, `writer` being the third: the
    golden-test report reads accepted goals at the fixed path
    `planner.response.result.parse_result`, and re-rooting the column would
    silently empty every diff.

    `to_serializable`, not `to_summary()`, for all three: the reply's own
    summary is two counts, and the prose is the point — the SSE stream that
    carried it to the browser is not readable back, so this column is the only
    copy of what the turn actually said.
    """
    output = planner.result if planner else None
    return {
        "chat_id": user_chat_id,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc),
        "user_message": user_message,
        "ok": record.ok,
        "runtime_error": record.runtime_error.type if record.runtime_error else None,
        "duration_s": record.duration,
        "total_tokens": record.token_usage.total,
        "mermaid": output.diagram if output else None,
        "planner": to_serializable(planner) if planner is not None else None,
        "tasks": to_serializable(tasks) if tasks is not None else None,
        "writer": to_serializable(writer) if writer is not None else None,
    }


async def _insert_chat_run(
    request_context: RequestContext,
    record: OperationResult,
    planner: TriageWorkflow | None,
    task_runner: TaskRunnerWorkflow | None,
    writer: GenerateRecommendationsExecutor | None,
) -> None:
    """The production sink: one row, built by `build_chat_run_row`.

    Its own database session, like every other write inside a turn — this runs
    from `Orchestrator._finalize`, which is shielded and outlives the request,
    so nothing opened at the request boundary is still there to use. The
    `begin()` block commits it, which is why `insert_run` only stages.

    It takes no `messages`: the conversation is a development artifact, and the
    row's three JSONB envelopes already carry what each layer was given.
    """
    row = build_chat_run_row(
        session_id=request_context.session_id,
        user_chat_id=request_context.user_message.id,
        user_message=request_context.user_message.content,
        record=record,
        planner=planner.record if planner is not None else None,
        tasks=task_runner.record if task_runner is not None else None,
        writer=writer.record if writer is not None else None,
    )
    async with request_context.store(ChatRunStore) as store:
        await store.insert_run(row)
    logger.info("📋 Recorded chat run %s", row["chat_id"])


def _save_turn_files(
    request_context: RequestContext,
    record: OperationResult,
    task_runner: TaskRunnerWorkflow | None,
    writer: GenerateRecommendationsExecutor | None,
    messages: list[APIMessage] | None,
) -> None:
    """The development sink: one directory of JSON per turn, named by chat_id
    so a turn's artifacts sit together and a new one is added without renaming.

    Synchronous on purpose — `save_file` is, and every await point in
    `_finalize` is one more place a cancellation can land.

    It takes no `planner`: the planner's envelope is already inside `record`,
    which is written whole. The row needs it separately only because its
    columns are one envelope per layer.
    """
    user_dir = FilesLocationConstants.EXPORT_DIR / request_context.user_message.id

    # a flat view; strip_zero_token_usage only touches this local
    # eyeballing copy — the chat_runs row keeps every token_usage as
    # recorded, so a genuinely free step still serializes cost_usd: 0.0
    flat = to_serializable(record.flatten())
    flat = strip_zero_token_usage(remove_empty_values(flat))
    save_file(flat, file_name="record", path=user_dir)

    # saving the convo history
    save_file(messages, file_name="convo_history", path=user_dir)

    # saving the writter. Both of these are None on a turn that never
    # planned (small talk, a refusal) and the writer is None again when
    # it declined — without the guards the AttributeError lands in
    # `record_chat_run`'s except and the whole recording is logged as failed.
    if writer is not None:
        save_file(to_serializable(writer.record), file_name="writer", path=user_dir)

    # save task runner output: one `TaskResult` per goal — the node's
    # output (with its `preview` books) plus its duration, token counts
    # and error — which is the turn's source of truth
    if task_runner is not None:
        dev_gen = {
            # exactly what the writer was fed: RecommendationsInput
            # takes list(task_results.values())
            "task_results": task_runner.result,
            # thin for the other reason: `record.input` is built by
            # to_record_input, where each result's to_summary() wins
            "writer_input_as_recorded": writer.record.input if writer else None,
        }
        save_file(dev_gen, file_name="dev_gen", path=user_dir)


async def record_chat_run(
    request_context: RequestContext,
    # the one place the tree shape is required rather than incidental — the
    # dev sink writes `record.flatten()`
    record: OperationResult,
    planner: TriageWorkflow | None = None,
    task_runner: TaskRunnerWorkflow | None = None,
    writer: GenerateRecommendationsExecutor | None = None,
    messages: list[APIMessage] | None = None,
) -> None:
    """Hand a finished turn to this environment's sink, and never raise.

    One `try` around the choice rather than one inside each sink, because the
    rule is the same for both: recording must not cost the user their reply.

    That swallowing is also why a failure in here reaches
    `Orchestrator._finalize` as a timeout and never as an error — nothing gets
    out, so the only thing `wait_for` can surface is its own `TimeoutError`.
    The traceback is this log line, not one at the call site. (Which also means
    `SAVE_LOG_TIMEOUT` stopped being decorative on 2026-09-23: the production
    sink is the first await this function has ever had.)
    """
    if not request_context or record is None:
        user_message_id = (
            request_context.user_message.id if request_context else "unknown"
        )
        logger.warning(
            f"record_chat_run: missing request_context or record "
            f"for chat_id={user_message_id}"
        )
        return

    try:
        if request_context.app_env == "production":
            await _insert_chat_run(
                request_context, record, planner, task_runner, writer
            )
        elif request_context.app_env == "development":
            _save_turn_files(request_context, record, task_runner, writer, messages)
    except Exception:
        logger.exception("Failed to record chat run")
