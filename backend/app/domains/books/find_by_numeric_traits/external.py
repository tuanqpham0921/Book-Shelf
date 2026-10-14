"""Retrieve_by_Numeric_Traits's request, input and output schemas."""

from typing import Literal

from app.domains.base_request import BaseRequest
from app.domains.books.external import BookCandidateOutput
from app.domains.node_input import NodeInput

from .labels import FindNumericTraitsNodeTypeEnum
from .tools import FindByNumericTraitsArgs


class FindByNumericTraitsRetrieval(BaseRequest):
    """Purpose: Retrieve books by their measurable traits — rating, number of ratings, page count, publication year.

    Args:
        traits: The measurable bounds to search on. Every bound is inclusive and
            independent — supply only the ones the request actually states.

    Returns: BookCandidateOutput — the books inside those bounds.

    depends_on: None — this node queries the database directly.

    Use when: the request states any measurable bound — as figures or in words,
    both belong here: "under 200 pages", "published after 2015", "show me some
    well rated books", "what do you have from the classical period", "your most
    popular books", "something really long". The wording is turned into bounds
    by this node's own parse, so a goal description in the user's own words is
    enough.

    That includes a bound riding alongside another subject. Emit this node for
    the bound, a retrieval node for the subject, and ONE Combine_Intersect
    depending on both:
        - "fantasy books over 400 pages"
            → Retrieve_by_Lexical_Traits + this node + Combine_Intersect
        - "Stephen King books over 400 pages"
            → Retrieve_by_Author + this node + Combine_Intersect
    The intersect goal is not optional there: two goals with no dependency
    between them are pooled (OR), so emitting this node beside the subject one
    and stopping would answer with MORE books rather than fewer — the opposite
    of the bound.

    Do not use: for a superlative that asks for an ordering this node cannot
    give. "The single longest book" is not a bound; ask for "very long books"
    instead. Nor for a subject of any kind — a genre, theme, author or title is
    someone else's retrieval, and this node only ever contributes the numbers.

    Constraints: at least one bound — a request with nothing measurable in it is
    not this node, and an empty filter is refused. Bounds are combined as AND,
    and an inverted range ("over 400 pages, under 200 pages") is rejected rather
    than answered with nothing. This node searches on measurable traits alone
    and takes no title, author, genre or theme. Superlatives become bounds
    ("highest rated" → rated 4.3 or higher), so results are ordered by rating
    rather than by the trait that was asked about.

    Example queries:
        - "Find books with fewer than 200 pages."          (this node alone)
        - "Show me some well rated books."                 (this node alone)
        - "What books do you have from the classical period?"
        - "Find me obscure books nobody has heard of."
        - "Find me fantasy books over 400 pages."          (+ subject + intersect)
    """

    node_type: Literal[FindNumericTraitsNodeTypeEnum.REQUEST] = (
        FindNumericTraitsNodeTypeEnum.REQUEST
    )


class FindByNumericTraitsInput(NodeInput):
    """The planner's instruction only — no field for upstream output.

    NOTE: empty on purpose. Narrowing another node's books by a bound is
    Combine_Intersect over both, never this node taking an input.
    """


class FindByNumericTraitsOutput(BookCandidateOutput):
    """How many books sit inside the bounds (`num_books`) and the query that
    reaches them.

    NOTE: a candidate, not an anchor — bounds describe a shelf, never a book
    ("well rated" is ~2,000 books with only a number in common).
    """

    # None means the parse never happened (read by `finalize_result`)
    args: FindByNumericTraitsArgs | None = None
