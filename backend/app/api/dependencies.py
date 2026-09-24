import logging
from typing import AsyncGenerator

import jwt
from fastapi import Request, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings, AppConfig
from db.stores.chat_run_store import ChatRunStore
from db.stores.feedback_store import FeedbackStore
from clients import OpenAIClient
from app.common.sse_stream import SSEStream
from app.orchestration.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def get_openai_client(request: Request) -> OpenAIClient:
    """Get the OpenAI client"""
    client = getattr(request.app.state, "openai_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="OpenAI client not available")
    return client


def get_orchestrator(request: Request) -> Orchestrator:
    """Get the orchestrator instance"""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    return orchestrator

def get_sqlalchemy_session_factory(request: Request):
    """Get SQLAlchemy session maker"""
    session_factory = getattr(request.app.state, "sqlalchemy_session_factory", None)
    if session_factory is None:
        raise HTTPException(
            status_code=503, detail="SQLAlchemy session factory not available"
        )
    return session_factory


async def get_sqlalchemy_session(
    session_factory=Depends(get_sqlalchemy_session_factory),
) -> AsyncGenerator[AsyncSession, None]:
    """One session and one transaction for the length of a request.

    `.begin()` rather than `()`: it commits on a clean exit, rolls back on an
    exception and closes either way, which is why no store commits for itself
    (see `BaseStore.execute_statement`). The commit therefore lands when the
    dependency is torn down, after the handler has returned its value — fine
    here because `expire_on_commit=False` keeps the returned rows readable.

    Only the plain HTTP routes use this, because only there is the request the
    unit of work. `/session/{id}/message` streams its response and outlives
    this scope entirely; it opens its own sessions through
    `RequestContext.store`.
    """
    async with session_factory.begin() as session:
        yield session


async def get_chat_run_store(
    session: AsyncSession = Depends(get_sqlalchemy_session),
) -> ChatRunStore:
    """Get ChatRunStore instance with injected session."""
    return ChatRunStore(session)


async def get_feedback_store(
    session: AsyncSession = Depends(get_sqlalchemy_session),
) -> FeedbackStore:
    """Get FeedbackStore instance with injected session."""
    return FeedbackStore(session)


def get_app_env(request: Request) -> str:
    """Get the app environment"""
    app_env = getattr(request.app.state, "app_env", None)
    if app_env is None:
        raise HTTPException(status_code=503, detail="App environment not available")
    return app_env


def get_sse_stream() -> SSEStream:
    return SSEStream()

async def get_request_context_factory(
    llm_client=Depends(get_openai_client),
    sse_stream=Depends(get_sse_stream),
    app_env: str = Depends(get_app_env),
    session_factory=Depends(get_sqlalchemy_session_factory),
):
    """Factory to create request contexts with runtime arguments."""
    from clients.messages import UserMessage
    from app.common.request_context import RequestContext

    async def create_context(session_id: str, user_message: UserMessage):
        # The factory, never a session or a store built on one: this runs in
        # the handler, and the turn it serves runs after the handler returns.
        # Each unit of work opens its own through `RequestContext.store`.
        return RequestContext(
            app_env=app_env,
            session_id=session_id,
            user_message=user_message,
            llm_client=llm_client,
            sse_stream=sse_stream,
            session_factory=session_factory,
        )

    return create_context


# `PyJWKClient` caches the key set, so it is built once rather than per request.
_app_check_keys = jwt.PyJWKClient(
    AppConfig.APP_CHECK_JWKS_URL, lifespan=AppConfig.APP_CHECK_JWKS_LIFESPAN
)


def require_app_check(
    x_firebase_appcheck: str | None = Header(default=None),
) -> None:
    """Refuse a request that doesn't carry a valid Firebase App Check token.

    The token proves the request came from the registered web app on
    tuanqpham0921.web.app, attested by reCAPTCHA. It is not authentication: a
    visitor can copy a live token out of their browser and replay it with curl
    until it expires. What it stops is the scripted caller who has never loaded
    the page.

    A plain `def`, so FastAPI runs it on the threadpool: fetching the key set
    is a blocking HTTP call, made once per cache lifespan.
    """
    project_number = settings.app.FIREBASE_PROJECT_NUMBER
    if project_number is None:
        return
    if not x_firebase_appcheck:
        raise HTTPException(status_code=401, detail="Missing App Check token")
    try:
        signing_key = _app_check_keys.get_signing_key_from_jwt(x_firebase_appcheck)
        jwt.decode(
            x_firebase_appcheck,
            signing_key.key,
            algorithms=["RS256"],
            audience=f"projects/{project_number}",
            issuer=f"https://firebaseappcheck.googleapis.com/{project_number}",
        )
    except jwt.PyJWTError as exc:
        logger.warning("Rejected App Check token: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid App Check token")
