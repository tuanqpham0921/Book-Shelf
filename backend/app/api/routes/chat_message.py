import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from app.api.schemas import ChatIn
from clients.messages import UserMessage
from app.orchestration.orchestrator import Orchestrator
from app.api.dependencies import (
    get_request_context_factory,
    get_orchestrator,
    get_sqlalchemy_session_factory,
)
from app.common.request_context import RequestContext
from db.stores.session_store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

async def generate_chat_response(
    orchestrator: Orchestrator,
    request_context: RequestContext,
) -> AsyncGenerator[Any, None]:
    # create_task cannot meaningfully fail here (calling an async def only
    # creates the coroutine; nothing in run() executes yet)
    orchestrator_task = asyncio.create_task(
            orchestrator.run(request_context=request_context)
        )

    try:
        async for event in request_context.sse_stream:
            yield event
            
        await orchestrator_task
    except Exception as e:
        # TODO: review this
        # realistically only the wait_for timeout: SSEStream.__anext__ and
        # Orchestrator.run both swallow their own exceptions.
        # yield the error directly — send_error() would enqueue an event
        # that this generator (the queue's only consumer) no longer reads        
        logger.exception("Orchestration stream failed", exc_info=e)
        yield ServerSentEvent(
            data=json.dumps({"type": "error", "data": "Orchestration error"})
        )
    finally:
        # covers every exit: normal end (no-op), CancelledError (client
        # disconnect), GeneratorExit (aclose) — the task never outlives
        # the stream
        await request_context.sse_stream.close()
        if not orchestrator_task.done():
            orchestrator_task.cancel()
            await asyncio.gather(orchestrator_task, return_exceptions=True)


@router.post("/session/{session_id}/message")
async def chat(
    session_id: str,
    chat_in: ChatIn, # NOTE: this can probably use UserMessage
    orchestrator: Orchestrator = Depends(get_orchestrator),
    request_context_factory: Callable = Depends(get_request_context_factory),
    session_factory: async_sessionmaker[AsyncSession] = Depends(
        get_sqlalchemy_session_factory
    ),
) -> EventSourceResponse:
    """Send a message to a session with SSE response."""
    if not chat_in.message or not chat_in.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    if len(chat_in.message) > 2000:
        raise HTTPException(
            status_code=400,
            detail=f"Message is too long. Maximum {2000} characters allowed.",
        )

    # The session's token budget — the only thing here that touches the database,
    # and last, so a blank or oversized message costs no round trip and mints no
    # session row. The same round trip creates the session on its first message
    # (POST /session/new stays stateless) and returns what it has left to spend.
    #
    # Read here but *judged* in the orchestrator, which is where a refusal can be
    # timed, recorded on the turn, and said to the user in the stream. Here it
    # could only be an HTTP 429, and the frontend renders any non-200 on this
    # route as "Oops something went wrong" — losing the one thing the user needs
    # to be told. It is read in the handler because the context is built from it
    # and the orchestrator has no way to look it up mid-stream.
    #
    # Its own session rather than the request-scoped dependency: the balance is
    # written back from `Orchestrator._finalize`, long after this handler has
    # returned, so nothing here should hold a session open on the turn's behalf.
    async with session_factory.begin() as session:
        remaining_tokens = await SessionStore(session).start_turn(session_id)

    request_context = await request_context_factory(
        session_id, UserMessage(content=chat_in.message), remaining_tokens
    )
    logger.info(f"🚀 Starting chat for session: {request_context.session_id}")

    return EventSourceResponse(
        generate_chat_response(
            orchestrator=orchestrator,
            request_context=request_context,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
        },
        # Safety net, not the primary close path: EventSourceResponse runs
        # this after its internal task group is fully done, which happens
        # whether that's from normal completion OR the disconnect path
        # (sse_starlette's task group swallows the cancellation it raises
        # internally). sse_stream.close() is idempotent (guards on
        # _closed/_finished), so this just guarantees the stream is never
        # left dangling even if Orchestrator.run's own cleanup got cut off.
        background=BackgroundTask(request_context.sse_stream.close),
    )
