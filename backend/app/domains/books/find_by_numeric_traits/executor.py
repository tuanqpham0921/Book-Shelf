"""Retrieve_by_Numeric_Traits' executor: parse measurable bounds (pages, year,
rating, rating count), count the books inside them, preview a few."""

from collections.abc import Callable
from typing import Any

from app.common.prompt_loader import load_prompt
from app.domains.books.base_workflow import BookWorkflow
from clients import OpenAIParserRequest
from clients.messages import AssistantMessage
from db.schema import BookMetadataFilter
from db.stores import numeric_traits_query

from .external import FindByNumericTraitsInput, FindByNumericTraitsOutput
from .tools import FindByNumericTraitsArgs

ARGS_PARSER_PROMPT_PATH = (
    "domains/books/find_by_numeric_traits/prompts/numeric_traits_args_parser.txt"
)

# the widest args schema in the app (a whole BookMetadataFilter), and
# reasoning_effort="low" spends from the same budget
MAX_COMPLETION_TOKENS = 2_000


class FindByNumericTraitsExecutor(BookWorkflow[FindByNumericTraitsOutput]):
    description = "Finds books by numbers like pages or rating"

    ui_loading_message = "getting books by traits..."

    async def run(self, node_input: FindByNumericTraitsInput) -> None:
        """Count the books inside the bounds and hand the query downstream, not the rows."""
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the planner's instruction into FindByNumericTraitsArgs
        parsed_args: FindByNumericTraitsArgs = await self.run_llm_args_parse(
            build_arg_parser_request(node_input.instruction)
        )
        self.result.args = parsed_args

        # NOTE: an all-None filter means this was the wrong node for the goal —
        # refused here so the error names the goal, not the SQL.
        if not describe_bounds(parsed_args.traits):
            raise ValueError(
                "No measurable trait was parsed: this goal has nothing to search "
                "on, and bounds are all this node can search by"
            )

        # 2. build the query and count — no rows fetched
        deferred = numeric_traits_query(parsed_args.traits)
        total = (await self.count_books(deferred)).unwrap()

        # 3. preview cards, only when something matched
        # NOTE: downstream nodes read `self.result.query` (every book inside the
        # bounds), never `preview`.
        if total:
            self.result.preview = (await self.fetch_books(deferred)).unwrap()
            await self.stream_books(self.result.preview)

        # 4. finalize — ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        # NOTE: ok means "the bounds were parsed and searched", not "something
        # matched" — bounds read from words are often tighter than the user
        # pictured, and a zero count is how they find out.
        ok = self.result.args is not None and self.result.query is not None
        return super().finalize_result(ok=ok)


def build_arg_parser_request(instruction: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `FindByNumericTraitsArgs` in from the planner's instruction.

    NOTE: its own prompt, not the shared fill-schema one — that prompt says "do
    not infer", which made "obscure" and "really long" parse to an empty filter.
    """
    if not instruction:
        raise ValueError("No instruction to parse arguments from")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=ARGS_PARSER_PROMPT_PATH),
        prompt_path=ARGS_PARSER_PROMPT_PATH,
        model="gpt-5-nano",
        # NOTE: `low`, not `minimal`, by measurement — minimal can't map a word
        # onto a number (2/8 on the calibration set vs 8/8) and sometimes puts a
        # bound on the wrong field. gpt-5-mini was no better than nano.
        reasoning_effort="low",
        # the planner wrote the instruction, so it goes in as an assistant turn
        # NOTE: single-turn only — earlier messages belong here once
        # conversations carry them.
        messages=[AssistantMessage(content=instruction)],
        tool_models=[FindByNumericTraitsArgs],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


def describe_bounds(filters: BookMetadataFilter) -> str:
    """The bounds as the user-facing line, e.g. `300 pages or more, published
    between 2020 and 2022, not for children`.

    Only what the parse set; an all-None filter returns "", which `run` refuses.
    Both ends are inclusive, hence "or more" / "or fewer".
    """
    parts = [
        range_phrase(
            filters.min_pages,
            filters.max_pages,
            "{low} pages or more",
            "{high} pages or fewer",
            "between {low} and {high} pages",
        ),
        range_phrase(
            filters.min_year,
            filters.max_year,
            "published in {low} or later",
            "published in {high} or earlier",
            "published between {low} and {high}",
        ),
        range_phrase(
            filters.min_rating,
            filters.max_rating,
            "rated {low} or higher",
            "rated {high} or lower",
            "rated between {low} and {high}",
            fmt=lambda value: f"{value:.1f}",
        ),
        range_phrase(
            filters.min_ratings_count,
            filters.max_ratings_count,
            "with at least {low} ratings",
            "with at most {high} ratings",
            "with between {low} and {high} ratings",
            fmt=lambda value: f"{value:,}",
        ),
    ]
    if filters.is_children is not None:
        parts.append("for children" if filters.is_children else "not for children")

    return ", ".join(part for part in parts if part)


def range_phrase(
    low: float | None,
    high: float | None,
    only_low: str,
    only_high: str,
    both: str,
    fmt: Callable[[Any], str] = str,
) -> str | None:
    """One min/max pair as words, or None when neither end is set."""
    if low is not None and high is not None:
        return both.format(low=fmt(low), high=fmt(high))
    if low is not None:
        return only_low.format(low=fmt(low))
    if high is not None:
        return only_high.format(high=fmt(high))
    return None
