"""Record each orchestrated chat turn.

The single place that decides which sinks a run goes to:
- test: nothing
- development: JSON files under `logs/<chat_id>/` (local eyeballing)
- production: nothing yet — the chat_runs insert is off in every environment
  until Stage 4 turns it back on (docs/deployment.md §4.2)
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


async def record_chat_run(
    request_context: RequestContext,
    # the one place the tree shape is required rather than incidental — the
    # dev-log below writes `record.flatten()`
    record: OperationResult,
    planner: TriageWorkflow | None = None,
    task_runner: TaskRunnerWorkflow | None = None,
    writer: GenerateRecommendationsExecutor | None = None,
    messages: list[APIMessage] | None = None,
) -> None:
    """Record a chat run. Never raises — recording must not break the chat."""
    if not request_context or record is None:
        user_message_id = (
            request_context.user_message.id if request_context else "unknown"
        )
        logger.warning(
            f"record_chat_run: missing request_context or record "
            f"for chat_id={user_message_id}"
        )
        return

    # Only development records anything right now. test stays hermetic, and
    # production has no sink until Stage 4 turns the chat_runs insert back on.
    # Files are never the production sink: Cloud Run's filesystem is in-memory,
    # so each one would cost instance RAM and vanish with the instance.
    if request_context.app_env != "development":
        return
    # NOTE: if something fails here
    # it'll timeout not error (why?)

    try:
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
        # it declined — without the guards the AttributeError lands in the
        # except below and the whole recording is logged as failed.
        if writer is not None:
            save_file(
                to_serializable(writer.record), file_name="writer", path=user_dir
            )

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

        # The chat_runs insert — off in every environment for now. Stage 4
        # (docs/deployment.md §4.2): uncomment and move above the development
        # gate, so production records too.
        # row = build_chat_run_row(
        #     session_id=request_context.session_id,
        #     user_chat_id=request_context.user_message.id,
        #     user_message=request_context.user_message.content,
        #     record=record,
        #     planner=planner.record if planner is not None else None,
        #     tasks=task_runner.record if task_runner is not None else None,
        #     writer=writer.record if writer is not None else None,
        # )
        # async with request_context.store(ChatRunStore) as store:
        #     await store.insert_run(row)
        # logger.info("📋 Recorded chat run %s", row["chat_id"])
    except Exception:
        logger.exception("Failed to record chat run")
