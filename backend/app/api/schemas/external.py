from typing import Literal

from pydantic import BaseModel, Field, model_validator

from config import AppConfig

class SessionOut(BaseModel):
    id: str
    created_at: str

class ChatIn(BaseModel):
    message: str

FeedbackCategory = Literal["Content", "Recommendation", "Planner", "Time", "UI/UX", "Other"]

class ReviewCommentIn(BaseModel):
    """One observation inside a review."""

    title: FeedbackCategory | None = None
    message: str = Field(max_length=AppConfig.FEEDBACK_COMMENT_LENGTH)
    positive: bool = False

class FeedbackIn(BaseModel):
    """One reaction to a chat run, upserted whole per (chat_id, session_id):
    an overall like/dislike plus a comment list, so re-sending replaces the
    previous version. The chat sends this for its own replies, with both ids
    in the URL; `ReviewIn` is the same body carrying them itself."""

    liked: bool | None = None
    comments: list[ReviewCommentIn] = Field(default=[], max_length=AppConfig.FEEDBACK_MAX_COMMENTS)

    @model_validator(mode="after")
    def _has_substance(self):
        if self.liked is None and not self.comments:
            raise ValueError(
                "a review needs an overall reaction or at least one comment"
            )
        return self

class ReviewIn(FeedbackIn):
    """The /review page's review of a chat run. session_id is the reviewing
    session, which may differ from the session that produced the run."""

    chat_id: str
    session_id: str

class BookOut(BaseModel):
    """One book as the chat client receives it, in a `book_card` SSE event.

    The wire contract for a book, and the only place the frontend's field
    names are pinned on this side. `Book` (app/domains/books/schemas.py) is the
    internal model and carries every catalog column; this is the subset the UI
    renders — `BookCard`, `BookCardDetailed`, `BookCover` and `BookDetailModal`
    between them read exactly these fields and nothing else.

    Unlike the prompt-facing renderers, which pick their fields inline, the
    narrowing here is a *type* on purpose: serialization is the boundary, so a
    field added to `Book` reaches the browser unless something stops it, and
    this class is that something. `ratings_count` is the standing example — the
    bounds behind "obscure" and "most popular" are read off it and it is worth
    keeping in the run log, but no card renders it. (`similarity_score` used to
    be the example; it was deleted 2026-08-24, when the similarity node stopped
    carrying rows to attach it to.)

    Adding or renaming a field here is a frontend change: the components read
    these names straight off the event payload, so a rename breaks rendering
    silently, with no error raised on either side.
    """

    isbn13: str
    title: str
    authors: str | None = None
    categories: str | None = None
    published_year: int | None = None
    num_pages: int | None = None
    average_rating: float | None = None
    description: str | None = None
    thumbnail: str | None = None


class HealthStatus(BaseModel):
    """Health check response model."""

    orchestrator: bool = False
    sqlalchemy_engine: bool = False
    message: str = "Service status"