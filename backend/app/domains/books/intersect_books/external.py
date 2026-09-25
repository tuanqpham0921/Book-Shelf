from typing import Literal

from pydantic import Field

from app.domains.base_request import BaseRequest
from app.domains.books.external import BookRetrievalOutput
from app.domains.node_input import NodeInput

from .labels import CombineIntersectNodeTypeEnum


class CombineIntersect(BaseRequest):
    """Purpose: Keep only the books that satisfy every one of several earlier searches at once.

    Args: none — this node reads nothing out of the goal description. What it
        intersects is decided entirely by what it depends on.

    Returns: BookRetrievalOutput — the books present in every depended-on
    result.

    depends_on: 2+ nodes producing books — BookRetrievalOutput, or either half
    of it (BookAnchorOutput, BookCandidateOutput). Any retrieval node, and
    Analyze_Similar_Books. **How each set was found does not matter here**: a
    title, a bibliography, a subject search, a page-count bound and a similarity
    pool are all just sets of books by the time they reach this node.

    Use when: the request states two or more conditions that must hold on the
    SAME book. Give each condition its own retrieval goal, then one goal here
    depending on all of them:
        - "fantasy books over 400 pages" → Lexical_Traits + Numeric_Traits
        - "did Jane Austen write thrillers?" → Author + Lexical_Traits
        - "horror by Stephen King over 500 pages" → Lexical_Traits + Author +
          Numeric_Traits, and ONE goal here over all three
        - "books like Dune that are under 300 pages" → Title →
          Analyze_Similar_Books, plus Numeric_Traits, and one goal here over
          those two
    This node is REQUIRED whenever conditions must combine: two goals with no
    dependency between them are pooled (OR), so leaving it out answers with MORE
    books rather than fewer — the opposite of what was asked.

    Do not use: when the request has one condition — there is nothing to
    intersect, and this node searches for nothing itself. Nor when the
    conditions are alternatives rather than requirements: "romance by Nora
    Roberts and mystery by Agatha Christie" is two answers, not one
    intersection, so it is two retrieval goals and no node here.

    Constraints: at least 2 dependencies; a goal with fewer is skipped. This
    node can only shrink what earlier goals found, never grow it. An empty
    result is a real answer — no book satisfied every condition at once.

    Example queries:
        - "Find me fantasy books over 400 pages."
        - "Did Jane Austen write thrillers?"
        - "What horror books has Stephen King written that are over 500 pages?"
    """

    node_type: Literal[CombineIntersectNodeTypeEnum.REQUEST] = (
        CombineIntersectNodeTypeEnum.REQUEST
    )


class CombineIntersectInput(NodeInput):
    """The results to AND together. Nothing else — this node parses no arguments.

    `min_length=2`, not 1, and the requirement is the node's contract: one input
    is not an intersection, and passing it through would report the upstream
    count as though something had narrowed it. `build_input` fills a `list[X]`
    with every match and a one-item list is still a *filled* field, so the
    length has to be rejected here — the runner then skips this one goal naming
    `anchors` rather than answering a wider question than was asked.

    Typed on the base, so any retrieval reaches it: an anchor
    (`Retrieve_by_Title`), a candidate (`Retrieve_by_Author`,
    `Retrieve_by_Lexical_Traits`, `Retrieve_by_Numeric_Traits`) or a similarity
    pool. That breadth is the point of the node — how a set was found stops
    mattering once it is a set.
    """

    anchors: list[BookRetrievalOutput] = Field(..., min_length=2)


class CombineIntersectOutput(BookRetrievalOutput):
    """`num_books` is what survived every condition, and `query` reaches exactly
    those books.

    Same shape as any retrieval — this node counts and hands on a query — but
    the query is the upstream ones ANDed together, so a downstream node composes
    against the intersection rather than re-applying anything. `num_books == 0`
    is a real answer: no book satisfied every condition at once, which is the
    moment to drop one rather than to fail the node.

    **On the base rather than either subclass, deliberately.** An intersection of
    two titles is anchor-shaped and an intersection of two subject searches is
    not, and the class cannot know which at definition time — so it lands on the
    base, which means "not anchorable" and is the safe half. The cost is that
    `Analyze_Similar_Books`, which requires `list[BookAnchorOutput]`, cannot
    depend on this node: "books like Harry Potter by Rowling" anchors on the
    title retrieval directly. See `BookRetrievalOutput`.

    No `args` field: this node has no parse to record. What it was asked is
    fully described by which goals it depended on.
    """
