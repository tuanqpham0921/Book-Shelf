"""Charge a finished turn to its session's token budget.

Its own module beside `run_recorder.py`, for the two reasons that one is: it
keeps `orchestration/orchestrator.py` free of any `db/` import, and it gives the
tests one name to patch.

The debit is the whole turn, not the tasks: `record` is the orchestrator's root
envelope, and airglider has already summed `token_usage` up the tree from every
LLM call through triage/planner, the task runner and the reply writer. The
planner alone ships the whole tool catalog, so a per-task debit would undercount
every turn.
"""

import logging

from airglider import OperationResult
from app.common.request_context import RequestContext
from db.stores.session_store import SessionStore

logger = logging.getLogger(__name__)


async def debit_session_tokens(
    request_context: RequestContext, record: OperationResult
) -> None:
    """Subtract this turn's spend from its session. Never raises — a lost debit
    must not break a chat response.

    Its own database session from `session_factory`, never a store off
    `ctx.stores`, for two independent reasons:

    - This runs from `Orchestrator._finalize`, inside `asyncio.shield`, so on the
      client-disconnect path it deliberately outlives the request. That is what
      `RequestContext.session_factory` is documented for.
    - The stores' `AsyncSession` is already out of scope regardless: FastAPI
      exits yield-dependencies when the *handler returns*, which for an SSE
      endpoint is before the first event is sent (fastapi 0.115 — the ordering
      changed in 0.106, so check this if that pin moves).

    And it would fail quietly rather than loudly: SQLAlchemy's `close()` is a
    reset, not a terminal close, so a write on that session would autobegin and
    commit on a connection nothing owns.
    """
    try:
        spent = record.token_usage.total
        async with request_context.session_factory() as session:
            remaining = await SessionStore(session).debit(
                request_context.session_id, spent
            )

        if remaining is None:
            # No row means nothing created it — the chat route does that on the
            # first message, so this is a turn that bypassed it.
            logger.warning(
                "No sessions row for %s: %s tokens not charged",
                request_context.session_id,
                spent,
            )
        else:
            logger.info(
                "💰 Charged %s tokens to %s, %s left",
                spent,
                request_context.session_id,
                remaining,
            )
    except Exception:
        logger.exception("Failed to debit session tokens")
