import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import FeedbackIn, ReviewIn
from app.api.dependencies import get_chat_run_store, get_feedback_store
from db.stores.chat_run_store import ChatRunStore
from db.stores.feedback_store import FeedbackStore

logger = logging.getLogger(__name__)

# Two routers over the one feedback table, because only one of them is served
# in production (app/main.py): `router` is the chat's thumbs up/down on its own
# replies, `review_router` is the /review page's surface, which reads every
# session's reviews and has no admin gate yet (docs/deployment.md §4.1).
router = APIRouter(tags=["Feedback"])
review_router = APIRouter(tags=["Feedback"])


@router.put("/session/{session_id}/message/{chat_id}/feedback")
async def submit_feedback(
    session_id: str,
    chat_id: str,
    feedback: FeedbackIn,
    chat_runs: ChatRunStore = Depends(get_chat_run_store),
    store: FeedbackStore = Depends(get_feedback_store),
):
    """Like, dislike or comment on one of this session's own replies, replacing
    any earlier feedback from it whole. A run another session produced is a
    404, as is one whose turn has not been recorded yet — so a session can only
    rate what it asked, and each run holds at most one row from it."""
    if not await chat_runs.belongs_to(chat_id, session_id):
        raise HTTPException(status_code=404, detail="Chat run not found")
    row = await store.upsert_review(
        chat_id=chat_id,
        session_id=session_id,
        liked=feedback.liked,
        comments=[comment.model_dump() for comment in feedback.comments],
    )
    logger.info(
        "👍 Feedback recorded for chat run %s (liked=%s, %d comment(s))",
        chat_id,
        feedback.liked,
        len(feedback.comments),
    )
    return row.to_dict()


@review_router.put("/feedback/review")
async def submit_review(
    review: ReviewIn,
    store: FeedbackStore = Depends(get_feedback_store),
):
    """Submit (or replace) one reviewing session's review of a chat run:
    the overall like/dislike plus the full comments list. One row per
    (chat_id, session_id) — re-submitting from the same session replaces
    the previous version whole; a different session appends a new review."""
    row = await store.upsert_review(
        chat_id=review.chat_id,
        session_id=review.session_id,
        liked=review.liked,
        comments=[comment.model_dump() for comment in review.comments],
    )
    logger.info(
        "📝 Review recorded for chat run %s (%d comment(s))",
        review.chat_id,
        len(review.comments),
    )
    return row.to_dict()


@review_router.get("/feedback")
async def get_feedback(
    chat_id: str = Query(...),
    store: FeedbackStore = Depends(get_feedback_store),
):
    """Get all reviews of one chat run, oldest first."""
    rows = await store.get_by_chat_id(chat_id)
    return {"feedback": [row.to_dict() for row in rows]}
