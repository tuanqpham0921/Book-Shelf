"""The session token budget: who may spend, and what a turn cost.

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

# What the user is told, as the turn's one and only event. Says what to do next,
# and names no number: a balance is not something a reader can act on.
OUT_OF_TOKENS_MESSAGE = (
    "This session has used up its token budget. Start a new chat to keep going."
)

# The environment the budget is enforced in. Everywhere else the row is still
# created and still debited — the write path stays identical, which is what keeps
# it honest — but nothing is refused. That is deliberate: `make dev` and the eval
# suites reuse one session for a whole run (evals/run_suites.py), and at 10–20k
# tokens a turn a 50,000 budget would cut a suite off after three or four cases.
ENFORCED_IN = "production"


def session_is_out_of_tokens(request_context: RequestContext) -> bool:
    """Whether this turn should be refused before any work starts.

    `<= 0`, not "can this turn afford it": a turn is charged after it runs (see
    `debit_session_tokens`), so a session's last turn legitimately ends in the
    red and the only question here is whether anything was left.

    Reads the balance off the context rather than the database. The route put it
    there, in the one round trip that also created the row — and the orchestrator
    could not read it again anyway, since it runs after this request's database
    session has gone out of scope.
    """
    if request_context.app_env != ENFORCED_IN:
        return False
    return request_context.remaining_tokens <= 0


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
        if spent <= 0:
            # A turn refused for being out of tokens spends nothing, and
            # `start_turn` has already moved `last_updated` — so there is
            # nothing here to write.
            return

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
