"""The books domain's registered nodes, one `SPEC` per line. Drop a `SPEC` to
hide its node from the planner."""

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
