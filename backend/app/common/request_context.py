"""`RequestContext` — the services one turn can reach.

Not what a node is working on; that half is `WorkflowInput`. They split on
lifetime: services are built once at the request boundary and are the same for
every node, while an input is assembled fresh at each dispatch.

The database is the exception to "built once", and deliberately so. What this
class carries is the *factory*, never a live session or a store built on one:
`/session/{id}/message` is an SSE endpoint, and FastAPI exits its
yield-dependencies when the handler returns — before the first event is sent,
and long before any node runs. A store parked here at request time would spend
the whole turn on a session that was already closed. `store()` below opens a
fresh one per use instead, which is also what lets `Orchestrator._finalize`
write after the request is over.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clients.messages import UserMessage, UnvalidatedUserMessage
from app.common.sse_stream import SSEStream
from db.stores.base_store import BaseStore

from clients import OpenAIClient

logger = logging.getLogger(__name__)

StoreT = TypeVar("StoreT", bound=BaseStore)


class RequestContext(BaseModel):
    """Everything a turn can reach, before anything decides what to do with it."""

    # OpenAIClient, SSEStream and the session factory are plain classes, not
    # pydantic models — without this the class raises at import time.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    app_env: str
    session_id: str

    # The turn's message — identity, not input: the wire `chat_id` and
    # `user_chat_id` in chat_runs both come from its id, and it outlives every
    # node in the plan while `NodeInput.instruction` changes at each dispatch.
    # Unvalidated as the route builds it; `Orchestrator.run` swaps in the
    # checked `UserMessage` before any workflow is built.
    user_message: UserMessage | UnvalidatedUserMessage

    llm_client: OpenAIClient = Field(..., exclude=True)
    sse_stream: SSEStream = Field(..., exclude=True)

    # The one database handle a turn gets. Everything that reads or writes goes
    # through `store()` below.
    session_factory: async_sessionmaker[AsyncSession] = Field(..., exclude=True)

    @asynccontextmanager
    async def store(self, store_cls: type[StoreT]) -> AsyncIterator[StoreT]:
        """One store on its own session and transaction, for the block's length.

        `.begin()`, not `()`: the transaction boundary is here, which is why no
        store commits for itself — one that did would close this transaction
        early and make the next statement in the block raise. SQLAlchemy runs
        the commit-and-close under `asyncio.shield`, so a block finishes its
        transaction even when the surrounding task is cancelled, which is what
        `Orchestrator._finalize` needs on the client-disconnect path.

        Opened per use rather than per request. Keep the block tight — around
        the round trip and nothing else — since it holds a pooled connection
        and an open transaction for as long as it is entered. Building a query
        needs no store at all (the builders in `db/stores/book_store.py` are
        module-level functions), so only the `await` belongs in here.
        """
        async with self.session_factory.begin() as session:
            yield store_cls(session)  # type: ignore[call-arg]  # concrete stores take (session)
