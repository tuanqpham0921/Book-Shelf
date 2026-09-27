from typing import Literal

from app.domains.base_request import BaseRequest
from app.domains.books.external import BookCandidateOutput
from app.domains.node_input import NodeInput

from .labels import FindLexicalTraitsNodeTypeEnum
from .tools import FindByLexicalTraitsArgs


class FindByLexicalTraitsRetrieval(BaseRequest):
    """Purpose: Retrieve books by their lexical traits alone — the words the catalog's text actually contains, plus the shelves it files them under.

    Args:
        traits: The words to search the catalog's text for, and which shelves to
            keep. Keywords, fiction-ness and audience are ANDed together, so one
            node serves "non-fiction about artificial intelligence".

    Returns: BookCandidateOutput — how many books match, and the query that
    reaches them.

    depends_on: None — this node queries the database directly.

    Use when: a word IS the search. "fantasy books", "books about ninjas",
    "non-fiction about history", "children's books", "any good mysteries",
    "something set in space". This is a **lexical** search: it matches books
    whose title, shelf label or description literally contains these words. It is
    the node for anything that is neither a number nor an identifier — the
    counterpart of Retrieve_by_Numeric_Traits, which owns the measurable half of
    the same job.

    Do not use: for a known title (Retrieve_by_Title) or a named author
    (Retrieve_by_Author). Mood, tone and premise ("cozy", "hopeful",
    "slow-burn", "spooky") are not lexical traits — they describe what a book is
    *like*, and this node can only find words the catalog's text contains, so
    searching for a feel finds nothing. Keep the part of the request that is a
    real word in the text and leave the rest out: "cozy mysteries" is
    keywords=["mystery"]. A measurable bound riding alongside is likewise not
    this node's to apply — "fantasy books over 400 pages" searches the words here
    and leaves the page bound in the goal's description.

    Constraints: at least one of keywords, genre or audience — an empty search is
    refused rather than answered with the whole catalog. Keywords are ANDed, not
    ORed: every keyword must appear, so few high-signal words find more than many.
    Genre is exactly fiction or non-fiction, the only two the catalog
    distinguishes; every finer shelf word ("mystery", "history", "biography") is
    a keyword instead. One node covers one subject — two unrelated subjects
    ("mysteries and cookbooks") are two nodes.

    Example queries:
        - "Show me children's books."
        - "What non-fiction books about history do you have?"
        - "Find me books about artificial intelligence."
        - "Books about ninjas."
        - "Any good mysteries?"
    """

    node_type: Literal[FindLexicalTraitsNodeTypeEnum.REQUEST] = (
        FindLexicalTraitsNodeTypeEnum.REQUEST
    )


class FindByLexicalTraitsInput(NodeInput):
    """The goal text and nothing else.

    The traits are read out of this node's own goal, so it has no field for
    upstream output — it *structurally* cannot consume one, which is the contract
    the empty subclass states. That absence is what separates this node from
    Combine_Intersect, whose `anchors` is required: this node contributes a set,
    that one combines sets, and neither can be handed the other's input by
    accident.
    """


class FindByLexicalTraitsOutput(BookCandidateOutput):
    """`num_books` is how many books match the traits, `query` is how to reach them.

    A **candidate** set, and the clearest case for the split: "mystery" matches
    358 books, and folding 358 blurbs into one description of an ideal book
    describes nothing at all. A lexical ask is served by embedding the words
    themselves, not by anchoring on what those words happened to match.

    The node keeps no rows: it streams a few cards so the section has something
    in it, and what it hands downstream is the query. That query is the point of
    this node — it is what lets Combine_Intersect AND it together with an
    author's bibliography or a page-count bound.

    The count is the honest report of a *lexical* match: these are books whose
    text contains the words, not books an embedding judged similar. `num_books ==
    0` is a real answer and the moment to try a broader word, not a failure.

    `args` is declared here rather than on `NodeWorkflowOutput`, and typed as the
    schema this node actually parses. None means the parse never happened, which
    is what `finalize_result` reads.
    """

    args: FindByLexicalTraitsArgs | None = None
