"""The session token budget: who may spend, and what a turn cost.

Its own module beside `run_recorder.py`, for the two reasons that one is: it
keeps `orchestration/orchestrator.py` free of any `db/` import, and it gives the
tests one name to patch.

**Both of the turn's own round trips live here**, at its two ends —
`start_session_turn` opens it, `debit_session_tokens` closes it — and each opens
its own database session through `ctx.store`, because the turn runs after the
HTTP handler that started it has already returned.

The debit is the whole turn, not the tasks: `record` is the orchestrator's root
envelope, and airglider has already summed `token_usage` up the tree from every
LLM call through triage/planner, the task runner and the reply writer. The
planner alone ships the whole tool catalog, so a per-task debit would undercount
every turn.
"""

import logging

from airglider import OperationResult, task
from app.common.request_context import RequestContext
from db.stores.session_store import SessionStore

logger = logging.getLogger(__name__)

# What the user is told, as the turn's one and only event. Says what to do next,
# and names no number: a balance is not something a reader can act on.
OUT_OF_TOKENS_MESSAGE = (
    "This session has used up its token budget. Start a new chat to keep going."
)

@task
async def start_session_turn(request_context: RequestContext) -> int:
    """Open the turn, and report what its session has left to spend.

    One round trip does both: it creates the `sessions` row on a session's first
    message (`POST /session/new` persists nothing) and returns the balance that
    `session_is_out_of_tokens` is about to judge.

    A `@task` because the turn waits on a database round trip, and its duration
    and any failure belong in the trace as their own step rather than folded
    into whatever ran next. `Orchestrator.run` attaches it with `add_step`:
    `run` builds the turn's root envelope rather than being a unit of work
    itself, so there is no enclosing scope for this to nest into.

    It ran in the chat route until 2026-09-23, which meant the handler held a
    database session on the turn's behalf and carried the number in on
    `RequestContext`. The turn is what is judged against the balance and what
    charges it back, so the turn is what waits for it.
    """
    async with request_context.store(SessionStore) as store:
        return await store.start_turn(request_context.session_id)


def session_is_out_of_tokens(remaining_tokens: int) -> bool:
    """Whether this turn should be refused before any work starts.

    `<= 0`, not "can this turn afford it": a turn is charged after it runs (see
    `debit_session_tokens`), so a session's last turn legitimately ends in the
    red and the only question here is whether anything was left.

    **Enforced in every environment since 2026-09-23.** It used to be production
    only, so `make dev` and the eval suites — which reuse one session for a whole
    run (evals/run_suites.py) — were never cut off partway. With the gate gone
    they are: at 10–20k tokens a turn, a 50,000 budget stops a suite after three
    or four cases, so a long suite needs a session per case or a larger
    `AppConfig.SESSION_TOKEN_BUDGET`.
    """
    return remaining_tokens <= 0


async def debit_session_tokens(
    request_context: RequestContext, record: OperationResult
) -> None:
    """Subtract this turn's spend from its session. Never raises — a lost debit
    must not break a chat response.

    Its own database session, like every other unit of work, and here that is
    load-bearing rather than merely uniform: this runs from
    `Orchestrator._finalize` inside `asyncio.shield`, so on the
    client-disconnect path it deliberately outlives the request. Anything built
    at the request boundary is long gone by then — FastAPI exits
    yield-dependencies when the *handler returns*, which for an SSE endpoint is
    before the first event is sent. `ctx.store()` is what makes that a
    non-question.
    """
    try:
        spent = record.token_usage.total
        if spent <= 0:
            # A turn refused for being out of tokens spends nothing, and
            # `start_turn` has already moved `last_updated` — so there is
            # nothing here to write.
            return

        async with request_context.store(SessionStore) as store:
            remaining = await store.debit(request_context.session_id, spent)

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
