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
    """The goal text and nothing else.

    Retrieval is single-dimension and reads the title out of its own goal, so
    this node has no field for upstream output — it *structurally* cannot
    consume one, which is the contract the empty subclass states. An artifact
    routed here would be logged as unclaimed by `build_input` rather than
    silently shaping the query.
    """


class FindByTitleOutput(BookAnchorOutput):
    """`num_books` is how many titles matched and `query` is how to reach them.

    An **anchor** rather than a candidate set, and this is the node the
    distinction is drawn around: the user named a book, so the match can be
    folded into a description of what to look for next. That is what
    `BookAnchorOutput` claims, and it is a claim about the *ask* — a title
    search can still return six editions of the same book, so a consumer that
    folds them keeps its own cap.

    The node keeps no rows: it streams a few cards so the section has something
    in it, and what it hands downstream is the query. `num_books == 0` means the
    catalog has no such title — a real answer, and the moment to ask the user for
    a better one rather than to fail the node.

    `args` is declared here rather than on `NodeWorkflowOutput`, and typed as
    the schema this node actually parses: what "the arguments" *are* is a fact
    about one node, so the base has no useful annotation for it. None means the
    parse never happened, which is what `finalize_result` reads."""

    args: FindByTitleArgs | None = None
