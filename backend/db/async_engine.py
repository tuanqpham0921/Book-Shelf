from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from config import AppConfig
from config.settings import SQLAlchemySettings
import logging

logger = logging.getLogger(__name__)


def get_session_factory(engine: AsyncEngine):
    """Get the session factory for the SQLAlchemy engine."""
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Keep objects usable after commit
    )

    logger.info("Session factory created")
    return session_factory


def get_async_engine(sqlalchemy_settings: SQLAlchemySettings) -> AsyncEngine:
    """Build the async engine"""

    engine = create_async_engine(
        sqlalchemy_settings.sqlalchemy_url,
        pool_size=sqlalchemy_settings.MIN_CONNECTIONS,
        max_overflow=sqlalchemy_settings.MAX_CONNECTIONS
        - sqlalchemy_settings.MIN_CONNECTIONS,
        # Validate connections before use — Neon suspends an idle compute, and
        # this drops a connection that died with it instead of failing a request
        pool_pre_ping=True,
        pool_recycle=1800,  # Recycle connections every 30 minutes
        # Every layer of AppConfig.DATABASE_TIMEOUT. Here rather than around
        # the await in BaseStore, because a query cancelled from the asyncio
        # side leaves the connection in a state SQLAlchemy no longer knows,
        # while the server cancelling its own query does not.
        pool_timeout=AppConfig.DATABASE_TIMEOUT,  # waiting for a connection
        connect_args={
            # Postgres cancels the query itself and the connection stays
            # usable; it surfaces as a DBAPIError with sqlstate 57014.
            # Startup parameters, so this needs Neon's *direct* host — the
            # `-pooler` one would have PgBouncer reject them.
            "server_settings": {
                "statement_timeout": str(int(AppConfig.DATABASE_TIMEOUT * 1000)),
            },
            # asyncpg's client-side backstop, deliberately above the server's
            # own cancel so that cancel wins whenever the server can hear it.
            # This is what covers a connection that never reaches the server;
            # it surfaces as a bare asyncio TimeoutError.
            "command_timeout": AppConfig.DATABASE_TIMEOUT + 2,
            # Opening the connection, which `command_timeout` does not cover —
            # it bounds commands, and there is no connection to run one on yet.
            # Without this a black-holed TCP connect waits out asyncpg's own
            # default of 60s, which is longer than anything else here and is
            # what `pool_pre_ping` falls back to when it drops a dead one.
            "timeout": AppConfig.DATABASE_TIMEOUT,
        },
        # echo=settings.debug, # Log SQL queries in debug mode
    )

    logger.info("Async engine created")
    return engine


async def close_async_engine(_async_engine: AsyncEngine):
    """Close the async engine."""
    await _async_engine.dispose()
    logger.info("SQLAlchemy engine disposed")


async def check_connection(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """Check if the database connection is established.

    Args:
        session: An async session.
    """
    from sqlalchemy import text

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
    return result.scalar() == 1
