import asyncio
import logging
from typing import TypeVar, Generic
from sqlalchemy.ext.asyncio import AsyncSession
from abc import ABC

from config import AppConfig
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
        themselves, so that the two things worth having on every query are in
        one place: the compiled SQL at DEBUG, and the timeout below.

        The timeout is asyncio-side rather than Postgres' `statement_timeout`
        because what needs bounding is the whole await, including the wait for a
        connection out of the pool — which the server cannot see, since nothing
        has reached it yet. The cost is that the session is not reusable
        afterwards: cancelling mid-execute leaves the connection in a state
        SQLAlchemy no longer knows, so a caller must let the session go rather
        than retry on it. Every caller does — a store lives for one request.
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Executing statement: %s", compile_sql(stmt))
        return await asyncio.wait_for(
            self.session.execute(stmt), timeout=AppConfig.DATABASE_TIMEOUT
        )
