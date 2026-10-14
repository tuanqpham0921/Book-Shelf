"""Retrieve_by_Lexical_Traits' executor: parse keywords, genre and audience, count
the books whose text matches, preview a few."""

from app.common.prompt_loader import load_prompt
from app.domains.books.base_workflow import BookWorkflow
from clients import OpenAIParserRequest
from clients.messages import AssistantMessage
from db.schema import AudienceEnum
from db.stores import lexical_query

from .external import FindByLexicalTraitsInput, FindByLexicalTraitsOutput
from .tools import FindByLexicalTraitsArgs

ARGS_PARSER_PROMPT_PATH = (
    "domains/books/find_by_lexical_traits/prompts/lexical_traits_args_parser.txt"
)

# more room than the single-field parsers: keywords is a list, and
# reasoning_effort="low" spends from the same budget
MAX_COMPLETION_TOKENS = 2_000


class FindByLexicalTraitsExecutor(BookWorkflow[FindByLexicalTraitsOutput]):
    description = "Finds books by subject"

    ui_loading_message = "searching the catalog's text..."

    async def run(self, node_input: FindByLexicalTraitsInput) -> None:
        """Count the books matching the lexical traits and hand the query downstream."""
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the planner's instruction into FindByLexicalTraitsArgs
        parsed_args: FindByLexicalTraitsArgs = await self.run_llm_args_parse(
            build_arg_parser_request(node_input.instruction)
        )
        self.result.args = parsed_args

        # NOTE: an empty parse means this was the wrong node for the goal —
        # refused here so the error names the goal, not the SQL.
        if not describe_lexical_traits(parsed_args):
            raise ValueError(
                "No lexical traits were parsed: this goal names no keyword, "
                "genre or audience, and those are all this node can search by"
            )

        # 2. build the query and count — no rows fetched
        deferred = lexical_query(
            keywords=parsed_args.keywords,
            genre=parsed_args.genre,
            audience=parsed_args.audience,
        )
        total = (await self.count_books(deferred)).unwrap()

        # 3. preview cards, only when something matched
        # NOTE: downstream nodes read `self.result.query`, never `preview`.
        if total:
            self.result.preview = (await self.fetch_books(deferred)).unwrap()
            await self.stream_books(self.result.preview)

        # 4. finalize — ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        # NOTE: ok means "the traits were parsed and searched", not "something
        # matched".
        ok = self.result.args is not None and self.result.query is not None
        return super().finalize_result(ok=ok)


def build_arg_parser_request(instruction: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `FindByLexicalTraitsArgs` in from the planner's instruction.

    NOTE: its own prompt, not the shared fill-schema one — that prompt says "do
    not infer", but "children's books" has to become `audience: children`.
    """
    if not instruction:
        raise ValueError("No instruction to parse arguments from")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=ARGS_PARSER_PROMPT_PATH),
        prompt_path=ARGS_PARSER_PROMPT_PATH,
        model="gpt-5-nano",
        reasoning_effort="low",
        messages=[AssistantMessage(content=instruction)],
        tool_models=[FindByLexicalTraitsArgs],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


_READERS: dict[AudienceEnum, str] = {
    AudienceEnum.CHILDREN: "children",
    AudienceEnum.ADULT: "adults",
}


def describe_lexical_traits(args: FindByLexicalTraitsArgs) -> str:
    """The traits as the user-facing line, e.g. `non-fiction about space, for children`.

    Only what the parse set; all-empty args return "", which `run` refuses.
    """
    subject = " and ".join(keyword for keyword in args.keywords if keyword.strip())
    readers = _READERS[args.audience] if args.audience else None

    if args.genre and subject:
        what = f"{args.genre.value} about {subject}"
    elif args.genre:
        what = f"{args.genre.value} books"
    elif subject:
        what = f"books about {subject}"
    elif readers:
        # audience alone still needs a noun, or the count line reads
        # "Found 447 for children"
        return f"books for {readers}"
    else:
        return ""

    return f"{what}, for {readers}" if readers else what
