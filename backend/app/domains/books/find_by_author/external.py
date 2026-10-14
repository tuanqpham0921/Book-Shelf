"""Retrieve_by_Author's request, input and output schemas."""

from typing import Literal

from app.domains.base_request import BaseRequest
from app.domains.books.external import BookCandidateOutput
from app.domains.node_input import NodeInput

from .labels import FindAuthorNodeTypeEnum
from .tools import FindByAuthorArgs


class FindByAuthorRetrieval(BaseRequest):
    """Purpose: Retrieve the books written by one named author.

    Args:
        author: The single author whose books to retrieve.

    Returns: BookCandidateOutput — that author's catalog.

    depends_on: None — this node queries the database directly.

    Use when: one author is the subject of the search — "books by Ursula K. Le
    Guin", "what else has Brandon Sanderson written".

    Do not use: for taste-based suggestions. For books two or more authors
    wrote *together*, use Retrieve_by_CoAuthors instead. When a title and an
    author are named together ("Dune by Frank Herbert", "did Frank Herbert
    write Dune"), this node is right but not on its own — Retrieve_by_Title
    carries the title, this node carries the author, and Combine_Intersect
    ANDs them, so the pairing is checked against the data rather than taken on
    trust.

    Constraints: exactly one author per node — several authors mean one node
    per author ("books by Austen and by Coelho" → two nodes), because each node
    returns one author's catalog. This node searches on the author alone and
    takes no title, genre or metadata argument.

    Example queries:
        - "books by Ursula K. Le Guin"
        - "what else has Brandon Sanderson written"
        - "show me some Agatha Christie"
    """

    node_type: Literal[FindAuthorNodeTypeEnum.REQUEST] = FindAuthorNodeTypeEnum.REQUEST


class FindByAuthorInput(NodeInput):
    """The planner's instruction only — no field for upstream output.

    NOTE: empty on purpose. An upstream artifact routed here is logged as
    unclaimed by `build_input` instead of shaping the query.
    """


class FindByAuthorOutput(BookCandidateOutput):
    """How many books the author has here (`num_books`) and the query that
    reaches them.

    NOTE: a candidate, not an anchor — the node can't tell a 12-book
    bibliography from an 800-book one, so "books like Herbert's" describes the
    taste instead of anchoring on the shelf.
    """

    # None means the parse never happened (read by `finalize_result`)
    args: FindByAuthorArgs | None = None
