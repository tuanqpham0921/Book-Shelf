"""The token budgets: `start_session_turn` and `read_site_spend` open a turn,
`debit_session_tokens` charges it. Its own module so the orchestrator imports
nothing from `db/`."""

import logging

from airglider import OperationResult, task
from app.common.request_context import RequestContext
from db.stores.session_store import SessionStore

logger = logging.getLogger(__name__)

# What the user is told, as the turn's one and only event. Says what to do next,
# and names no number: a balance is not something a reader can act on.
OUT_OF_TOKENS_MESSAGE = (
    "This session has used up its token budget. Start a new session by refreshing the page."
)

# The site-wide cap is not the user's to fix, so this one says to come back later.
SITE_OUT_OF_TOKENS_MESSAGE = (
    "The site has reached its daily usage limit. Please try again tomorrow."
)

# The site-wide cap applies only here: a local eval campaign is spend the owner
# chose, and would trip it against the dev database.
SITE_BUDGET_ENFORCED_IN = "production"


@task(description="Checks your session's token budget")
async def start_session_turn(request_context: RequestContext) -> int:
    """Open the turn, and report what its session has left to spend.

    One round trip does both: it creates the `sessions` row on a session's first
    message (`POST /session/new` persists nothing) and returns the balance
    `Orchestrator.run` judges.

    A `@task` so the round trip is its own step on the trace. `run` attaches it
    with `add_step`, since it builds the turn's root rather than being a unit
    of work itself.
    """
    async with request_context.store(SessionStore) as store:
        return await store.start_turn(request_context.session_id)


@task(description="Checks the site's daily spend")
async def read_site_spend(request_context: RequestContext) -> int:
    """What the whole site has spent in the last 24 hours.

    The session budget's backstop: a made-up session id starts with a full
    budget, so only a cap over every session bounds the bill. A `@task` for the
    same reason `start_session_turn` is — a round trip the turn waits on.
    """
    async with request_context.store(SessionStore) as store:
        return await store.spent_in_last_day()


async def debit_session_tokens(
    request_context: RequestContext, record: OperationResult
) -> None:
    """Subtract this turn's spend from its session. Never raises — a lost debit
    must not break a chat response.

    The spend is the whole turn, read off the orchestrator's root envelope,
    where airglider has summed every LLM call: triage, the planner, the tasks
    and the reply. The planner alone ships the whole tool catalog, so a
    per-task debit would undercount every turn.

    NOTE: its own database session through `ctx.store`, because this runs from
    `Orchestrator._finalize` inside `asyncio.shield` and can outlive the
    request; anything opened at the request boundary is closed by then.
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
            # No row means nothing created it — `start_session_turn` does
            # that, so this is a turn that bypassed it.
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
