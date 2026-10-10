"""The books domain's registered nodes, one `SPEC` per line.

`Registry` (app/registry.py) answers every lookup from these. To hide a node
from the planner without deleting it, drop its `SPEC` here.
"""

from app.domains.books import (
    find_by_author,
    find_by_lexical_traits,
    find_by_numeric_traits,
    find_by_title,
    find_similar_books,
    intersect_books,
)
from app.domains.node_spec import NodeSpec

BOOK_SPECS: tuple[NodeSpec, ...] = (
    find_by_title.SPEC,
    find_by_author.SPEC,
    find_by_lexical_traits.SPEC,
    find_by_numeric_traits.SPEC,
    find_similar_books.SPEC,
    intersect_books.SPEC,
)
