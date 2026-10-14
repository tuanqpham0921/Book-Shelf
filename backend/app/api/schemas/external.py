"""The API's wire models: request bodies (`ChatIn`, `FeedbackIn`, `ReviewIn`) and
responses (`SessionOut`, `HealthStatus`, and `BookOut` for each book card).
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from config import AppConfig

# Emoji blocks plus the characters that glue emoji together: variation
# selectors, the zero-width joiner, the keycap mark and the flag tag letters.
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs, emoticons, transport, flags, symbols
    "⌀-⏿"  # technical: ⌚ ⏰ ⏳
    "☀-➿"  # misc symbols and dingbats: ☀ ✨ ❤
    "⬀-⯿"  # arrows and stars: ⬆ ⭐
    "︎️‍⃣"
    "\U000E0020-\U000E007F"
    "]"
)


class SessionOut(BaseModel):
    id: str
    created_at: str


class ChatIn(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def strip_emoji(cls, message: str) -> str:
        """Emoji carry nothing the app can search on. A message that was only
        emoji comes out blank, and the route refuses it as empty."""
        return EMOJI_PATTERN.sub("", message)


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

    The wire contract for a book: `Book` (app/domains/books/schemas.py) carries
    every catalog column, and this is the subset the UI renders. It is a type on
    purpose, so a field added to `Book` does not reach the browser by default
    (`ratings_count` is in the run log, but no card shows it).

    NOTE: renaming a field here is a frontend change. The components read these
    names straight off the event, so a rename breaks the cards with no error.
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