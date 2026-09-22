"""In-process API tests of POST /session/{id}/message — specifically the session
token budget, which is the only guard on that route that touches the database.

Same shape as test_chat_runs_api.py: the real FastAPI app over httpx's ASGI
transport, stores swapped out via dependency_overrides, so no database, no LLM
and no network. The orchestrator is faked too — what is under test is everything
that happens *before* a turn starts, so no turn is ever allowed to start.

Three overrides rather than one, because `ASGITransport` runs no lifespan: with
`app.state` empty, `get_orchestrator` and `get_request_context_factory` would
raise 503 while resolving, and every Depends resolves before the handler body —
so the guard would never be reached.
"""

from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sse_starlette.sse import AppStatus

from app.api.dependencies import (
    get_orchestrator,
    get_request_context_factory,
    get_session_store,
)
from app.common.request_context import RequestContext
from app.common.sse_stream import SSEStream
from app.main import app
from clients import OpenAIClient

pytestmark = pytest.mark.integration

URL = "/session/dev_abc123/message"


@pytest.fixture(autouse=True)
def reset_sse_shutdown_event():
    """sse_starlette keeps its shutdown signal on the class
    (`AppStatus.should_exit_event`), created lazily on the first SSE response and
    bound to that response's event loop. Each test gets a fresh loop, so without
    this the second test to stream anything dies on "bound to a different event
    loop" — and passes in isolation, which makes it look like flake."""
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


class FakeSessionStore:
    def __init__(self, remaining_tokens=50_000):
        self.remaining_tokens = remaining_tokens
        self.calls = []

    async def start_turn(self, session_id):
        self.calls.append(session_id)
        return self.remaining_tokens


class FakeOrchestrator:
    """Stands in for the real turn. It closes the stream immediately so the SSE
    response completes instead of hanging on an empty queue."""

    def __init__(self):
        self.runs = []

    async def run(self, request_context):
        self.runs.append(request_context.session_id)
        await request_context.sse_stream.close()


@pytest.fixture
def client_for():
    """Factory: pass the session store the route should use, get an AsyncClient
    against the real app with it injected. Overrides are cleared after the test
    so app state never leaks between tests."""
    orchestrator = FakeOrchestrator()

    async def _context_factory(session_id, user_message):
        """What get_request_context_factory returns, with every service faked —
        no turn runs, so none of them is touched."""
        return RequestContext(
            app_env="test",
            session_id=session_id,
            user_message=user_message,
            llm_client=MagicMock(spec=OpenAIClient),
            stores={},
            sse_stream=SSEStream(),
            session_factory=MagicMock(spec=async_sessionmaker),
        )

    def _make(store):
        app.dependency_overrides[get_session_store] = lambda: store
        app.dependency_overrides[get_orchestrator] = lambda: orchestrator
        app.dependency_overrides[get_request_context_factory] = (
            lambda: _context_factory
        )
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )

    yield _make
    app.dependency_overrides.clear()


class TestTheTokenBudgetGuard:
    async def test_an_exhausted_session_is_refused(self, client_for):
        store = FakeSessionStore(remaining_tokens=0)

        async with client_for(store) as client:
            resp = await client.post(URL, json={"message": "Find me a book"})

        assert resp.status_code == 429

    async def test_an_overspent_session_is_refused(self, client_for):
        """The balance goes negative by design — a turn is charged after it runs,
        so the last turn of a session overshoots."""
        store = FakeSessionStore(remaining_tokens=-3_000)

        async with client_for(store) as client:
            resp = await client.post(URL, json={"message": "Find me a book"})

        assert resp.status_code == 429

    async def test_a_session_with_budget_left_is_served(self, client_for):
        store = FakeSessionStore(remaining_tokens=1)

        async with client_for(store) as client:
            resp = await client.post(URL, json={"message": "Find me a book"})

        assert resp.status_code == 200

    async def test_the_route_looks_up_the_session_from_the_path(self, client_for):
        """One lookup, which is also what creates the row on a first message."""
        store = FakeSessionStore()

        async with client_for(store) as client:
            await client.post(URL, json={"message": "Find me a book"})

        assert store.calls == ["dev_abc123"]


class TestGuardOrder:
    """The budget check is last of the three, so a request that was never going
    to run costs no round trip and mints no session row."""

    async def test_a_blank_message_never_reaches_the_database(self, client_for):
        store = FakeSessionStore()

        async with client_for(store) as client:
            resp = await client.post(URL, json={"message": "   "})

        assert resp.status_code == 400
        assert store.calls == []

    async def test_an_oversized_message_never_reaches_the_database(self, client_for):
        store = FakeSessionStore()

        async with client_for(store) as client:
            resp = await client.post(URL, json={"message": "x" * 2001})

        assert resp.status_code == 400
        assert store.calls == []
