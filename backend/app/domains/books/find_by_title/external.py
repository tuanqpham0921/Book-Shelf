"""Retrieve_by_Title's request, input and output schemas."""

from typing import Literal

from app.domains.base_request import BaseRequest
from app.domains.books.external import BookAnchorOutput
from app.domains.node_input import NodeInput

from .labels import FindTitleNodeTypeEnum
from .tools import FindByTitleArgs


class FindByTitleRetrieval(BaseRequest):
    """Purpose: Retrieve the books whose titles most closely match the one given.

    Args:
        title: Book title to search for.

    Returns: BookAnchorOutput — the named book, and the query that reaches it.
    An anchor: the user pointed at this book, so a later step can search for
    others like it.

    depends_on: None — this node queries the database directly.

    Use when: a specific title is named — "find Dune", "do you have The Great
    Gatsby".

    Do not use: when the author is the actual subject of the search ("books by
    Frank Herbert"), or when no specific title is named.

    Constraints: one title per node — for multiple named titles, emit one node
    per title. This node searches on the title alone and takes no author
    argument. When a title and an author are named together ("Dune by Frank
    Herbert"), or the question is whether a given author wrote a given title
    ("did Frank Herbert write Dune"), the author is a second retrieval
    dimension: emit Retrieve_by_Author alongside this node and AND them with
    Combine_Intersect. That checks the pairing against the data instead of
    taking it on trust, and an empty intersection is the real answer to "did X
    write Y?".

    Example queries:
        - "find Dune"
        - "do you have The Great Gatsby"
    """

    node_type: Literal[FindTitleNodeTypeEnum.REQUEST] = FindTitleNodeTypeEnum.REQUEST


class FindByTitleInput(NodeInput):
    """The planner's instruction only — no field for upstream output.

    NOTE: empty on purpose. An upstream artifact routed here is logged as
    unclaimed by `build_input` instead of shaping the query.
    """


class FindByTitleOutput(BookAnchorOutput):
    """How many titles matched (`num_books`) and the query that reaches them.

    NOTE: an anchor because the user named the book, but a title can still
    match several editions — a consumer that folds anchors keeps its own cap.
    """

    # None means the parse never happened (read by `finalize_result`)
    args: FindByTitleArgs | None = None
