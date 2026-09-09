from typing import Iterable
from collections import Counter

def count_values(values: Iterable[str | None]) -> dict[str, int]:
    """`{value: how many books had it}`, commonest first.

    Blanks are dropped rather than counted as a group: "3 books with no genre"
    is a fact about the catalog, not about the recommendation, and both
    readers of these summaries (the run log and the response generator) would
    be misled by it.
    """
    return dict(Counter(value for value in values if value).most_common())

def render_counts(counts: dict[str, int]) -> str:
    """`A (2), B` — a `count_values` result as one line of prose.

    The count only where it exceeds one, since "(1)" after every name reads as
    data to report rather than as context. Lives beside `count_values` rather
    than in a slice because it is that function's output shape being rendered,
    and every node writing a reply about a set of books renders it the same way.
    """
    return ", ".join(
        name if n == 1 else f"{name} ({n})" for name, n in counts.items()
    )

def truncate_str(text: str, limit: int, collapse: bool = True) -> str:
    """Cut at a word boundary so a clipped description doesn't end mid-word.

    `collapse` folds the internal whitespace of a single document onto one
    line; the assembled block passes False, because the blank lines between
    documents are what separate them.
    """
    text = " ".join(text.split()) if collapse else text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"