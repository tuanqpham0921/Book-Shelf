"""Retrieve_by_Lexical_Traits's request, input and output schemas."""

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
    """The planner's instruction only — no field for upstream output.

    NOTE: empty on purpose. An upstream artifact routed here is logged as
    unclaimed by `build_input` instead of shaping the query.
    """


class FindByLexicalTraitsOutput(BookCandidateOutput):
    """How many books' text matches the traits (`num_books`) and the query that
    reaches them.

    NOTE: a candidate, not an anchor — "mystery" matches hundreds of books, and
    folding their blurbs into one description describes nothing.
    """

    # None means the parse never happened (read by `finalize_result`)
    args: FindByLexicalTraitsArgs | None = None
