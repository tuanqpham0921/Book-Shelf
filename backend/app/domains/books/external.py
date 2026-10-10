"""The books domain's output shapes — what nodes return and what downstream
inputs declare."""

from typing import Any

from pydantic import ConfigDict, Field

from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.books.schemas import Book
from db.stores import DeferredBookQuery


class BookRetrievalOutput(NodeWorkflowOutput):
    """How many books matched (`num_books`) and the query that reaches them.

    `num_books == 0` is a real answer, not a failure. A node stamps `query`
    whether or not anything matched, so read `num_books` first.

    NOTE: `preview` is the few rows fetched for the cards, kept for the record
    and the reply. It is capped — no `NodeInput` should take rows from it;
    compose against `query` instead.

    Concrete on purpose: a node that accepts any book output declares this
    base, and `CombineIntersectOutput` returns it (an intersection may or may
    not be anchorable, so it counts as not).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # NOTE: every field needs a default — `Workflow.__init__` calls
    # `output_type()` with no arguments
    num_books: int = 0
    query_sql: str | None = None
    # excluded so the SQLAlchemy statement never reaches the `chat_runs` JSONB;
    # `query_sql` is the persisted copy
    query: DeferredBookQuery | None = Field(default=None, exclude=True)
    preview: list[Book] = Field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        # `has_query` rather than the SQL: `query_sql` is already on the record
        return {"num_books": self.num_books, "has_query": self.query is not None}


class BookAnchorOutput(BookRetrievalOutput):
    """Books the user *named* (`Retrieve_by_Title`) — can be folded into a
    description of what to look for next.

    NOTE: narrows intent, not size. A title can match every edition of a book,
    so a consumer that folds anchors keeps its own cap
    (`find_similar_books.MAX_ANCHOR_BOOKS`).
    """


class BookCandidateOutput(BookRetrievalOutput):
    """Books matching a *description* — author, lexical, numeric, and the
    similarity pool. A set, not a reference: nothing anchors on it.

    NOTE: the similarity pool's query carries a LIMIT. Intersecting it is safe
    and keeps its ranking; pooling it with `"or"` is lossy (see
    `DeferredBookQuery`).
    """
