"""The writing call's pure half: `render_report` turns the turn's task results
into the one block the writer reads, `build_recommendations_request` wraps it,
and `books_by_handle` resolves the reply's refs back to books.

Each goal is one section: a header (its instruction), an `<info>` block (how
it ended and how it was done), and a `<books>` block (the preview it kept) or,
for project facts, a `<project>` block. Two lines are held:

- **No identifiers in the books.** A model that sees an isbn13 will eventually
  print one, so each book carries a handle instead (`1.2`: section 1, book 2),
  which the reply's `refs` name it by.
- **Internals are grounding, not vocabulary.** `<info>` carries the search
  arguments, cost and SQL because they say exactly what was searched for; the
  prompt says to read them and never repeat them. NOTE: a known leak —
  `compile_sql` inlines literals, so a similarity search's SQL carries the
  anchor ISBNs. SQL renders last, so the info cap usually cuts it, and the
  prompt's no-identifiers rule covers the rest.

Each section is capped, not the report: truncating the whole block would cut
the end, which is where failures render. A plan is bounded by
`MAX_SYSTEM_GOALS`, so the report needs no cap of its own.
"""

import json

from app.common.prompt_loader import load_prompt
from app.common.utils import truncate_str
from app.domains.base_workflow import FailedGoalOutput, NodeWorkflowOutput
from app.domains.books.external import BookRetrievalOutput
from app.domains.books.find_similar_books import SimilarBooksOutput
from app.domains.books.schemas import Book
from app.domains.project.find_project_info import ProjectInfoOutput
from app.orchestration.task_runner import TaskResult
from airglider import remove_empty_values
from clients import OpenAIParserRequest
from clients.messages import AssistantMessage, UserMessage

from .external import GenerationResult

PROMPT_PATH = "orchestration/write_reply/prompts/reply.txt"

# A section's two caps, in characters (~4 per token). The info block is
# grounding, so it is the one allowed to lose its tail; a book entry is sized so
# a catalog-average description (~500 chars) survives whole.
MAX_INFO_CHARS = 400
MAX_BOOK_CHARS = 600

# The longest output in the app: prose plus sources for every goal in the plan,
# so it scales with MAX_SYSTEM_GOALS rather than with one schema.
MAX_COMPLETION_TOKENS = 4_000

# What an entry with no goal instruction is headed by — an output that never
# travelled through the runner, which no registered plan produces today.
FALLBACK_HEADER = "part of the search"

# what the evidence is headed by
FINDINGS_HEADER = "What I found:"


def render_report(results: list[TaskResult]) -> str:
    """Everything the plan produced as one block, a section per result, in the
    order given. All of it is evidence: no line in it is an instruction."""
    blocks = [FINDINGS_HEADER]
    blocks += [render_section(i, result) for i, result in enumerate(results, start=1)]
    return "\n\n".join(blocks)


def books_by_handle(results: list[TaskResult]) -> dict[str, Book]:
    """Every book `render_report` listed, keyed by the handle it printed —
    what a `SourceBlock`'s refs resolve against.

    Same list, same numbering: pass it exactly what the report was rendered
    from, and a handle the model copies is always the book it read.
    """
    return {
        _handle(section, position): book
        for section, result in enumerate(results, start=1)
        for position, book in enumerate(_preview(result), start=1)
    }


def build_recommendations_request(
    rendered: str, user_message: str
) -> OpenAIParserRequest:
    """Ask the LLM to write the reply as `GenerationResult` blocks.

    Structured rather than streamed: each text is followed by the cards it
    talks about, and the executor sends them in that order once the reply is
    whole. The tool description is left off — `tool_choice` already pins the
    one tool, and the prompt carries the format.

    Two messages, and the split is the trust boundary. The report is an
    `AssistantMessage`, prior system work the prompt says to read as data. The
    user's own text is the `UserMessage`: the question being answered and the
    only direction the call carries. It goes last so the model replies to it
    rather than continuing its own turn.

    A cheap model on purpose: this call writes prose from facts it was handed.
    """
    if not rendered.strip():
        raise ValueError("Nothing to write recommendations from")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=PROMPT_PATH),
        prompt_path=PROMPT_PATH,
        model="gpt-5-mini",
        reasoning_effort="low",
        messages=[
            AssistantMessage(content=rendered),
            UserMessage(content=user_message),
        ],
        tool_models=[GenerationResult],
        include_tool_description=False,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


