"""In-process API tests of POST /session/{id}/message — what the route does
before a turn starts, which since 2026-09-23 is validation and nothing else.

The session token budget used to be read here. It moved into the turn:
creating the row, reading the balance, judging it and charging it back are all
`Orchestrator`'s work now (tests/unit/app/orchestration/test_orchestrator.py
and test_token_budget.py). What is pinned here is what is left — the two 400s,
the context the route builds for the turn, and that the handler opens no
database session of its own.

Same shape as test_chat_runs_api.py: the real FastAPI app over httpx's ASGI
transport, its services swapped out via dependency_overrides, so no database,
no LLM and no network. The orchestrator is faked too — what is under test is
everything that happens *before* a turn starts, so no turn is ever allowed to
start.

Two overrides rather than none, because `ASGITransport` runs no lifespan: with
`app.state` empty, `get_orchestrator` and `get_request_context_factory` would
raise 503 while resolving, and every Depends resolves before the handler body.
"""

from unittest.mock import MagicMock

import httpx
import pytest
from sse_starlette.sse import AppStatus

from app.api.dependencies import (
    get_orchestrator,
    get_request_context_factory,
    get_sqlalchemy_session_factory,
)
from app.common.request_context import RequestContext
from app.common.sse_stream import SSEStream
from app.main import app
from clients import OpenAIClient
from tests.conftest import fake_session_factory

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
def client():
    """An AsyncClient against the real app, plus the orchestrator that will be
    handed the turn and the session factory the app would hand out. Overrides
    are cleared after the test so app state never leaks between tests."""
    orchestrator = FakeOrchestrator()
    factory = fake_session_factory()

    async def _context_factory(session_id, user_message):
        """What get_request_context_factory returns, with every service faked —
        no turn runs, so none of them is touched."""
        return RequestContext(
            app_env="test",
            session_id=session_id,
            user_message=user_message,
            llm_client=MagicMock(spec=OpenAIClient),
            sse_stream=SSEStream(),
            session_factory=factory,
        )

    app.dependency_overrides[get_sqlalchemy_session_factory] = lambda: factory
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_request_context_factory] = lambda: _context_factory

    yield (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ),
        orchestrator,
        factory,
    )
    app.dependency_overrides.clear()


class TestStartingTheTurn:
    async def test_the_turn_is_handed_the_session_from_the_path(self, client):
        http, orchestrator, _ = client

        async with http:
            resp = await http.post(URL, json={"message": "Find me a book"})

        assert resp.status_code == 200
        assert [ctx.session_id for ctx in orchestrator.contexts] == ["dev_abc123"]

    async def test_the_turn_is_handed_the_message(self, client):
        http, orchestrator, _ = client

        async with http:
            await http.post(URL, json={"message": "Find me a book"})

        assert [ctx.user_message.content for ctx in orchestrator.contexts] == [
            "Find me a book"
        ]

    async def test_the_route_opens_no_database_session(self, client):
        """The handler returns before the turn sends its first event, so a
        session opened here would be closed before anything used it. The turn
        opens its own, per round trip, through `RequestContext.store` — the
        factory is all the route passes on."""
        http, _, factory = client

        async with http:
            await http.post(URL, json={"message": "Find me a book"})

        factory.begin.assert_not_called()
        factory.assert_not_called()


class TestValidation:
    """Both guards are ahead of everything else, so a request that was never
    going to run starts no turn."""

    async def test_a_blank_message_is_refused(self, client):
        http, orchestrator, _ = client

        async with http:
            resp = await http.post(URL, json={"message": "   "})

        assert resp.status_code == 400
        assert orchestrator.contexts == []

    async def test_an_oversized_message_is_refused(self, client):
        http, orchestrator, _ = client

        async with http:
            resp = await http.post(URL, json={"message": "x" * 2001})

        assert resp.status_code == 400
        assert orchestrator.contexts == []
