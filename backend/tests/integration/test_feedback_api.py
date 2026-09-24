"""In-process API tests of PUT /session/{session_id}/message/{chat_id}/feedback —
the chat's thumbs up/down. Both stores are swapped out via dependency_overrides,
so no database is needed; see test_chat_runs_api.py for the template."""

import httpx
import pytest

from app.api.dependencies import get_chat_run_store, get_feedback_store
from app.main import app

pytestmark = pytest.mark.integration


class FakeChatRunStore:
    def __init__(self, runs):
        # {chat_id: session_id} for the recorded runs
        self.runs = runs

    async def belongs_to(self, chat_id, session_id):
        return self.runs.get(chat_id) == session_id


class FakeRow:
    def __init__(self, **fields):
        self.fields = fields

    def to_dict(self):
        return self.fields


class FakeFeedbackStore:
    def __init__(self):
        self.calls = []

    async def upsert_review(self, chat_id, session_id, liked, comments):
        self.calls.append(
            {"chat_id": chat_id, "session_id": session_id, "liked": liked, "comments": comments}
        )
        return FakeRow(chat_id=chat_id, session_id=session_id, liked=liked, comments=comments)


@pytest.fixture
def client_for():
    """Factory: pass both stores, get an AsyncClient against the real app with
    them injected. Overrides are cleared after the test."""

    def _make(chat_runs, feedback):
        app.dependency_overrides[get_chat_run_store] = lambda: chat_runs
        app.dependency_overrides[get_feedback_store] = lambda: feedback
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )

    yield _make
    app.dependency_overrides.clear()


class TestSubmitFeedback:
    async def test_own_run_is_upserted_without_comments(self, client_for):
        feedback = FakeFeedbackStore()

        async with client_for(FakeChatRunStore({"chat_1": "s_1"}), feedback) as client:
            resp = await client.put(
                "/session/s_1/message/chat_1/feedback", json={"liked": False}
            )

        assert resp.status_code == 200
        assert feedback.calls == [
            {"chat_id": "chat_1", "session_id": "s_1", "liked": False, "comments": []}
        ]

    async def test_another_sessions_run_is_not_found(self, client_for):
        feedback = FakeFeedbackStore()

        async with client_for(FakeChatRunStore({"chat_1": "s_1"}), feedback) as client:
            resp = await client.put(
                "/session/s_2/message/chat_1/feedback", json={"liked": True}
            )

        assert resp.status_code == 404
        assert feedback.calls == []

    async def test_unrecorded_run_is_not_found(self, client_for):
        feedback = FakeFeedbackStore()

        async with client_for(FakeChatRunStore({}), feedback) as client:
            resp = await client.put(
                "/session/s_1/message/chat_1/feedback", json={"liked": True}
            )

        assert resp.status_code == 404
        assert feedback.calls == []

    async def test_liked_is_required(self, client_for):
        feedback = FakeFeedbackStore()

        async with client_for(FakeChatRunStore({"chat_1": "s_1"}), feedback) as client:
            resp = await client.put("/session/s_1/message/chat_1/feedback", json={})

        assert resp.status_code == 422
        assert feedback.calls == []
