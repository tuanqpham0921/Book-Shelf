from typing import Literal, Any

from pydantic import BaseModel, Field

from app.domains.base_request import BaseRequest
from app.domains.books.external import BookAnchorOutput, BookCandidateOutput
from app.domains.books.schemas import Book
from app.domains.node_input import NodeInput

from .labels import SimilarBooksNodeTypeEnum


class SimilarBooksSearch(BaseRequest):
    """Purpose: Find the books most similar in meaning to a book the user named.

    Args: none — this node reads nothing out of the goal description. What it
        searches for is built from the anchor books themselves.

    Returns: BookCandidateOutput — the books nearest the anchor, nearest first.
    A pool to choose from, not a final answer.

    depends_on: 1+ nodes returning BookAnchorOutput — Retrieve_by_Title, the
    node for a book the user named. A bibliography, a subject search or a
    numeric search returns BookCandidateOutput and CANNOT anchor this node:
    "mystery" matches hundreds of books, and averaging hundreds of blurbs
    describes nothing. A goal depending on one is skipped.

    Use when: the user names a book and wants more like it.
        - One book — "books like Dune": one Retrieve_by_Title, one goal here.
        - Several books BLENDED — "books like Dune and Neuromancer", "something
          between X and Y": ONE goal here, depending on every title retrieval.
          The anchors are folded into a single description, so the pool is what
          the named books have in common.
        - Several books SEPARATELY — "books like Dune or like Neuromancer",
          "recommendations for each of these": ONE GOAL PER BOOK, each depending
          on its own retrieval. Two goals, two pools. Pooling them into one goal
          would average two tastes into a description of neither.

    Do not use: when no book is named. Taste, mood and theme with nothing to
    anchor on ("something cozy and hopeful") are not this node's — it searches
    from the anchor books, not from the words in the goal. A subject word
    ("mysteries", "books about space") is Retrieve_by_Lexical_Traits.

    Constraints: every anchor a goal depends on is folded into one description
    and produces one pool — so AND is one goal with several depends_on, OR is
    several goals with one each. At most 5 anchor books in total across a
    goal's dependencies; more than that is refused rather than averaged.

    Example queries:
        - "recommend books like Dune"
        - "books like Dune and Neuromancer"        (one goal, two depends_on)
        - "books like Dune or like Neuromancer"    (two goals, one each)
    """

    node_type: Literal[SimilarBooksNodeTypeEnum.REQUEST] = (
        SimilarBooksNodeTypeEnum.REQUEST
    )


class SimilarBooksInput(NodeInput):
    """The books to be similar *to* — named ones only.

    `anchors` is required, and both halves of the requirement are the node's
    contract. **The type**: only a book the user *named* can be folded into a
    description of what to look for next, so `list[BookAnchorOutput]` structurally
    refuses a bibliography or a subject search — `build_input` fills by
    `isinstance`, and a plan that tries is skipped at dispatch naming this field
    rather than dying inside the node. **The `min_length`**: `build_input` fills a
    `list[X]` with every match and an empty list is still a *filled* field, so a
    bare `...` would never fire.

    There is no fallback to fall back to. A similarity search with nothing to be
    similar to is a different question — one no registered node answers today.

    No `documents` field: `AnalyzeBooksOutput` is a reserved name with no class,
    and a field can only select by type against a type that exists.
    """

    anchors: list[BookAnchorOutput] = Field(..., min_length=1)


class ScoreStats(BaseModel):
    """How close the pool actually sits, as cosine similarity.

    The pool is truncated to `CANDIDATE_POOL_SIZE`, so `num_books` reports that
    number far more often than it reports a match size — these are what say
    whether the pool found anything worth keeping. A `min` resting on
    `BookConstraints.MIN_SIMILARITY` means the floor never bound and the LIMIT
    chose the whole pool; a `min` well above it means the floor did the cutting
    and the pool is smaller than its ceiling.

    It is also the record `Book.similarity_score` used to keep. Per-book, that
    field only survived as far as the browser, where `BookOut` dropped it; the
    spread reaches `chat_runs` and is what "why these books" is answered from.
    """

    count: int
    min: float
    max: float
    avg: float


class SimilarBooksArgs(BaseModel):
    """What the search ran on. Every other slice's `args` is what it parsed out
    of the instruction; this node parses nothing from it and folds its anchors
    into a description instead — but that description is still the one input
    the search takes, so it lives where every section shows its arguments.
    Named for the `embed(search_text)` label in the pool's recorded SQL, which
    points at it."""

    search_text: str


class SimilarBooksOutput(BookCandidateOutput):
    """How many books sit nearest the anchor, and the query that reaches them.

    A **candidate** set, and on the candidate side for the same reason every
    other one is: these books match a *description* — the one this node
    synthesized — rather than a reference the user gave. So the pool can never
    be fed back in as an anchor to another similarity search, and a later node
    that re-ranks or picks from it declares `list[BookCandidateOutput]`.

    Shaped like every other retrieval — a count and a query, no rows — which it
    was not until 2026-08-24. `embedding_search_stmt` carries an ORDER BY and a
    LIMIT, and this node used to hand on 50 fetched rows because
    `DeferredBookQuery` forbids both by invariant. It now takes that invariant's
    one documented exception instead, because the rows cost more than the
    exception does: with a query, `Combine_Intersect` bounds the pool in SQL
    and `score` carries cosine order through the narrowing, so a bound on a
    similarity ask is expressible without this node parsing one.

    Counting, intersecting and materializing `query` are all safe — the count
    after an intersect means "of the 250 nearest, N also match". **Pooling it
    with `"or"` is not** — the LIMIT applies before the union, so it changes
    which books qualify, and `compose()` then drops the `score` that chose
    them. Nothing enforces that; see `DeferredBookQuery`. `score` is what
    describes this output, since `num_books` mostly reports the pool size.

    `references` and `args.search_text` are kept because "why these books" is
    only answerable against what was pointed at and what was embedded.
    `search_text` is the synthesized ideal-book description — what the embedding
    actually saw — not anything the user typed.
    """

    references: list[Book] = Field(default_factory=list)
    args: SimilarBooksArgs | None = None
    score: ScoreStats | None = Field(
        default=None,
        description="the pool's cosine spread — None when nothing cleared the floor",
    )

    def to_summary(self) -> dict[str, Any]:
        """The *shape* of the pool, not the books in it — none are carried now.

        A summary is read at a glance, and the two numbers worth glancing at
        are how big the pool is and how close it sits.
        """
        return {
            "num_books": self.num_books,
            "num_references": len(self.references),
            "score": self.score.model_dump() if self.score else None,
        }
