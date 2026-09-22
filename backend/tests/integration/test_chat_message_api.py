"""In-process API tests of POST /session/{id}/message — specifically what the
route does with the session token budget, which is the only thing on it that
touches the database.

The route reads the balance and hands it to the turn; it does not judge it. The
refusal lives in `Orchestrator` (tests/unit/app/orchestration/test_orchestrator.py),
so what is pinned here is the round trip: that it happens once, on the session in
the path, after the two 400s and not before.

Same shape as test_chat_runs_api.py: the real FastAPI app over httpx's ASGI
transport, stores swapped out via dependency_overrides, so no database, no LLM
and no network. The orchestrator is faked too — what is under test is everything
that happens *before* a turn starts, so no turn is ever allowed to start.

Three overrides rather than one, because `ASGITransport` runs no lifespan: with
`app.state` empty, `get_orchestrator` and `get_request_context_factory` would
raise 503 while resolving, and every Depends resolves before the handler body —
so the read would never be reached.
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
    response completes instead of hanging on an empty queue, and keeps the
    context it was handed so a test can read what the route put on it."""

    def __init__(self):
        self.contexts = []

    async def run(self, request_context):
        self.contexts.append(request_context)
        await request_context.sse_stream.close()


@pytest.fixture
def client_for():
    """Factory: pass the session store the route should use, get an AsyncClient
    against the real app with it injected, plus the orchestrator that will be
    handed the turn. Overrides are cleared after the test so app state never
    leaks between tests."""
    orchestrator = FakeOrchestrator()

    async def _context_factory(session_id, user_message, remaining_tokens):
        """What get_request_context_factory returns, with every service faked —
        no turn runs, so none of them is touched."""
        return RequestContext(
            app_env="test",
            session_id=session_id,
            remaining_tokens=remaining_tokens,
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
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        return client, orchestrator

    yield _make
    app.dependency_overrides.clear()


class TestTheBudgetRoundTrip:
    async def test_the_route_looks_up_the_session_from_the_path(self, client_for):
        """One lookup, which is also what creates the row on a first message."""
        store = FakeSessionStore()
        client, _ = client_for(store)

        async with client:
            await client.post(URL, json={"message": "Find me a book"})

        assert store.calls == ["dev_abc123"]

    async def test_the_balance_is_handed_to_the_turn(self, client_for):
        """The orchestrator reads it off the context — it cannot look it up
        itself, because it runs after this request's database session is gone."""
        client, orchestrator = client_for(FakeSessionStore(remaining_tokens=1_234))

        async with client:
            await client.post(URL, json={"message": "Find me a book"})

        assert [ctx.remaining_tokens for ctx in orchestrator.contexts] == [1_234]

    async def test_an_exhausted_session_still_gets_its_turn_started(self, client_for):
        """No 429 here by design: an empty balance is the orchestrator's to
        refuse, so that the user is told why over the stream."""
        client, orchestrator = client_for(FakeSessionStore(remaining_tokens=0))

        async with client:
            resp = await client.post(URL, json={"message": "Find me a book"})

        assert resp.status_code == 200
        assert [ctx.remaining_tokens for ctx in orchestrator.contexts] == [0]


class TestGuardOrder:
    """The budget read is last, so a request that was never going to run costs
    no round trip and mints no session row."""

    async def test_a_blank_message_never_reaches_the_database(self, client_for):
        store = FakeSessionStore()
        client, _ = client_for(store)

        async with client:
            resp = await client.post(URL, json={"message": "   "})

        assert resp.status_code == 400
        assert store.calls == []

    async def test_an_oversized_message_never_reaches_the_database(self, client_for):
        store = FakeSessionStore()
        client, _ = client_for(store)

        async with client:
            resp = await client.post(URL, json={"message": "x" * 2001})

        assert resp.status_code == 400
        assert store.calls == []
