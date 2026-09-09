"""The title node's flow — the worked example of a **single-call node**.

The 1-1 shape: one request schema, one executor, one LLM call (the arg parse),
then the counts-first opening move — nothing to interpret from upstream, so no
satellite modules. A slice that grows past this (several LLM calls, artifacts
to interpret) graduates to the layout `find_similar_books/` demonstrates; the
reading rule for both is in domains/README.md.

There is a second LLM call, but only on the turns the plan asks this node to
answer in words ("do you have Dune?"), and its pure half is two short functions
rather than a rendering layer — so it stayed in this file. A slice whose reply
needs real rendering puts it in a satellite the way `find_similar_books` does.
"""

from clients.messages import AssistantMessage
from app.common.prompt_loader import load_prompt
from app.common.utils import count_values, render_counts
from app.domains.books.base_workflow import BookWorkflow
from app.domains.books.schemas import Book
from clients import OpenAIParserRequest
from airglider import task

from .schemas import FindByTitleArgs
from .external import FindByTitleInput, FindByTitleOutput

from common.prompts import basic_fill_schema_prompt

REPLY_PROMPT_PATH = "domains/books/find_by_title/prompts/reply.txt"

# A confirmation is one or two sentences. Well under the 600 a note about ten
# books gets, and the cap matters for more than spend: `SSEStream.send_chars`
# paces output per character, and nothing else in the plan runs while it does.
MAX_REPLY_TOKENS = 150


def build_arg_parser_request(instruction: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `FindByTitleArgs` in from the planner's instruction."""
    if not instruction:
        raise ValueError("No instruction to parse arguments from")

    return OpenAIParserRequest(
        prompt=basic_fill_schema_prompt,
        model="gpt-5-nano",
        reasoning_effort="minimal",
        # the instruction is the planner's own work, not something the user typed.
        # NOTE: this should carry the previous messages too; clear and direct
        # instructions are enough while the conversation is single-turn.
        messages=[AssistantMessage(content=instruction)],
        tool_models=[FindByTitleArgs],
        max_completion_tokens=2000,
    )


def render_title_facts(
    title: str, asked_for: str, total: int, shown: list[Book]
) -> str:
    """The block the reply is written from — labelled lines, empties dropped.

    Both counts, always, and that is the point of the function. `shown` is a
    preview (`BookConstraints.default_limit`), so a title with forty editions
    puts three on screen: without `<m> of them on screen` beside `<n> in the
    catalogue`, a writer handed three rows describes three books as though they
    were all of them. Same hazard `candidates_found` guards next door.

    Authors are counted off the rows rather than listed per book — they are here
    to settle *which* book this is, not to enumerate editions.
    """
    lines = [f"- looked for: {title}"]
    if asked_for:
        lines.append(f"- asked for: {asked_for}")

    lines.append(f"- {total} in the catalogue under that title")
    if total:
        lines.append(f"- {len(shown)} of them on screen")

    authors = count_values(book.authors for book in shown)
    if authors:
        lines.append(f"- by: {render_counts(authors)}")

    return "\n".join(lines)


class FindByTitleExecutor(BookWorkflow[FindByTitleOutput]):
    ui_loading_message = "Getting Book By Title..."
    ui_section_title = "Found books by title"

    async def run(self, node_input: FindByTitleInput) -> None:
        """Count the matching titles and hand the query downstream — not the set.

        The count is what makes a "4,000 matched, narrow it down?" pause
        possible before any large result set is built; the query is what lets
        a later node compose this search with another one in SQL instead of
        intersecting two already-capped lists.
        """
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the goal text into this node's own schema
        instruction = node_input.instruction
        parsed_args: FindByTitleArgs = await self.run_llm_args_parse(
            build_arg_parser_request(instruction)
        )
        self.result.args = parsed_args

        book_title = parsed_args.title
        if not book_title:
            raise ValueError("No title was parsed")
        await self.sse_stream.send_ui_loading(f"finding book titled: {book_title}")

        # 2. build the deferred query and count — no rows fetched
        deferred = self.store.title_query(title=book_title)
        total = (await self.count_books(deferred)).unwrap()

        # A machine line, and only for the turns this node is working material.
        # When the plan asked it to answer in words the section is expanded, and
        # a count bullet sitting directly above prose that must not sound
        # technical undoes the reply — which says the same thing better.
        asked_to_say = node_input.generation_instruction
        if not asked_to_say:
            await self.sse_stream.send_chars(
                f"- Found {total} books titled: {book_title}"
            )

        # 3. Cards for the section, and nothing more: they are streamed and
        # let go, never assigned to the output. What travels downstream is the
        # query on `self.result`, which reaches the whole match rather than
        # these few rows. Nothing to fetch when nothing matched — but the rows
        # are kept now, because the reply below is written from them.
        shown: list[Book] = []
        if total:
            shown = (await self.fetch_books(deferred)).unwrap()
            await self.stream_books(shown)

        # 4. answer in words, when the plan asked for words. Deliberately
        # outside the `if total` above: "I don't have Dune" is the reply this
        # exists to write, and it is written from an empty set.
        if asked_to_say:
            await self.reply_to_user(
                book_title, node_input.instruction, total, shown, asked_to_say
            )

        # 5. last: ok is read off the output
        self.finalize_result()

    @task
    async def reply_to_user(
        self,
        title: str,
        asked_for: str,
        total: int,
        shown: list[Book],
        asked_to_say: str,
    ) -> None:
        """Answer the lookup in words, streamed as it is written.

        Only reached when the goal carried a `generation_instruction` — most
        title lookups are a step in someone else's chain and say nothing. The
        facts are what this node already has: the title it parsed, the count,
        and the rows it just streamed.

        A `@task`, and deliberately not unwrapped by `run`: the query is a real
        artifact the next goal composes against, so a writer that fails costs
        the turn its sentence, not its search. Same reasoning as
        `FindSimilarBooksExecutor.response_to_user`.
        """
        await self.sse_stream.send_ui_loading("checking the shelves...")
        message = await self.run_llm_reply(
            facts=render_title_facts(title, asked_for, total, shown),
            guidance=load_prompt(prompt_path=REPLY_PROMPT_PATH),
            asked_to_say=asked_to_say,
            max_tokens=MAX_REPLY_TOKENS,
        )
        self.add_details(
            f"Answered '{asked_to_say}' in "
            f"{len((message.content or '').split())} words"
        )

    def finalize_result(self):
        # ok means "the query got built", not "something matched" — zero
        # matches is an answer this node reports, not a failure it raises.
        ok = self.result.args is not None and self.result.query is not None
        return super().finalize_result(ok=ok)
