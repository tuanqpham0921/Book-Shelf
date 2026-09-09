"""The reply-writing call's pure half: this node's own work in, its brief out.

The books it chose are already on screen as cards, so the reply is not a list —
it is the one thing the cards cannot say: why this set, given what was asked
for. So the model gets two summaries rather than two lists of books: the input
half (`summarize_references`) and the output half (`summarize_shown`).

Descriptions and isbn13s stay out — one would re-summarize a visible book, the
other is not prose. `search_text` stays out too, and that exclusion is the
oldest decision in this file: it is a 100-300 word book description this node
wrote, and handing it to a model asked for a friendly reply gets it paraphrased
back at the user as if they had said it.

Two summarizers rather than one because the two halves are read off different
things — the anchor books the fold consumed, and the rows the browser was sent.
Neither is `SimilarBooksOutput.to_summary()`, which describes the *pool* (a
count and a cosine spread) for the record rather than the set on screen.

Unlike the analysis call next door this is not a tool call and this module
builds no request: the output *is* the reply, so it goes out through
`AppWorkflow.run_llm_reply`, which owns the streaming request and the half of
the prompt every reply in the app shares. What stays here is this node's half —
the summarizers above, and the guidance below. The step that runs it is
`FindSimilarBooksExecutor.response_to_user`, next door.
"""

from typing import Any, Iterable

from app.common.prompt_loader import load_prompt
from app.common.utils import count_values, render_counts
from app.domains.books.schemas import Book

RESPONSE_PROMPT_PATH = "domains/books/find_similar_books/prompts/response_prompt.txt"

# ~150 words of reply is ~200 tokens; the rest is headroom for the model's
# reasoning tokens, which count against this budget on gpt-5 models.
MAX_RESPONSE_TOKENS = 600


def summarize_references(
    references: Iterable[Book], asked_for: str = "", found: int = 0
) -> dict[str, Any]:
    """The input half: what was pointed at, and what the search was set to do.

    Only `title`, `authors` and `genre` are read off each book, which keeps
    descriptions and identifiers out of the reply.

    `asked_for` is the goal's instruction — the planner's restatement of the
    ask, which is the only account of it this node has. It stands in for the
    keywords an argument parser used to supply, and the prompt is told it is
    the system's own wording so it is used as direction rather than quoted back.

    `found` is how big the pool was. Paired with the number shown it is the
    difference between "here are ten" and "only these three exist" — and when
    it is 0 it is the whole story, which is a reply this node writes rather
    than an error it raises.

    Editions collapse to one entry per title before anything is counted —
    otherwise the title repeats ("books like Dune and Dune") and its author
    doubles, reading as a much stronger preference than was expressed.
    """
    by_title: dict[str, Book] = {}
    for book in references:
        by_title.setdefault(book.title, book)
    unique = list(by_title.values())

    return {
        "referenced_titles": [book.title for book in unique],
        "reference_authors": count_values(book.authors for book in unique),
        "reference_genres": count_values(book.genre for book in unique),
        "asked_for": asked_for,
        "candidates_found": found,
    }


def summarize_shown(books: list[Book]) -> dict[str, Any]:
    """The output half: the *shape* of the set on screen, not the books in it.

    Counts and ranges, because the reply characterizes the set rather than
    listing it — titles would only invite the model to enumerate what the cards
    already show.

    Read off the rows that were streamed rather than off the output, which
    carries the pool's size and cosine spread instead: the note goes with the
    cards, so it has to describe the cards.
    """
    pages = [book.num_pages for book in books if book.num_pages]
    return {
        "num_books": len(books),
        "authors": count_values(book.authors for book in books),
        "genres": count_values(book.genre for book in books),
        # None, not 0: a 0-0 range reads as "very short books" downstream
        "min_pages": min(pages) if pages else None,
        "max_pages": max(pages) if pages else None,
    }


def render_summaries(
    input_summary: dict[str, Any], output_summary: dict[str, Any]
) -> str:
    """The block the response prompt reads.

    Labelled lines rather than a dumped dict: the prompt asks for a reply that
    does not sound technical, and `{'genre_num': Counter(...)}` is a shape
    models happily imitate. Empty fields are dropped rather than printed as
    None, which reads as a value worth mentioning.
    """
    lines: list[str] = ["input:"]

    titles = input_summary.get("referenced_titles") or []
    if titles:
        lines.append(f"- referenced books: {', '.join(titles)}")

    authors = input_summary.get("reference_authors") or {}
    if authors:
        lines.append(f"- by: {render_counts(authors)}")

    genres = input_summary.get("reference_genres") or {}
    if genres:
        lines.append(f"- shelved as: {render_counts(genres)}")

    asked_for = input_summary.get("asked_for")
    if asked_for:
        lines.append(f"- asked for: {asked_for}")

    lines.append("")
    lines.append("output:")
    num_books = output_summary.get("num_books", 0)
    lines.append(f"- {num_books} books shown")

    # How big the pool was, whenever it is not simply the answer. Both
    # directions matter to the reply: a pool of 3 means "these are all there
    # are" rather than a shortlist, and a large one means the cards are the
    # closest of many.
    #
    # Always stated when nothing was shown, even at 0 — that is the one case
    # where the reply is *about* the pool, and an omitted line would leave
    # "found nothing" and "found some, showed none" indistinguishable.
    found = input_summary.get("candidates_found", 0)
    if found != num_books or not num_books:
        lines.append(f"- {found} came close enough to consider")

    out_authors = output_summary.get("authors") or {}
    if out_authors:
        lines.append(f"- by: {render_counts(out_authors)}")

    out_genres = output_summary.get("genres") or {}
    if out_genres:
        lines.append(f"- shelved as: {render_counts(out_genres)}")

    min_pages, max_pages = (
        output_summary.get("min_pages"),
        output_summary.get("max_pages"),
    )
    if min_pages and max_pages:
        lines.append(f"- length: {min_pages}-{max_pages} pages")

    return "\n".join(lines)


def response_guidance() -> str:
    """This node's half of the reply prompt — what the note is for, what the
    two summaries mean, what to do when the pool came back empty, and a worked
    example.

    The other half — the role, the trust boundary, the voice, and what
    `asked for` and `asked to say` mean — is `domains/prompts/reply.txt` and is
    shared with every other node that writes prose. `run_llm_reply` joins them,
    so nothing about tone or trust is restated here.
    """
    return load_prompt(prompt_path=RESPONSE_PROMPT_PATH)
