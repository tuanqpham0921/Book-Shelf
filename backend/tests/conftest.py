"""Fixtures shared by every test suite.

`RequestContext` is now what a workflow is constructed with, so building one is
the setup step for anything that touches `AppWorkflow`. It lives here as a
*factory* rather than a plain fixture because callers need to vary one field at
a time (`app_env` for the run-recorder sinks, `user_message` for the planner)
while the rest stay boring.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import AppConfig
from clients.messages import UserMessage
from app.common.sse_stream import SSEStream
from app.common.request_context import RequestContext
from clients import OpenAIClient
from db.stores.book_store import BookStore


def fake_session_factory() -> MagicMock:
    """A session factory whose `.begin()` is a working async context manager.

    `RequestContext.store` enters `session_factory.begin()`, so a bare
    `MagicMock(spec=async_sessionmaker)` would raise on `__aenter__` rather
    than hand over a session. The session it yields is a plain mock — a test
    that cares what a store does with it stubs the store (see `book_store`).
    """
    factory = MagicMock(spec=async_sessionmaker)
    factory.begin.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    factory.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.fixture
def make_request_context():
    """Build a RequestContext, overriding any field by keyword."""

    def _make(**overrides) -> RequestContext:
        defaults = dict(
            app_env="test",
            session_id="sess_1",
            # a budget nothing has spent from; the guard that reads it only
            # bites in production anyway, so "test" makes it doubly irrelevant
            remaining_tokens=AppConfig.SESSION_TOKEN_BUDGET,
            user_message=UserMessage(content="Find me a book"),
            llm_client=MagicMock(spec=OpenAIClient),
            sse_stream=SSEStream(),
            session_factory=fake_session_factory(),
        )
        return RequestContext(**{**defaults, **overrides})

    return _make


@pytest.fixture
def request_context(make_request_context) -> RequestContext:
    return make_request_context()


@pytest.fixture
def book_store(monkeypatch) -> MagicMock:
    """The `BookStore` every `ctx.store(BookStore)` block yields.

    Patched on the class rather than the instance: `RequestContext` is a
    pydantic model, and `store` is a method on it, so every context a test
    builds picks this up. The real one opens a session off `session_factory`,
    which is a bare mock here.

    The assert is what is left of `require_store`'s isinstance check — without
    it nothing would catch a workflow asking for the wrong store.
    """
    store = MagicMock(spec=BookStore)

    @asynccontextmanager
    async def _store(self, store_cls):
        assert store_cls is BookStore, f"unexpected store requested: {store_cls}"
        yield store

    monkeypatch.setattr(RequestContext, "store", _store)
    return store
