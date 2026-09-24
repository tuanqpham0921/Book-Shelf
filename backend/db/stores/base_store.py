import logging
from typing import TypeVar, Generic
from sqlalchemy.ext.asyncio import AsyncSession
from abc import ABC

from db.stores.deferred_query import compile_sql

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseStore(Generic[T], ABC):
    """Base store with common database operations."""

    def __init__(self, session: AsyncSession, model_class: type[T]):
        self.session = session
        self.model = model_class

    async def execute_statement(self, stmt):
        """Run one statement — the single execute path for every store.

        Store methods go through here rather than calling `self.session.execute`
        themselves, so that what should hold for every query lives in one place:
        today the compiled SQL at DEBUG.

        **No timeout here, and no commit anywhere in a store.** Both belong to
        whoever opened the session. `AppConfig.DATABASE_TIMEOUT` is enforced by
        the engine (`db/async_engine.py`) as Postgres' `statement_timeout`, so a
        long query is cancelled by the server and the connection comes back
        usable; the `asyncio.wait_for` that used to be here cancelled
        mid-execute instead, which left the connection in a state SQLAlchemy no
        longer knew and the server still running the query. The transaction
        boundary is the `session_factory.begin()` block a store is built inside
        (`RequestContext.store`) — a store that commits for itself closes that
        transaction early, and the next statement in the block raises.
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Executing statement: %s", compile_sql(stmt))
        return await self.session.execute(stmt)