def render_section(index: int, result: TaskResult) -> str:
    """One goal: what was asked, how it went, and the books or project facts
    it kept.

    No `<books>` block when there are none — nothing matched, or the goal
    failed — rather than an empty one the model has to interpret.
    """
    output = result.output
    parts = [
        f"[{index}] {output.goal_instruction or FALLBACK_HEADER}",
        f"<info>\n{render_info(result)}\n</info>",
    ]

    books = _preview(result)
    if books:
        rendered = "\n".join(
            render_book(_handle(index, position), book)
            for position, book in enumerate(books, start=1)
        )
        parts.append(f"<books>\n{rendered}\n</books>")

    if isinstance(output, ProjectInfoOutput) and output.answer:
        cited = f"\nSources: {', '.join(output.sources)}" if output.sources else ""
        parts.append(f"<project>\n{output.answer}{cited}\n</project>")

    return "\n".join(parts)


def render_info(result: TaskResult) -> str:
    """How one part of the work went and how it was done, at most
    `MAX_INFO_CHARS`: the outcome, the error, the similarity lines, the
    arguments, what it cost, and the SQL — in that order, so the cap cuts the
    SQL first and never the error.

    The similarity pool gets two extra lines. Its books match a description the
    *system* wrote from the books the user named, and a reply explaining "why
    these fit" is only honest against that: what it was built from, and what
    was actually searched for. NOTE: the one typed read into a sibling slice —
    interpreting an upstream shape is the consumer's job (rule 6 in
    domains/README.md).

    Read off the fields rather than `output.to_summary()`: that is the trace's
    view, and changing it would change every `chat_runs` summary.
    """
    output = result.output
    lines = [render_outcome(output)]

    if result.error_message:
        lines.append(f"error: {result.error_message}")

    if isinstance(output, SimilarBooksOutput):
        if output.references:
            named = ", ".join(book.title for book in output.references)
            lines.append(f"built from the reader's reference books: {named}")
        if output.args:
            lines.append(f'searched for books matching: "{output.args.search_text}"')

    # `getattr`: every parsing slice types its own `args`, and no shared shape
    # declares the field. The pool's args are its search text, rendered above in
    # the wording the prompt names — a second copy would spend the info cap.
    args = getattr(output, "args", None)
    if args is not None and not isinstance(output, SimilarBooksOutput):
        parsed = remove_empty_values(args.model_dump(mode="json"))
        if parsed:
            lines.append(f"arguments: {json.dumps(parsed, ensure_ascii=False)}")

    if result.duration is not None:
        cost = f"took {result.duration}s"
        if result.total_tokens:
            cost += (
                f", {result.total_tokens} tokens "
                f"({result.input_tokens} in, {result.output_tokens} out)"
            )
        lines.append(cost)

    if isinstance(output, BookRetrievalOutput) and output.query_sql:
        lines.append(f"sql: {' '.join(output.query_sql.split())}")

    return truncate_str("\n".join(lines), MAX_INFO_CHARS, collapse=False)


def render_outcome(output: NodeWorkflowOutput) -> str:
    """How one part of the work ended — the first line of its info block.

    Kept apart because they mean different things to the reply: "found
    nothing" is an answer about the catalog, rendered as a sentence because a
    blank relays it to nobody; "could not be completed" is about the plan, with
    the runner's reason relayed verbatim — it is already prose, and the only
    place a two-hop cause is stated.
    """
    if isinstance(output, FailedGoalOutput):
        line = "could not be completed"
        if output.reason:
            line += f" — {output.reason}"
        return line

    # a finished project lookup always has an answer: an empty one fails its claim
    if isinstance(output, ProjectInfoOutput):
        return "found facts about BookShelf"

    num_books = output.num_books if isinstance(output, BookRetrievalOutput) else 0
    return f"found {num_books} book(s)" if num_books else "found nothing"


def render_book(handle: str, book: Book) -> str:
    """One book as the writer sees it, at most `MAX_BOOK_CHARS`, labelled with
    the handle the reply's `refs` point at it by.

    No isbn13 and no thumbnail: the first is an identifier the prose must never
    contain, the second only travels to the browser on the card. The cap is on
    the whole entry, so the description gets whatever room the fact line
    leaves.
    """
    facts = [book.authors or "author unknown"]
    if book.published_year:
        facts.append(str(book.published_year))
    if book.num_pages:
        facts.append(f"{book.num_pages} pages")
    if book.average_rating:
        facts.append(f"rated {book.average_rating}")

    line = f"- [{handle}] {book.title} — {', '.join(facts)}"
    # the newline, the two-space indent and `truncate_str`'s ellipsis
    room = MAX_BOOK_CHARS - len(line) - 4
    if book.description and room > 0:
        line += f"\n  {truncate_str(book.description, room)}"
    return line


def _preview(result: TaskResult) -> list[Book]:
    """The books one goal kept — what its section lists, and what its handles
    resolve to."""
    output = result.output
    return output.preview if isinstance(output, BookRetrievalOutput) else []


def _handle(section: int, position: int) -> str:
    """A book's label in the report, and what a `SourceBlock` names it by."""
    return f"{section}.{position}"
